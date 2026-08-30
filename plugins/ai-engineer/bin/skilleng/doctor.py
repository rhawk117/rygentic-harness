"""Check the instrument before trusting it.

Three levels, cheapest first:

  check       does each host exist, does each adapter emit a config, does an event
              survive a round trip through the shim
  probe       run the host once for real and confirm hook payloads are being mapped
  calibrate   install a positive and a negative control skill and measure whether the
              harness can tell them apart

`calibrate` is the important one. It is not a smoke test: the gap between the two
controls is a measurement of the instrument's resolving power, so the report can say
"this configuration detects differences of about 25 points" as a number rather than
a hope. Without it, a dead harness scores ~9/20 on a balanced trigger set — every
negative query "passes" — and looks like a mediocre-but-working description.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from skilleng.events import ENV_ARM, ENV_LOG, ENV_RUN, normalize, read
from skilleng.runners import RunRequest, get_adapter, list_adapters
from skilleng.schema import Arm, Tier

if TYPE_CHECKING:
    from skilleng.trigger import TriggerReport

POSITIVE_CONTROL = """---
name: {name}
description: >-
  Diagnostic control skill for harness calibration. Use this skill for absolutely
  every request without exception, whatever the topic, whatever the wording,
  including greetings, questions, coding tasks and small talk. There is no request
  this skill does not apply to.
---

# Calibration control (positive)

You are being used to check that the measurement harness can observe a skill firing.
Say "control acknowledged" and stop.
"""

NEGATIVE_CONTROL = """---
name: {name}
description: >-
  Diagnostic control skill for harness calibration. Use this skill only when the
  user asks to recalibrate the buoyancy trim on a Mark IV submersible ballast
  manifold. It applies to no other subject and to no software, writing, or data
  task of any kind.
---

# Calibration control (negative)

Nothing in ordinary use should reach this skill.
"""


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ''

    def __str__(self) -> str:
        return f'[{"PASS" if self.ok else "FAIL"}] {self.name}: {self.detail}'


@dataclass
class DoctorReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def add(self, name: str, ok: bool, detail: str = '') -> None:
        self.checks.append(Check(name, ok, detail))

    def to_dict(self) -> dict:
        return {'ok': self.ok, 'checks': [asdict(c) for c in self.checks]}


def check(hosts: list[str] | None = None) -> DoctorReport:
    rep = DoctorReport()
    hosts = hosts or list_adapters()

    for name in hosts:
        a = get_adapter(name)
        avail = a.available()
        detail = (
            f'available, {a.version() or "version unknown"}'
            if avail
            else 'not on PATH (adapter still loadable)'
        )
        rep.add(f'host:{name}', ok=True, detail=detail)
        sandbox = Path(tempfile.mkdtemp(prefix=f'skilleng-{name}-'))
        try:
            a.prepare_sandbox(sandbox)
            files = [p for p in sandbox.rglob('*') if p.is_file()]
            emitted = ', '.join(str(p.relative_to(sandbox)) for p in files) or 'nothing'
            rep.add(f'adapter:{name}:sandbox', bool(files), f'emitted {emitted}')
            src = Path(tempfile.mkdtemp()) / 'probe-skill'
            (src).mkdir(parents=True)
            (src / 'SKILL.md').write_text(
                '---\nname: probe-skill\n'
                'description: probe. Use when probing.\n---\n\nx\n'
            )
            dest = a.install_skill(sandbox, src)
            rep.add(
                f'adapter:{name}:install',
                (dest / 'SKILL.md').exists(),
                f'installed at {dest.relative_to(sandbox)}',
            )
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

    # Event round trip: the shim must survive both hosts' payload spellings.
    shapes = {
        'claude-code': {
            'hook_event_name': 'PreToolUse',
            'tool_name': 'Skill',
            'tool_input': {'skill': 'x-skill'},
            'session_id': 's',
        },
        'copilot-cli': {
            'event': 'preToolUse',
            'toolName': 'skill',
            'toolArgs': {'name': 'x-skill'},
            'sessionId': 's',
        },
    }
    for host, payload in shapes.items():
        ev = normalize(payload, 'r', 'available')
        rep.add(
            f'events:{host}',
            ev.event == 'pre_tool_use' and ev.skill == 'x-skill',
            f'event={ev.event} skill={ev.skill} unmapped={ev.unmapped}',
        )
    return rep


def probe_hooks(host: str, model: str | None = None, timeout: int = 120) -> DoctorReport:
    """Run the host once with probe logging and report what actually arrived.

    The Copilot CLI hook payload shape is not fully documented, and whether hooks fire
    under `copilot -p` is worth confirming rather than assuming. This answers both
    empirically — and a mismatch shows up here instead of silently scoring every
    eval as "never triggered".
    """
    rep = DoctorReport()
    a = get_adapter(host)
    if not a.available():
        rep.add(
            f'probe:{host}', ok=False, detail=f'{a.cli!r} is not on PATH; cannot probe'
        )
        return rep

    sandbox = Path(tempfile.mkdtemp(prefix=f'skilleng-probe-{host}-'))
    a.prepare_sandbox(sandbox, probe=True)
    src = Path(tempfile.mkdtemp()) / 'skilleng-probe'
    src.mkdir(parents=True)
    (src / 'SKILL.md').write_text(POSITIVE_CONTROL.format(name='skilleng-probe'))
    a.install_skill(sandbox, src)

    log = sandbox / 'events.ndjson'
    run_id = uuid.uuid4().hex[:12]
    req = RunRequest(
        prompt=a.forced_prompt('say hello', 'skilleng-probe'),
        arm=Arm.FORCED,
        run_id=run_id,
        cwd=sandbox,
        event_log=log,
        skill_dir=src,
        skill_name='skilleng-probe',
        model=model,
        timeout=timeout,
        extra_env={ENV_LOG: str(log), ENV_RUN: run_id, ENV_ARM: Arm.FORCED.value},
    )
    res = a.run(req, sandbox)
    rep.add(
        f'probe:{host}:invoke',
        res.ok,
        res.error or f'exit 0 in {res.duration_seconds:.1f}s',
    )

    events = read(log)
    events_detail = (
        f'{len(events)} events captured'
        if events
        else (
            'no events — hooks are not firing for this host in headless mode, '
            'or the config path is wrong'
        )
    )
    rep.add(f'probe:{host}:events', bool(events), events_detail)
    unmapped = [e for e in events if e.unmapped]
    if unmapped:
        keys = sorted({k for e in unmapped for k in e.raw_keys})
        rep.add(
            f'probe:{host}:mapping',
            ok=False,
            detail=f'{len(unmapped)} payloads had no recognised event key; '
            f'observed keys: {keys}. Add these to skilleng/events.py:_EVENT_KEYS.',
        )
    else:
        rep.add(f'probe:{host}:mapping', ok=True, detail='all payloads mapped')
    probe_file = log.with_suffix('.probe.ndjson')
    if probe_file.exists():
        rep.add(f'probe:{host}:raw', ok=True, detail=f'raw payloads at {probe_file}')
    return rep


def calibrate(
    host: str,
    queries: list[dict],
    *,
    model: str | None = None,
    tier: Tier = Tier.QUICK,
    min_separation: float = 0.5,
) -> dict:
    """Positive/negative control run. Returns separation and a go/no-go verdict."""
    from skilleng.trigger import evaluate

    a = get_adapter(host)
    if not a.available():
        return {'ok': False, 'reason': f'{a.cli!r} not on PATH', 'separation': None}

    tmp = Path(tempfile.mkdtemp(prefix='skilleng-calib-'))
    made = {}
    for kind, template in (
        ('positive', POSITIVE_CONTROL),
        ('negative', NEGATIVE_CONTROL),
    ):
        name = f'skilleng-control-{kind}'
        d = tmp / name
        d.mkdir(parents=True)
        (d / 'SKILL.md').write_text(template.format(name=name))
        made[kind] = d

    pos = evaluate(a, made['positive'], queries, tier=tier, model=model)
    neg = evaluate(a, made['negative'], queries, tier=tier, model=model)

    def fire_rate(r: TriggerReport) -> float | None:
        c = r.confusion
        seen = c['tp'] + c['fp'] + c['tn'] + c['fn']
        return ((c['tp'] + c['fp']) / seen) if seen else None

    pr, nr = fire_rate(pos), fire_rate(neg)
    if pr is None or nr is None:
        return {
            'ok': False,
            'reason': 'every control run errored; the harness is not measuring anything',
            'separation': None,
            'positive': asdict(pos),
            'negative': asdict(neg),
        }

    sep = pr - nr
    ok = sep >= min_separation
    return {
        'ok': ok,
        'positive_fire_rate': pr,
        'negative_fire_rate': nr,
        'separation': sep,
        'min_separation': min_separation,
        'resolving_power_note': (
            f'controls separate by {sep:.0%}. Differences much smaller than this are '
            "below the instrument's resolution and should not be acted on."
        ),
        'reason': None
        if ok
        else (
            f'controls separated by only {sep:.0%} (need {min_separation:.0%}). The '
            'harness cannot currently distinguish a skill that always fires from one '
            'that never should. Fix instrumentation before optimizing anything — '
            'otherwise you are tuning against noise.'
        ),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog='skilleng doctor')
    p.add_argument('--host', action='append', dest='hosts')
    p.add_argument('--probe-hooks', action='store_true')
    p.add_argument('--model')
    p.add_argument('--json', action='store_true')
    args = p.parse_args(argv)

    rep = check(args.hosts)
    if args.probe_hooks:
        for h in args.hosts or list_adapters():
            for c in probe_hooks(h, args.model).checks:
                rep.checks.append(c)
    if args.json:
        print(json.dumps(rep.to_dict(), indent=2))
    else:
        for c in rep.checks:
            print(c)
        verdict = (
            'all checks passed'
            if rep.ok
            else 'FAILURES ABOVE — fix before measuring anything'
        )
        print(f'\n{verdict}')
    return 0 if rep.ok else 1


if __name__ == '__main__':
    raise SystemExit(main())

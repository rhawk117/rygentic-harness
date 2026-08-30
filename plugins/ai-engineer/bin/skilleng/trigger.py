"""Triggering as a classification problem, measured against a real install.

Two things make this different from skill-creator's description optimizer:

  * The skill is genuinely installed and invocation is read from the hook event log.
    skill-creator writes a *slash command* carrying the description into
    `.claude/commands/` and measures whether that fires — a different mechanism in a
    different part of the prompt, with no published evidence the proxy correlates.
  * Competitive mode is the default. Real triggering is a contest among the whole
    installed roster; measuring one skill alone is an optimistic upper bound, and it
    cannot see the neighbour a "pushy" description started stealing from.
"""

from __future__ import annotations

import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from skilleng.events import ENV_LOG, prompt_mentions_skill, read, skill_invoked
from skilleng.runners import HostAdapter, RunRequest
from skilleng.schema import Arm, Outcome, Tier
from skilleng.stats import mcnemar_exact, mde_proportion, wilson


@dataclass
class QueryResult:
    query: str
    should_trigger: bool
    fired: int = 0
    runs: int = 0
    errors: int = 0
    outcome: str = Outcome.ERROR.value
    stole_from: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float | None:
        n = self.runs - self.errors
        return (self.fired / n) if n else None


@dataclass
class TriggerReport:
    skill_name: str
    mode: str  # "competitive" | "isolated"
    tier: str
    results: list[dict]
    confusion: dict
    metrics: dict
    diagnostics: list[str]


def evaluate(
    adapter: HostAdapter,
    skill_dir: Path,
    queries: list[dict],
    *,
    tier: Tier = Tier.STANDARD,
    model: str | None = None,
    timeout: int = 180,
    roster: list[Path] | None = None,
    sandbox: Path | None = None,
    threshold: float = 0.5,
) -> TriggerReport:
    skill_dir = Path(skill_dir).resolve()
    skill_name = skill_dir.name
    roster = roster or []
    mode = 'competitive' if roster else 'isolated'

    sandbox = Path(sandbox or tempfile.mkdtemp(prefix='skilleng-trigger-'))
    adapter.prepare_sandbox(sandbox)
    adapter.install_skill(sandbox, skill_dir)
    for other in roster:
        adapter.install_skill(sandbox, Path(other))

    log = sandbox / 'events.ndjson'
    diagnostics: list[str] = []
    results: list[QueryResult] = []

    for q in queries:
        qr = QueryResult(query=q['query'], should_trigger=bool(q['should_trigger']))
        if prompt_mentions_skill(qr.query, skill_name):
            diagnostics.append(
                f'query names the skill directly ({qr.query[:50]!r}...) — that is a '
                'forced invocation, not a trigger test; excluded.'
            )
            qr.outcome = Outcome.ERROR.value
            qr.errors = 1
            qr.runs = 1
            results.append(qr)
            continue

        for _ in range(tier.runs_per_eval):
            run_id = uuid.uuid4().hex[:12]
            req = RunRequest(
                prompt=qr.query,
                arm=Arm.AVAILABLE,
                run_id=run_id,
                cwd=sandbox,
                event_log=log,
                skill_dir=skill_dir,
                skill_name=skill_name,
                model=model,
                timeout=timeout,
                extra_env={ENV_LOG: str(log)},
            )
            res = adapter.run(req, sandbox)
            qr.runs += 1
            if not res.ok:
                qr.errors += 1
                diagnostics.append(f'run error ({qr.query[:40]}...): {res.error}')
                continue
            events = read(log)
            fired = skill_invoked(events, run_id, skill_name)
            if fired is None:
                qr.errors += 1
                diagnostics.append(
                    'no hook events for a completed run — instrumentation is not '
                    'attached; this is unknown, not a non-trigger. '
                    'Run `skilleng doctor --probe-hooks`.'
                )
                continue
            if fired:
                qr.fired += 1
            for other in roster:
                if skill_invoked(events, run_id, Path(other).name):
                    qr.stole_from.append(Path(other).name)

        rate = qr.rate
        if rate is None:
            qr.outcome = Outcome.ERROR.value
        else:
            hit = rate >= threshold
            qr.outcome = (
                Outcome.PASS.value if hit == qr.should_trigger else Outcome.FAIL.value
            )
        results.append(qr)

    # -- confusion matrix over runs, errors excluded ------------------------
    pos = [r for r in results if r.should_trigger and r.rate is not None]
    neg = [r for r in results if not r.should_trigger and r.rate is not None]
    tp = sum(r.fired for r in pos)
    fn = sum(r.runs - r.errors - r.fired for r in pos)
    fp = sum(r.fired for r in neg)
    tn = sum(r.runs - r.errors - r.fired for r in neg)
    errs = sum(r.errors for r in results)

    precision = wilson(tp, tp + fp) if (tp + fp) else None
    recall = wilson(tp, tp + fn) if (tp + fn) else None
    accuracy = wilson(tp + tn, tp + tn + fp + fn) if (tp + tn + fp + fn) else None

    if errs:
        diagnostics.append(
            f'{errs} runs errored and are excluded from every rate above. '
            'skill-creator counts these as non-triggers, which scores them as '
            'passes on the should-not-trigger half.'
        )
    n_per_side = min(len(pos), len(neg)) * tier.runs_per_eval
    if n_per_side:
        diagnostics.append(
            f'resolving power: with {n_per_side} runs per side this eval can '
            f'detect a difference of about {mde_proportion(n_per_side):.0%} in '
            'trigger rate. Smaller differences are noise.'
        )
    stolen = sorted({s for r in results for s in r.stole_from})
    if stolen:
        diagnostics.append(
            f"cannibalisation: this skill's queries also fired {', '.join(stolen)}. "
            'A pushier description usually takes those invocations from a neighbour.'
        )
    if mode == 'isolated':
        diagnostics.append(
            'isolated mode: only this skill was installed, so these rates are an '
            'optimistic upper bound on deployed behaviour. Pass --roster for the '
            'competitive measurement.'
        )

    return TriggerReport(
        skill_name=skill_name,
        mode=mode,
        tier=tier.value,
        results=[asdict(r) for r in results],
        confusion={'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn, 'errors': errs},
        metrics={
            'precision': asdict(precision) if precision else None,
            'recall': asdict(recall) if recall else None,
            'accuracy': asdict(accuracy) if accuracy else None,
            'intervals_shown': tier.may_claim_intervals,
        },
        diagnostics=diagnostics,
    )


def compare(a: TriggerReport, b: TriggerReport) -> dict:
    """Paired McNemar between two descriptions over the same queries."""
    by_a = {r['query']: r for r in a.results}
    only_a = only_b = 0
    for rb in b.results:
        ra = by_a.get(rb['query'])
        if (
            not ra
            or ra['outcome'] == Outcome.ERROR.value
            or rb['outcome'] == Outcome.ERROR.value
        ):
            continue
        pa, pb = ra['outcome'] == Outcome.PASS.value, rb['outcome'] == Outcome.PASS.value
        only_a += pa and not pb
        only_b += pb and not pa
    return {
        'only_a_correct': only_a,
        'only_b_correct': only_b,
        'p_value': mcnemar_exact(only_a, only_b),
        'test': 'exact McNemar (paired)',
    }

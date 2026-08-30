"""cli.cmd_run's per-arm sandbox/record loop, driven through a scripted HostAdapter.

cmd_run resolves its adapter with `.runners.get_adapter(args.host)` inside the
function body, so monkeypatching that name (re-imported on every call) swaps in a
FakeAdapter without touching cli.py or launching any real host. Namespace objects
stand in for argparse's parsed CLI args, per the plan's note that refactoring
cli.py to avoid that is a separately ticketed finding.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from skilleng.cli import cmd_run
from skilleng.events import Event, append
from skilleng.runners import HostAdapter, RunRequest, RunResult
from skilleng.schema import Arm
from skilleng.workspace import Workspace

SKILL_MD = '---\nname: demo-skill\ndescription: Does a thing. Use when a thing is needed.\n---\n\n# demo-skill\n'


class FakeAdapter(HostAdapter):
    name = 'fake-run-loop'
    cli = 'fake-cli'
    skill_install_subdir = 'skills'

    def __init__(self, *, available: bool = True, ok: bool = True) -> None:
        self._available = available
        self._ok = ok
        self.installed: list[str] = []
        self.calls: list[RunRequest] = []

    def available(self) -> bool:
        return self._available

    def version(self) -> str | None:
        return '1.0.0'

    def prepare_sandbox(self, sandbox: Path, probe: bool = False) -> Path:
        sandbox = Path(sandbox)
        sandbox.mkdir(parents=True, exist_ok=True)
        return sandbox

    def install_skill(self, sandbox: Path, skill_dir: Path) -> Path:
        # cmd_run installs the skill once per non-baseline arm before any run() call,
        # so this cannot key off the request's arm — only the run loop below can.
        self.installed.append(Path(skill_dir).name)
        return Path(sandbox)

    def run(self, req: RunRequest, sandbox: Path) -> RunResult:
        self.calls.append(req)
        if not self._ok:
            return RunResult(False, 1, '', '', 0.01, error='fake run failed')
        if req.arm is not Arm.BASELINE:
            append(
                req.event_log,
                Event(
                    ts='t',
                    event='pre_tool_use',
                    run_id=req.run_id,
                    tool='Skill',
                    skill=req.skill_name,
                ),
            )
        return RunResult(True, 0, 'ok', '', 0.01)


@pytest.fixture
def skill_dir(tmp_path) -> Path:
    d = tmp_path / 'demo-skill'
    d.mkdir()
    (d / 'SKILL.md').write_text(SKILL_MD)
    return d


@pytest.fixture
def evals_path(tmp_path) -> Path:
    p = tmp_path / 'evals.json'
    p.write_text(
        '{"skill_name": "demo-skill", "cases": [{"id": "e1", "prompt": "do a thing", '
        '"assertions": [{"id": "a1", "text": "runs clean", "kind": "mechanical", "check": "true"}]}]}'
    )
    return p


def _args(**overrides) -> argparse.Namespace:
    base = dict(
        skill=None,
        evals=None,
        workspace=None,
        host='fake-run-loop',
        model=None,
        surface='cli',
        tier='quick',
        iteration=None,
        arms=None,
        timeout=30,
        force=False,
        require_controls=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


class TestPerArmLoop:
    def test_writes_one_run_record_per_arm_and_classifies_skill_invoked(
        self, tmp_path, skill_dir, evals_path, monkeypatch
    ):
        adapter = FakeAdapter()
        monkeypatch.setattr('skilleng.runners.get_adapter', lambda name: adapter)
        ws_root = tmp_path / 'ws'
        args = _args(
            skill=str(skill_dir),
            evals=str(evals_path),
            workspace=str(ws_root),
            arms=['baseline', 'available'],
        )

        rc = cmd_run(args)

        assert rc == 0
        ws = Workspace(ws_root)
        runs = {(r.eval_id, r.arm): r for r in ws.load_runs(1)}
        assert runs[('e1', Arm.BASELINE)].skill_invoked is None, (
            'baseline never installs the skill, so invocation is not applicable'
        )
        assert runs[('e1', Arm.AVAILABLE)].skill_invoked is True
        assert adapter.installed == ['demo-skill'], (
            'baseline must not trigger a skill install; only one non-baseline arm ran'
        )

    def test_a_failed_run_is_recorded_as_an_error_not_skipped(
        self, tmp_path, skill_dir, evals_path, monkeypatch
    ):
        adapter = FakeAdapter(ok=False)
        monkeypatch.setattr('skilleng.runners.get_adapter', lambda name: adapter)
        ws_root = tmp_path / 'ws'
        args = _args(
            skill=str(skill_dir),
            evals=str(evals_path),
            workspace=str(ws_root),
            arms=['forced'],
        )

        rc = cmd_run(args)

        assert rc == 0, 'a per-run failure must not abort the whole loop'
        ws = Workspace(ws_root)
        [rec] = ws.load_runs(1)
        assert rec.outcome.value == 'error'
        assert rec.error == 'fake run failed'


class TestEarlyExits:
    def test_refuses_to_run_when_the_host_is_unavailable(
        self, tmp_path, skill_dir, evals_path, monkeypatch
    ):
        adapter = FakeAdapter(available=False)
        monkeypatch.setattr('skilleng.runners.get_adapter', lambda name: adapter)
        args = _args(
            skill=str(skill_dir), evals=str(evals_path), workspace=str(tmp_path / 'ws')
        )

        assert cmd_run(args) == 2
        assert adapter.calls == [], (
            'no run should be attempted once the host is unavailable'
        )

    def test_refuses_to_run_without_the_controls_gate(
        self, tmp_path, skill_dir, evals_path, monkeypatch
    ):
        adapter = FakeAdapter()
        monkeypatch.setattr('skilleng.runners.get_adapter', lambda name: adapter)
        args = _args(
            skill=str(skill_dir),
            evals=str(evals_path),
            workspace=str(tmp_path / 'ws'),
            require_controls=True,
        )

        assert cmd_run(args) == 2
        assert adapter.calls == [], 'controls must be verified before any run is spent'

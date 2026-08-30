"""trigger.evaluate, driven through a scripted HostAdapter instead of a real host.

No subprocess is launched here: FakeAdapter.run() writes the same normalized events
a real hook would have appended to the event log, and returns a fixed RunResult.
That is the seam trigger.evaluate is built on (adapter: HostAdapter), so the
classification arithmetic downstream of it runs unmodified against scripted input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from skilleng.events import Event, append
from skilleng.runners import HostAdapter, RunRequest, RunResult
from skilleng.schema import Outcome, Tier
from skilleng.trigger import evaluate


@dataclass
class ScriptedRun:
    """One scripted response to an adapter.run() call.

    `fired` lists the skill name(s) a hook would have reported for this run;
    None means the run completed but produced no hook events at all (the
    uninstrumented case). `ok=False` simulates a run that failed outright.
    """

    fired: list[str] | None = field(default_factory=list)
    ok: bool = True
    error: str | None = None


class FakeAdapter(HostAdapter):
    name = 'fake-trigger'
    cli = 'fake-cli'
    skill_install_subdir = 'skills'

    def __init__(self, script: list[ScriptedRun]) -> None:
        self._script = iter(script)
        self.calls: list[RunRequest] = []
        self.installed: list[str] = []

    def prepare_sandbox(self, sandbox: Path, probe: bool = False) -> Path:
        sandbox = Path(sandbox)
        sandbox.mkdir(parents=True, exist_ok=True)
        return sandbox

    def install_skill(self, sandbox: Path, skill_dir: Path) -> Path:
        self.installed.append(Path(skill_dir).name)
        return Path(sandbox)

    def run(self, req: RunRequest, sandbox: Path) -> RunResult:
        self.calls.append(req)
        step = next(self._script)
        if step.fired is not None:
            # A run always logs *something* (e.g. a non-skill tool call) unless the
            # host is uninstrumented; `fired=[]` is "ran, skill did not invoke", not
            # "produced no events at all" — the two read differently through
            # events.skill_invoked (False vs None).
            append(
                req.event_log,
                Event(ts='t', event='pre_tool_use', run_id=req.run_id, tool='Bash'),
            )
            for name in step.fired:
                append(
                    req.event_log,
                    Event(
                        ts='t',
                        event='pre_tool_use',
                        run_id=req.run_id,
                        tool='Skill',
                        skill=name,
                    ),
                )
        if not step.ok:
            return RunResult(False, 1, '', '', 0.01, error=step.error or 'boom')
        return RunResult(True, 0, '', '', 0.01)


def _queries(*pairs: tuple[str, bool]) -> list[dict]:
    return [{'query': q, 'should_trigger': should} for q, should in pairs]


class TestConfusionMatrix:
    """One run per query cell (tier=quick), exercising tp/fn/fp/tn arithmetic."""

    def test_counts_land_in_the_right_cell(self, tmp_path):
        skill_dir = tmp_path / 'demo-skill'
        skill_dir.mkdir()
        adapter = FakeAdapter([
            ScriptedRun(fired=['demo-skill']),  # should trigger, did      -> tp
            ScriptedRun(fired=[]),  # should not trigger, did not -> tn
            ScriptedRun(fired=[]),  # should trigger, did not  -> fn
            ScriptedRun(fired=['demo-skill']),  # should not trigger, did  -> fp
        ])
        queries = _queries(
            ('merge these csv files', True),
            ('what is the weather', False),
            ('reticulate the splines', True),
            ('summarise this report', False),
        )
        report = evaluate(adapter, skill_dir, queries, tier=Tier.QUICK)

        assert report.confusion == {'tp': 1, 'fp': 1, 'tn': 1, 'fn': 1, 'errors': 0}
        assert report.metrics['accuracy']['point'] == 0.5
        assert adapter.installed == ['demo-skill'], (
            'the skill under test must be installed once'
        )
        assert len(adapter.calls) == 4, 'one run per query at the quick tier'


class TestPromptMentionsSkillExclusion:
    """trigger.py:~75 — a query naming the skill is a forced invocation, not a trigger test."""

    def test_a_query_that_names_the_skill_is_excluded_not_run(self, tmp_path):
        skill_dir = tmp_path / 'demo-skill'
        skill_dir.mkdir()
        adapter = FakeAdapter([
            ScriptedRun(fired=['demo-skill'])
        ])  # would fire for the other query
        queries = _queries(
            ('please use demo-skill on this file', True),
            ('merge these csv files', True),
        )
        report = evaluate(adapter, skill_dir, queries, tier=Tier.QUICK)

        assert len(adapter.calls) == 1, (
            'the forced-mention query must never reach adapter.run'
        )
        excluded = next(r for r in report.results if r['query'].startswith('please use'))
        assert excluded['outcome'] == Outcome.ERROR.value
        assert excluded['errors'] == 1
        assert any('forced invocation' in d for d in report.diagnostics)


class TestFiredIsNoneErrorPath:
    """trigger.py:~98 — no hook events at all is "unknown", scored as an error, never a non-trigger."""

    def test_an_uninstrumented_run_is_an_error_not_a_miss(self, tmp_path):
        skill_dir = tmp_path / 'demo-skill'
        skill_dir.mkdir()
        adapter = FakeAdapter([ScriptedRun(fired=None)])
        queries = _queries(('merge these csv files', True))
        report = evaluate(adapter, skill_dir, queries, tier=Tier.QUICK)

        result = report.results[0]
        assert result['errors'] == 1
        assert result['fired'] == 0
        assert result['outcome'] == Outcome.ERROR.value
        assert report.confusion == {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'errors': 1}
        assert any('no hook events for a completed run' in d for d in report.diagnostics)

    def test_a_failed_run_is_also_excluded_from_the_confusion_matrix(self, tmp_path):
        skill_dir = tmp_path / 'demo-skill'
        skill_dir.mkdir()
        adapter = FakeAdapter([ScriptedRun(ok=False, error='claude exited 1')])
        queries = _queries(('merge these csv files', True))
        report = evaluate(adapter, skill_dir, queries, tier=Tier.QUICK)

        result = report.results[0]
        assert result['errors'] == 1
        assert result['outcome'] == Outcome.ERROR.value
        assert any('run error' in d for d in report.diagnostics)

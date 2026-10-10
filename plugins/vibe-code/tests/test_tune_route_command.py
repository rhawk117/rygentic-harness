from dataclasses import dataclass
from pathlib import Path

import msgspec
import pytest
from vibe_code_cli.cli import main
from vibe_code_cli.tune.schemas import ProposePacket, StatusSummary
from vibe_code_cli.tune.store import JsonLoopStore
from vibe_code_cli.tune.tests.agent import ScriptedAgent
from vibe_code_cli.tune.tests.support import SkillLibrary
from vibe_code_cli.tune.wiring import STATE_CODEC


@dataclass(slots=True, kw_only=True, frozen=True)
class RoutedRun:
    state: Path
    workdir: Path
    claude: Path
    capsys: pytest.CaptureFixture[str]

    def run(self, *args: str) -> int:
        return main(['tune', '--state', str(self.state), *args])

    def json(self, *args: str) -> dict[str, object]:
        self.capsys.readouterr()
        assert self.run(*args) == 0
        return msgspec.json.decode(self.capsys.readouterr().out)

    def status(self) -> StatusSummary:
        return msgspec.convert(self.json('status'), StatusSummary)

    def route(self) -> int:
        return self.run('route', '--claude', str(self.claude))

    def report(self) -> str:
        self.capsys.readouterr()
        assert self.run('report') == 0
        return self.capsys.readouterr().out

    def step(self, agent: ScriptedAgent) -> str:
        work = self.json('next')
        if work['kind'] == 'route':
            assert self.route() == 0
        if work['kind'] == 'propose':
            packet = msgspec.convert(work, ProposePacket)
            path = self.workdir.joinpath(f'{packet.packet_id}.json')
            path.write_bytes(msgspec.json.encode({'description': agent.propose(packet)}))
            self.json('submit', '--packet', packet.packet_id, '--answer', str(path))
        return str(work['kind'])


@pytest.fixture
def routed_run(tmp_path: Path, capsys: pytest.CaptureFixture[str], fake_claude: Path) -> RoutedRun:
    return RoutedRun(
        state=tmp_path.joinpath('state.json'),
        workdir=tmp_path,
        claude=fake_claude,
        capsys=capsys,
    )


class TestRouteCommand:
    MAX_STEPS = 40

    @pytest.fixture
    def run(self, routed_run: RoutedRun, library: SkillLibrary) -> RoutedRun:
        library_args = ['--skills', str(library.skills_dir)]
        trigger_args = ['--triggers', str(library.triggers_file)]
        routed_run.json('init', *library_args, *trigger_args, '--judge', 'claude-code')
        return routed_run

    def test_routed_run_improves_validation(
        self, run: RoutedRun, scripted_agent: ScriptedAgent
    ) -> None:
        kinds = [run.step(scripted_agent) for _step in range(self.MAX_STEPS)]
        assert 'route' in kinds
        assert 'done' in kinds
        status = run.status()
        assert status.judge == 'claude-code'
        assert status.baseline is not None
        assert status.current is not None
        assert status.current.validation > status.baseline.validation

    def test_competing_skills_are_listed_in_the_report(
        self, run: RoutedRun, scripted_agent: ScriptedAgent
    ) -> None:
        assert run.step(scripted_agent) == 'route'
        report = run.report()
        assert '## Competing skills' in report
        assert 'code-review' in report

    def test_interrupted_route_keeps_finished_packets(
        self, run: RoutedRun, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run.json('next')
        monkeypatch.setenv('FAKE_CLAUDE_CRASH_ON', 'haiku')
        assert run.route() == 1
        partial = JsonLoopStore(path=run.state, codec=STATE_CODEC).read()
        monkeypatch.delenv('FAKE_CLAUDE_CRASH_ON')
        assert run.route() == 0
        finished = JsonLoopStore(path=run.state, codec=STATE_CODEC).read()
        total = len(finished.setup.examples)
        assert 0 < len(partial.in_progress.verdicts) < total
        assert finished.history.baseline is not None
        assert len(finished.history.baseline.verdicts) == total

    def test_route_outside_judging_is_refused(
        self, run: RoutedRun, scripted_agent: ScriptedAgent
    ) -> None:
        assert run.step(scripted_agent) == 'route'
        assert run.status().stage == 'proposing'
        assert run.route() == 1

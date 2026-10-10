"""The CLI contract the host agent relies on, driven end to end."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import msgspec
import pytest
from vibe_code_cli.cli import main
from vibe_code_cli.tune.repository import TriggerEntry, read_skill
from vibe_code_cli.tune.schemas import (
    ApplyResult,
    JudgePacket,
    JudgeWork,
    ProposePacket,
    StatusSummary,
)
from vibe_code_cli.tune.store import JsonLoopStore
from vibe_code_cli.tune.tests.agent import JudgeAnswer, ScriptedAgent
from vibe_code_cli.tune.tests.support import SkillLibrary
from vibe_code_cli.tune.wiring import STATE_CODEC


class Kind(msgspec.Struct, frozen=True, kw_only=True):
    kind: str


@dataclass(slots=True, kw_only=True, frozen=True)
class CliSession:
    state: Path
    workdir: Path
    capsys: pytest.CaptureFixture[str]

    def run(self, *args: str) -> int:
        return main(['tune', '--state', str(self.state), *args])

    def run_argv(self, argv: list[str]) -> int:
        return self.run(*argv)

    def output(self, *args: str) -> bytes:
        self.capsys.readouterr()
        assert self.run(*args) == 0
        return self.capsys.readouterr().out.encode()

    def decoded[T](self, type_: type[T], *args: str) -> T:
        return msgspec.json.decode(self.output(*args), type=type_)

    def answer(self, packet_id: str, payload: object) -> None:
        path = self.workdir.joinpath(f'{packet_id}.json')
        path.write_bytes(msgspec.json.encode(payload))
        self.output('submit', '--packet', packet_id, '--answer', str(path))

    def init(self, library: SkillLibrary, *extra: str) -> int:
        skills = ['--skills', str(library.skills_dir)]
        triggers = ['--triggers', str(library.triggers_file)]
        return self.run('init', *skills, *triggers, '--judge', 'subagent', *extra)

    def judge_packets(self) -> list[JudgePacket]:
        work = self.decoded(JudgeWork, 'next')
        return [
            msgspec.json.decode(Path(entry.path).read_bytes(), type=JudgePacket)
            for entry in work.packets
        ]

    def answer_file(self, packet_id: str, payload: JudgeAnswer) -> str:
        path = self.workdir.joinpath(f'{packet_id}.json')
        path.write_bytes(msgspec.json.encode(payload))
        return str(path)

    def step(self, agent: ScriptedAgent) -> str:
        raw = self.output('next')
        kind = msgspec.json.decode(raw, type=Kind).kind
        if kind == 'judge':
            for entry in msgspec.json.decode(raw, type=JudgeWork).packets:
                packet = msgspec.json.decode(Path(entry.path).read_bytes(), type=JudgePacket)
                self.answer(packet.packet_id, agent.judge(packet))
        if kind == 'propose':
            packet = msgspec.json.decode(raw, type=ProposePacket)
            self.answer(packet.packet_id, {'description': agent.propose(packet)})
        return kind


@pytest.fixture
def session(
    tmp_path: Path, library: SkillLibrary, capsys: pytest.CaptureFixture[str]
) -> CliSession:
    state = tmp_path.joinpath('state.json')
    cli = CliSession(state=state, workdir=tmp_path, capsys=capsys)
    assert cli.init(library) == 0
    return cli


class TestUsage:
    def test_tune_without_a_command_prints_usage_and_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(['tune']) == 2
        assert 'usage: vibe-code' in capsys.readouterr().err


class TestFinishedRun:
    @pytest.fixture
    def finished(self, session: CliSession, scripted_agent: ScriptedAgent) -> CliSession:
        kinds = [session.step(scripted_agent) for _step in range(60)]
        assert 'done' in kinds
        return session

    def test_status_reports_improvement(self, finished: CliSession) -> None:
        status = finished.decoded(StatusSummary, 'status')
        assert status.current is not None
        assert status.baseline is not None
        assert status.current.validation > status.baseline.validation

    def test_apply_writes_tuned_descriptions(self, finished: CliSession, skills_dir: Path) -> None:
        result = finished.decoded(ApplyResult, 'apply')
        written = {change.skill: change.description for change in result.changes}
        assert written
        for name, description in written.items():
            assert read_skill(skills_dir.joinpath(name, 'SKILL.md')).description == description

    def test_dry_run_leaves_files_alone(self, finished: CliSession, skills_dir: Path) -> None:
        before = skills_dir.joinpath('jira', 'SKILL.md').read_text(encoding='utf-8')
        assert finished.run('apply', '--dry-run') == 0
        assert skills_dir.joinpath('jira', 'SKILL.md').read_text(encoding='utf-8') == before


class TestInitValidation:
    def test_init_refuses_to_clobber_a_run(
        self, session: CliSession, skills_dir: Path, triggers_file: Path
    ) -> None:
        code = session.run('init', '--skills', str(skills_dir), '--triggers', str(triggers_file))
        assert code == 1

    def test_invalid_skill_name_is_refused_at_init(
        self, tmp_path: Path, library: SkillLibrary, capsys: pytest.CaptureFixture[str]
    ) -> None:
        library.rename_skill('jira', '../jira')
        state = tmp_path.joinpath('fresh-state.json')
        code = main(
            [
                'tune',
                '--state',
                str(state),
                'init',
                '--skills',
                str(library.skills_dir),
                '--triggers',
                str(library.triggers_file),
            ]
        )
        assert code == 1
        assert 'lowercase' in capsys.readouterr().err

    def test_malformed_trigger_yaml_is_a_clean_error(
        self, tmp_path: Path, library: SkillLibrary, capsys: pytest.CaptureFixture[str]
    ) -> None:
        library.triggers_file.write_text('- request: [unclosed\n', encoding='utf-8')
        cli = CliSession(state=tmp_path.joinpath('other.json'), workdir=tmp_path, capsys=capsys)
        assert cli.init(library) == 1
        assert 'not a valid trigger set' in capsys.readouterr().err

    def test_non_positive_timeout_is_refused(
        self, tmp_path: Path, library: SkillLibrary, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cli = CliSession(
            state=tmp_path.joinpath('timeout-state.json'), workdir=tmp_path, capsys=capsys
        )
        assert cli.init(library, '--timeout', '0') == 1
        assert '--timeout must be positive' in capsys.readouterr().err


class TestRunIntegrity:
    def test_report_and_apply_work_before_baseline_finishes(self, session: CliSession) -> None:
        assert session.run('next') == 0
        assert session.run('report') == 0
        result = session.decoded(ApplyResult, 'apply', '--dry-run')
        assert result == ApplyResult(written=False, changes=())

    def test_printed_work_never_contains_request_text(
        self, session: CliSession, library: SkillLibrary
    ) -> None:
        session.capsys.readouterr()
        assert session.run('next') == 0
        printed = session.capsys.readouterr().out
        entries = msgspec.json.decode(library.triggers_file.read_bytes(), type=list[TriggerEntry])
        assert not [entry.request for entry in entries if entry.request in printed]

    def test_parallel_submits_keep_every_answer(
        self, session: CliSession, scripted_agent: ScriptedAgent
    ) -> None:
        packets = session.judge_packets()
        submissions = [
            [
                'submit',
                '--packet',
                p.packet_id,
                '--answer',
                session.answer_file(p.packet_id, scripted_agent.judge(p)),
            ]
            for p in packets
        ]
        with ThreadPoolExecutor(max_workers=len(submissions)) as pool:
            codes = list(pool.map(session.run_argv, submissions))
        assert codes == [0] * len(submissions)
        state = JsonLoopStore(path=session.state, codec=STATE_CODEC).read()
        assert state.history.baseline is not None
        assert len(state.history.baseline.verdicts) == len(state.setup.examples)

    def test_answers_from_a_replaced_run_are_refused(
        self, session: CliSession, library: SkillLibrary, scripted_agent: ScriptedAgent
    ) -> None:
        stale = session.judge_packets()[0]
        assert session.init(library, '--force') == 0
        session.judge_packets()
        path = session.answer_file(stale.packet_id, scripted_agent.judge(stale))
        assert session.run('submit', '--packet', stale.packet_id, '--answer', path) == 1

    def test_stale_packet_answer_is_an_error(self, session: CliSession) -> None:
        path = session.workdir.joinpath('stale.json')
        path.write_bytes(b'{}')
        assert session.run('submit', '--packet', 'j999', '--answer', str(path)) == 1


class TestStateCompatibility:
    def test_state_from_an_older_version_is_a_clean_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        state = tmp_path.joinpath('state.json')
        state.write_bytes(msgspec.json.encode({'run_id': 'old', 'stage': 'done'}))
        assert main(['tune', '--state', str(state), 'status']) == 1
        assert 'another version' in capsys.readouterr().err

    def test_malformed_answer_is_a_clean_error(
        self, session: CliSession, capsys: pytest.CaptureFixture[str]
    ) -> None:
        packet = session.judge_packets()[0]
        path = session.workdir.joinpath('bad.json')
        path.write_bytes(b'{"q1": "not a list"')
        code = session.run('submit', '--packet', packet.packet_id, '--answer', str(path))
        assert code == 1
        assert 'wrong shape' in capsys.readouterr().err

"""TuningService driven by a scripted host agent against in-memory adapters."""

from dataclasses import replace

import msgspec
import pytest
from vibe_code_cli.tune.domain.scoring import score_verdicts
from vibe_code_cli.tune.domain.state import LoopState
from vibe_code_cli.tune.domain.values import Split, Stage
from vibe_code_cli.tune.errors import (
    InvalidProposalError,
    InvalidSkillNameError,
    PacketNotPendingError,
    RunFinishedError,
    StateExistsError,
)
from vibe_code_cli.tune.schemas import DoneWork, JudgeWork, ProposePacket
from vibe_code_cli.tune.services import StartRequest
from vibe_code_cli.tune.tests.agent import ScriptedAgent
from vibe_code_cli.tune.tests.support import MemoryRun, SkillLibrary


def encode(value: object) -> bytes:
    return msgspec.json.encode(value)


class TestDrivenRun:
    @pytest.fixture
    def finished(self, started: MemoryRun, scripted_agent: ScriptedAgent) -> LoopState:
        kinds = scripted_agent.drive(started.tuning, started.packets)
        assert kinds[-1] == 'done'
        return started.state

    def test_run_finishes(self, finished: LoopState) -> None:
        assert finished.stage is Stage.DONE

    def test_validation_score_improves_over_baseline(self, finished: LoopState) -> None:
        history, examples = finished.history, finished.setup.examples
        assert history.baseline is not None
        assert history.accepted is not None
        before = score_verdicts(examples, history.baseline.verdicts)
        after = score_verdicts(examples, history.accepted.verdicts)
        assert after.validation > before.validation

    def test_accepted_rounds_never_lower_validation(self, finished: LoopState) -> None:
        accepted = [r.validation for r in finished.history.rounds if r.accepted]
        assert accepted == sorted(accepted)

    def test_proposals_never_show_validation_requests(
        self, finished: LoopState, scripted_agent: ScriptedAgent
    ) -> None:
        validation = {e.request for e in finished.setup.examples if e.split is Split.VALIDATION}
        shown = {
            request
            for packet in scripted_agent.proposals
            for request in (*packet.missed, *packet.false_triggers)
        }
        assert shown
        assert not shown & validation

    def test_run_respects_round_budget(self, finished: LoopState) -> None:
        assert len(finished.history.rounds) <= finished.setup.options.max_rounds

    @pytest.mark.usefixtures('finished')
    def test_finished_run_refuses_answers(self, started: MemoryRun) -> None:
        with pytest.raises(RunFinishedError):
            started.tuning.submit('p1-t0', encode({'description': 'late'}))

    @pytest.mark.usefixtures('finished')
    def test_finished_run_keeps_answering_done(self, started: MemoryRun) -> None:
        assert isinstance(started.tuning.next_work(), DoneWork)


class TestJudgeWork:
    @pytest.fixture
    def work(self, started: MemoryRun) -> JudgeWork:
        work = started.tuning.next_work()
        assert isinstance(work, JudgeWork)
        return work

    def test_every_example_is_judged_exactly_once(
        self, started: MemoryRun, work: JudgeWork
    ) -> None:
        requests = [
            text
            for published in work.packets
            for text in started.packets.packets[published.packet_id].requests.values()
        ]
        assert sorted(requests) == sorted(e.request for e in started.state.setup.examples)

    def test_packets_number_their_requests(self, started: MemoryRun, work: JudgeWork) -> None:
        packet = started.packets.packets[work.packets[0].packet_id]
        assert set(packet.requests) == {f'q{i}' for i in range(1, len(packet.requests) + 1)}

    def test_asking_again_returns_the_same_pending_packets(
        self, started: MemoryRun, work: JudgeWork
    ) -> None:
        assert started.tuning.next_work() == work

    def test_answer_for_unknown_packet_is_refused(
        self, started: MemoryRun, work: JudgeWork
    ) -> None:
        assert work.packets
        with pytest.raises(PacketNotPendingError):
            started.tuning.submit('j999', b'{}')


class TestProposals:
    @pytest.fixture
    def packet(self, started: MemoryRun, scripted_agent: ScriptedAgent) -> ProposePacket:
        assert scripted_agent.step(started.tuning, started.packets) == 'judge'
        work = started.tuning.next_work()
        assert isinstance(work, ProposePacket)
        return work

    @pytest.mark.parametrize(
        ('description', 'reason'),
        [
            pytest.param('   ', 'empty', id='blank'),
            pytest.param('x' * 2000, 'longer than', id='too-long'),
            pytest.param('Use for <xml> work', 'angle brackets', id='angle-brackets'),
            pytest.param('Use for\x7fwork', 'control characters', id='delete-char'),
            pytest.param('Use for\x85work', 'control characters', id='next-line'),
        ],
    )
    def test_invalid_proposals_are_refused(
        self, *, started: MemoryRun, packet: ProposePacket, description: str, reason: str
    ) -> None:
        answer = encode({'description': description})
        with pytest.raises(InvalidProposalError, match=reason):
            started.tuning.submit(packet.packet_id, answer)

    def test_current_description_cannot_be_resubmitted(
        self, started: MemoryRun, packet: ProposePacket
    ) -> None:
        answer = encode({'description': packet.current})
        with pytest.raises(InvalidProposalError, match='identical'):
            started.tuning.submit(packet.packet_id, answer)

    def test_packet_lists_training_failures(self, packet: ProposePacket) -> None:
        assert packet.missed or packet.false_triggers

    def test_refused_proposal_leaves_state_unchanged(
        self, started: MemoryRun, packet: ProposePacket
    ) -> None:
        before = started.store.data
        with pytest.raises(InvalidProposalError):
            started.tuning.submit(packet.packet_id, encode({'description': ''}))
        assert started.store.data == before


class TestStart:
    def test_existing_run_is_not_clobbered(
        self, started: MemoryRun, start_request: StartRequest
    ) -> None:
        with pytest.raises(StateExistsError):
            started.tuning.start(start_request)

    def test_answers_from_a_replaced_run_are_refused(
        self,
        started: MemoryRun,
        start_request: StartRequest,
        scripted_agent: ScriptedAgent,
    ) -> None:
        stale = started.tuning.next_work()
        assert isinstance(stale, JudgeWork)
        old = started.packets.packets[stale.packets[0].packet_id]
        started.tuning.start(replace(start_request, force=True))
        started.tuning.next_work()
        with pytest.raises(PacketNotPendingError):
            started.tuning.submit(old.packet_id, encode(scripted_agent.judge(old)))

    def test_invalid_skill_name_is_refused(
        self, memory_run: MemoryRun, start_request: StartRequest, library: SkillLibrary
    ) -> None:
        library.rename_skill('jira', '../jira')
        with pytest.raises(InvalidSkillNameError):
            memory_run.tuning.start(start_request)
        assert memory_run.store.data is None

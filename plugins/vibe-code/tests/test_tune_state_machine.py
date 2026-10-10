"""TuningService as a state machine: any interleaving of agent moves keeps the run sound.

`TuningRunInvariants` holds what must stay true after every step; `TuningMachine`
holds the moves a host agent can make, valid and invalid.
"""

from dataclasses import dataclass, field, replace
from operator import attrgetter
from pathlib import Path

import msgspec
from hypothesis import assume, settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
    run_state_machine_as_test,
)
from vibe_code_cli.tune.domain.scoring import score_verdicts
from vibe_code_cli.tune.domain.state import LoopState
from vibe_code_cli.tune.domain.values import LoopOptions, Skill, Split, Stage
from vibe_code_cli.tune.errors import (
    InvalidProposalError,
    InvalidVerdictError,
    MalformedAnswerError,
    PacketNotPendingError,
    RunFinishedError,
    TuneError,
)
from vibe_code_cli.tune.repository import TriggerEntry
from vibe_code_cli.tune.schemas import (
    JudgePacket,
    JudgeWork,
    ProposalAnswer,
    ProposePacket,
    Work,
    status_summary,
)
from vibe_code_cli.tune.services import StartRequest, TuningService
from vibe_code_cli.tune.tests.fakes import (
    MemoryLoopStore,
    MemoryPacketPublisher,
    MemorySkillRepository,
    MemoryTriggerSetReader,
    SequentialRunIds,
)
from vibe_code_cli.tune.tests.strategies import (
    invalid_proposals,
    judge_answers,
    loop_options,
    malformed_judge_answers,
    skill_libraries,
    trigger_entries,
)
from vibe_code_cli.tune.wiring import STATE_CODEC

LIBRARY = Path('memory:skills')
TRIGGERS = Path('memory:triggers')
STAGE_ORDER = (Stage.PROPOSING, Stage.JUDGING, Stage.DONE)


def progress(state: LoopState) -> tuple[int, int]:
    history = state.history
    evaluations = len(history.rounds) + int(history.baseline is not None)
    return evaluations, STAGE_ORDER.index(state.stage)


def issued_packet_ids(work: Work) -> set[str]:
    if isinstance(work, JudgeWork):
        return {published.packet_id for published in work.packets}
    if isinstance(work, ProposePacket):
        return {work.packet_id}
    return set()


@dataclass(slots=True, kw_only=True)
class RunUnderTest:
    store: MemoryLoopStore
    packets: MemoryPacketPublisher
    tuning: TuningService
    request: StartRequest
    previous: LoopState | None = None
    last_work: Work | None = None
    issued: set[str] = field(default_factory=set)
    restarted: bool = False

    @property
    def state(self) -> LoopState:
        return self.store.read()

    @property
    def previous_in_run(self) -> LoopState | None:
        previous = self.previous
        same_run = previous and previous.setup.run_id == self.state.setup.run_id
        return previous if same_run else None

    @property
    def pending_packet_ids(self) -> tuple[str, ...]:
        return status_summary(self.state).pending_packets

    @property
    def judge_packets(self) -> tuple[JudgePacket, ...]:
        records = self.state.pending_judge_records
        return tuple(self.packets.packets[record.packet_id] for record in records)

    @property
    def proposal(self) -> ProposePacket | None:
        work, pending = self.last_work, self.state.pending_proposal
        open_packet = isinstance(work, ProposePacket) and pending is not None
        return work if open_packet and work.packet_id == pending.packet_id else None

    def next_work(self) -> None:
        self.previous = self.state
        self.last_work = self.tuning.next_work()
        self.issued |= issued_packet_ids(self.last_work)

    def submit(self, packet_id: str, answer: bytes) -> TuneError | None:
        before, stored = self.state, self.store.data
        self.previous = before
        try:
            self.tuning.submit(packet_id, answer)
        except TuneError as refusal:
            assert self.store.data == stored
            return refusal
        assert before.stage is not Stage.DONE
        return None

    def restart(self) -> None:
        self.previous = self.state
        self.tuning.start(replace(self.request, force=True))
        self.last_work = None
        self.restarted = True


def restart_is_open(machine: 'TuningMachine') -> bool:
    run = machine.run
    return not run.restarted and run.state.history.baseline is not None


def start_memory_run(
    skills: tuple[Skill, ...], entries: list[TriggerEntry], options: LoopOptions
) -> RunUnderTest:
    store, packets = MemoryLoopStore(), MemoryPacketPublisher()
    tuning = TuningService(
        store=store,
        skills=MemorySkillRepository(libraries={LIBRARY: skills}),
        triggers=MemoryTriggerSetReader(trigger_sets={TRIGGERS: entries}),
        packets=packets,
        run_ids=SequentialRunIds(),
    )
    request = StartRequest(skills=(LIBRARY,), triggers=TRIGGERS, options=options)
    tuning.start(request)
    return RunUnderTest(store=store, packets=packets, tuning=tuning, request=request)


class TuningRunInvariants(RuleBasedStateMachine):
    run: RunUnderTest

    @invariant()
    def stage_only_moves_forward(self) -> None:
        previous = self.run.previous_in_run
        if previous is not None:
            assert progress(previous) <= progress(self.run.state)

    @invariant()
    def packet_counter_never_decreases(self) -> None:
        previous = self.run.previous_in_run
        if previous is not None:
            assert previous.packet_counter <= self.run.state.packet_counter

    @invariant()
    def pending_packet_ids_are_unique(self) -> None:
        pending = self.run.pending_packet_ids
        assert len(pending) == len(set(pending))

    @invariant()
    def accepted_validation_never_decreases(self) -> None:
        state = self.run.state
        history = state.history
        if history.baseline is not None:
            baseline = score_verdicts(state.setup.examples, history.baseline.verdicts)
            accepted = [r.validation for r in history.rounds if r.accepted]
            scores = [baseline.validation, *accepted]
            assert scores == sorted(scores)

    @invariant()
    def rounds_stay_within_budget(self) -> None:
        state = self.run.state
        assert len(state.history.rounds) <= state.setup.options.max_rounds

    @invariant()
    def proposals_hide_validation_requests(self) -> None:
        work = self.run.last_work
        if isinstance(work, ProposePacket):
            examples = self.run.state.setup.examples
            hidden = {e.request for e in examples if e.split is Split.VALIDATION}
            assert not hidden & {*work.missed, *work.false_triggers}

    @invariant()
    def state_round_trips_through_json(self) -> None:
        state = self.run.state
        assert STATE_CODEC.decode(STATE_CODEC.encode(state)) == state


class TuningMachine(TuningRunInvariants):
    unknown_packet_ids = st.from_regex(r'[jp][0-9]{1,3}-x[0-9]', fullmatch=True) | st.text(
        max_size=8
    )
    stale_answers = st.sampled_from((b'{"q1": []}', b'{"description": "Use for anything."}'))
    fresh_descriptions = st.from_regex(r'Use for [a-z ]{1,30}\.', fullmatch=True)

    @initialize(data=st.data())
    def start(self, *, data: st.DataObject) -> None:
        skills = data.draw(skill_libraries())
        entries = data.draw(trigger_entries(skills))
        self.run = start_memory_run(skills, entries, data.draw(loop_options))

    @rule()
    def ask_for_next_work(self) -> None:
        self.run.next_work()

    @precondition(attrgetter('run.judge_packets'))
    @rule(data=st.data())
    def judge_correctly(self, *, data: st.DataObject) -> None:
        packet = data.draw(st.sampled_from(self.run.judge_packets))
        answer = msgspec.json.encode(data.draw(judge_answers(packet)))
        assert self.run.submit(packet.packet_id, answer) is None

    @precondition(attrgetter('run.judge_packets'))
    @rule(data=st.data())
    def judge_malformed(self, *, data: st.DataObject) -> None:
        packet = data.draw(st.sampled_from(self.run.judge_packets))
        refusal = self.run.submit(packet.packet_id, data.draw(malformed_judge_answers(packet)))
        assert isinstance(refusal, InvalidVerdictError | MalformedAnswerError)

    @rule(data=st.data())
    def answer_unknown_or_stale(self, *, data: st.DataObject) -> None:
        pending = self.run.pending_packet_ids
        stale = sorted(self.run.issued.difference(pending))
        packet_ids = (
            st.sampled_from(stale) | self.unknown_packet_ids if stale else self.unknown_packet_ids
        )
        packet_id = data.draw(packet_ids)
        assume(packet_id not in pending)
        refusal = self.run.submit(packet_id, data.draw(self.stale_answers))
        assert isinstance(refusal, PacketNotPendingError | RunFinishedError)

    @precondition(attrgetter('run.proposal'))
    @rule(data=st.data())
    def propose_valid(self, *, data: st.DataObject) -> None:
        packet = self.run.proposal
        assert packet is not None
        description = data.draw(self.fresh_descriptions)
        assume(description not in {packet.current, *packet.rejected})
        answer = msgspec.json.encode(ProposalAnswer(description=description))
        assert self.run.submit(packet.packet_id, answer) is None

    @precondition(attrgetter('run.proposal'))
    @rule(data=st.data())
    def propose_invalid(self, *, data: st.DataObject) -> None:
        packet = self.run.proposal
        assert packet is not None
        description = data.draw(invalid_proposals(packet))
        answer = msgspec.json.encode(ProposalAnswer(description=description))
        refusal = self.run.submit(packet.packet_id, answer)
        assert isinstance(refusal, InvalidProposalError)

    @precondition(restart_is_open)
    @rule()
    def restart_with_force(self) -> None:
        self.run.restart()


class TestTuningMachine:
    machine_settings = settings(max_examples=50, stateful_step_count=80, deadline=None)

    def test_any_sequence_of_agent_moves_keeps_the_run_sound(self) -> None:
        run_state_machine_as_test(TuningMachine, settings=self.machine_settings)

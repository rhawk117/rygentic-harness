"""The loop aggregate's transitions, exercised directly without any service."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from vibe_code_cli.tune.domain.state import LoopState, RunSetup, start_loop
from vibe_code_cli.tune.domain.values import LoopOptions, Skill, Split, Stage, TriggerExample
from vibe_code_cli.tune.errors import InvalidVerdictError, PacketNotPendingError
from vibe_code_cli.tune.tests.strategies import run_setups

SKILLS = (
    Skill(name='alpha', path='/alpha/SKILL.md', description='Use for alpha work.'),
    Skill(name='beta', path='/beta/SKILL.md', description='Use for beta work.'),
)


def build_setup(count: int, batch_size: int = 3) -> RunSetup:
    examples = tuple(
        TriggerExample(
            request_id=f'r{n}',
            request=f'request {n}',
            expected=frozenset({'alpha'}) if n % 2 else frozenset(),
            split=Split.VALIDATION if n % 3 == 0 else Split.TRAIN,
        )
        for n in range(count)
    )
    return RunSetup(
        run_id='d0',
        skills=SKILLS,
        examples=examples,
        options=LoopOptions(batch_size=batch_size),
    )


def judge_everything(state: LoopState) -> LoopState:
    planned = state.with_judging_planned()
    assert planned.judging is not None
    for record in planned.judging.pending:
        verdicts = [frozenset({'alpha'})] * len(record.request_ids)
        planned = planned.with_verdicts(record.packet_id, verdicts)
    return planned


class TestPlanRecords:
    @given(st.integers(min_value=1, max_value=40), st.integers(min_value=1, max_value=12))
    def test_records_partition_the_requests(self, count: int, batch_size: int) -> None:
        setup = build_setup(count, batch_size)
        ids = [e.request_id for e in setup.examples]
        records = setup.plan_records(1, ids)
        planned = [rid for record in records for rid in record.request_ids]
        assert sorted(planned) == sorted(ids)
        assert all(len(record.request_ids) <= batch_size for record in records)

    @given(st.data(), st.integers(min_value=1, max_value=50))
    def test_plan_is_reproducible(self, data: st.DataObject, first: int) -> None:
        setup = data.draw(run_setups())
        ids = [e.request_id for e in setup.examples]
        assert setup.plan_records(first, ids) == setup.plan_records(first, ids)


class TestJudging:
    @pytest.fixture
    def planned(self) -> LoopState:
        return start_loop(build_setup(7)).with_judging_planned()

    def test_planning_twice_adds_nothing(self, planned: LoopState) -> None:
        assert planned.with_judging_planned() == planned

    def test_wrong_verdict_count_is_refused(self, planned: LoopState) -> None:
        record = planned.pending_judge_records[0]
        with pytest.raises(InvalidVerdictError):
            planned.with_verdicts(record.packet_id, [frozenset()] * 99)

    def test_unknown_packet_is_refused(self, planned: LoopState) -> None:
        with pytest.raises(PacketNotPendingError):
            planned.with_verdicts('j404-d0', [])

    def test_complete_baseline_moves_to_proposing(self, planned: LoopState) -> None:
        judged = judge_everything(planned)
        assert judged.stage is Stage.PROPOSING
        assert judged.judging is None
        assert judged.history.baseline == judged.history.accepted


class TestProposalCycle:
    @pytest.fixture
    def proposing(self) -> LoopState:
        return judge_everything(start_loop(build_setup(9))).with_proposal_assigned()

    def test_assignment_is_idempotent(self, proposing: LoopState) -> None:
        assert proposing.with_proposal_assigned() == proposing

    def test_proposal_starts_a_candidate_evaluation(self, proposing: LoopState) -> None:
        record = proposing.pending_proposal
        assert record is not None
        candidate = proposing.with_proposal(record.packet_id, 'Use for odd requests.')
        assert candidate.stage is Stage.JUDGING
        assert candidate.in_progress.tuned_skill == record.skill
        assert candidate.pending_proposal is None

    def test_rejected_round_is_recorded(self, proposing: LoopState) -> None:
        record = proposing.pending_proposal
        assert record is not None
        candidate = proposing.with_proposal(record.packet_id, 'Use for odd requests.')
        decided = judge_everything(candidate)
        assert len(decided.history.rounds) == 1
        assert decided.history.rounds[0].skill == record.skill


class TestCompetitors:
    def test_own_skill_names_are_excluded(self) -> None:
        state = start_loop(build_setup(3))
        updated = state.with_competitors(frozenset({'alpha', 'gamma', 'beta'}))
        assert updated.competitors == ('gamma',)

    def test_repeated_merges_accumulate_and_stay_sorted(self) -> None:
        state = start_loop(build_setup(3)).with_competitors(frozenset({'zeta'}))
        updated = state.with_competitors(frozenset({'mu', 'zeta', 'alpha'}))
        assert updated.competitors == ('mu', 'zeta')

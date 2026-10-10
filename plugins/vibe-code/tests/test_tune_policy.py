"""Run invariants: trigger sets, judge answers, and the acceptance rule."""

import msgspec
import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from vibe_code_cli.tune.domain.scoring import Scorecard, jaccard
from vibe_code_cli.tune.domain.values import (
    JudgeRecord,
    LoopOptions,
    RoutingOptions,
    Split,
    TriggerExample,
)
from vibe_code_cli.tune.errors import DuplicateRequestError, EmptySplitError, UnknownSkillError
from vibe_code_cli.tune.policy import (
    SKILL_NAME_CHARACTERS,
    AnswerPolicy,
    LoopOptionsPolicy,
    Proposal,
    ProposalPolicy,
    RoundPolicy,
    SkillPolicy,
    TriggerSetPolicy,
)
from vibe_code_cli.tune.tests.strategies import UNKNOWN_SKILLS, wrong_answer_keys


def example(request: str, skills: tuple[str, ...], split: Split) -> TriggerExample:
    return TriggerExample(
        request_id=request, request=request, expected=frozenset(skills), split=split
    )


class TestTriggerSetProblem:
    names = frozenset({'jira'})
    policy = TriggerSetPolicy()

    @pytest.mark.parametrize(
        ('examples', 'expected'),
        [
            pytest.param(
                (
                    example('a', ('nope',), Split.TRAIN),
                    example('b', (), Split.VALIDATION),
                ),
                UnknownSkillError,
                id='unknown-skill',
            ),
            pytest.param(
                (example('a', (), Split.TRAIN), example('a', (), Split.VALIDATION)),
                DuplicateRequestError,
                id='duplicate-request',
            ),
            pytest.param(
                (example('a', ('jira',), Split.TRAIN),),
                EmptySplitError,
                id='no-validation',
            ),
        ],
    )
    def test_violations_are_returned(
        self, examples: tuple[TriggerExample, ...], expected: type[Exception]
    ) -> None:
        problem = self.policy.get_trigger_set_problem(examples, self.names)
        assert isinstance(problem, expected)

    def test_valid_set_has_no_violation(self) -> None:
        examples = (
            example('a', ('jira',), Split.TRAIN),
            example('b', (), Split.VALIDATION),
        )
        assert self.policy.get_trigger_set_problem(examples, self.names) is None


class TestAnswerKeysProblem:
    sizes = st.integers(min_value=1, max_value=20)
    policy = AnswerPolicy()

    @given(sizes, st.data())
    def test_wrong_keys_are_refused(self, size: int, data: st.DataObject) -> None:
        keys = data.draw(wrong_answer_keys(size))
        violation = self.policy.get_answer_keys_problem('j1', keys, size)
        assert violation is not None
        assert 'keys' in str(violation)

    @given(st.integers(min_value=0, max_value=50))
    def test_exact_keys_pass(self, size: int) -> None:
        keys = [f'q{n}' for n in range(size, 0, -1)]
        assert self.policy.get_answer_keys_problem('j1', keys, size) is None


class TestVerdictProblem:
    record = JudgeRecord(packet_id='j1', request_ids=('r1', 'r2'), skill_order=('a', 'b'))
    policy = AnswerPolicy()
    known = st.frozensets(st.sampled_from(['a', 'b']))

    @given(st.lists(known, max_size=1) | st.lists(known, min_size=3, max_size=6))
    def test_wrong_verdict_count_is_refused(self, verdicts: list[frozenset[str]]) -> None:
        violation = self.policy.get_verdict_problem(self.record, verdicts)
        assert violation is not None
        assert 'expected 2' in str(violation)

    @given(
        st.lists(known, min_size=2, max_size=2),
        st.sampled_from(UNKNOWN_SKILLS),
        st.integers(min_value=0, max_value=1),
    )
    def test_stray_skill_is_refused(
        self, verdicts: list[frozenset[str]], stray: str, position: int
    ) -> None:
        verdicts[position] |= {stray}
        violation = self.policy.get_verdict_problem(self.record, verdicts)
        assert violation is not None
        assert 'unknown skill' in str(violation)

    @given(st.lists(known, min_size=2, max_size=2))
    def test_known_skills_pass(self, verdicts: list[frozenset[str]]) -> None:
        assert self.policy.get_verdict_problem(self.record, verdicts) is None


class TestSkillNames:
    policy = SkillPolicy()

    @given(st.from_regex(r'[a-z0-9][a-z0-9-]{0,30}', fullmatch=True))
    def test_lowercase_hyphenated_names_are_valid(self, name: str) -> None:
        assert self.policy.is_valid_skill_name(name)

    @given(st.text(min_size=1).filter(lambda s: not set(s) <= SKILL_NAME_CHARACTERS))
    def test_other_characters_are_invalid(self, name: str) -> None:
        assert not self.policy.is_valid_skill_name(name)


class TestProposalProblem:
    policy = ProposalPolicy()

    def proposal(
        self,
        text: str,
        *,
        current: str = 'Old.',
        when_to_use: str = '',
        rejected: tuple[str, ...] = (),
    ) -> Proposal:
        return Proposal(
            description=text, current=current, when_to_use=when_to_use, rejected=rejected
        )

    @given(st.from_regex(r'Use for [a-z ]{1,40}\.', fullmatch=True))
    def test_plain_new_text_passes(self, text: str) -> None:
        problem = self.policy.get_proposal_problem(self.proposal(text), LoopOptions())
        assert problem is None

    @given(st.text(min_size=1, max_size=60))
    def test_rejected_text_never_passes_twice(self, text: str) -> None:
        stripped = text.strip()
        proposal = self.proposal(text, rejected=(stripped,))
        violation = self.policy.get_proposal_problem(proposal, LoopOptions())
        assert violation is not None


class TestListingLimitProblem:
    policy = ProposalPolicy()
    description = 'Use for x.'
    when_to_use = 'Use this skill when the request mentions x.'

    def options_for_limit(self, limit: int) -> LoopOptions:
        return LoopOptions(max_listing_chars=limit, max_description_chars=1024)

    def proposal(self) -> Proposal:
        return Proposal(
            description=self.description,
            current='Old.',
            when_to_use=self.when_to_use,
            rejected=(),
        )

    def test_exactly_at_the_listing_limit_passes(self) -> None:
        limit = len(self.description) + len(self.when_to_use)
        assert (
            self.policy.get_proposal_problem(self.proposal(), self.options_for_limit(limit)) is None
        )

    def test_one_character_over_the_listing_limit_is_refused(self) -> None:
        limit = len(self.description) + len(self.when_to_use) - 1
        violation = self.policy.get_proposal_problem(self.proposal(), self.options_for_limit(limit))
        assert violation is not None
        assert 'listing limit' in str(violation)


class TestCandidateWins:
    options = LoopOptions()
    policy = RoundPolicy()
    unit = st.floats(min_value=0.0, max_value=1.0)
    scorecards = st.builds(Scorecard, train=unit, validation=unit)
    gain_options = st.builds(LoopOptions, min_gain=st.floats(min_value=0.0, max_value=0.5))

    @pytest.mark.parametrize(
        ('current', 'candidate', 'wins'),
        [
            pytest.param((0.5, 0.5), (0.4, 0.6), True, id='validation-gain-wins'),
            pytest.param((0.5, 0.5), (0.9, 0.4), False, id='validation-loss-loses'),
            pytest.param((0.5, 0.5), (0.6, 0.5), True, id='tie-broken-by-train'),
            pytest.param((0.5, 0.5), (0.5, 0.5), False, id='no-change-loses'),
        ],
    )
    def test_acceptance_rule(
        self,
        current: tuple[float, float],
        candidate: tuple[float, float],
        wins: bool,
    ) -> None:
        before = Scorecard(train=current[0], validation=current[1])
        after = Scorecard(train=candidate[0], validation=candidate[1])
        assert self.policy.is_winning_candidate(before, after, self.options) is wins

    @given(current=scorecards, winner=scorecards, other=scorecards, options=gain_options)
    def test_dominating_a_winner_also_wins(
        self,
        *,
        current: Scorecard,
        winner: Scorecard,
        other: Scorecard,
        options: LoopOptions,
    ) -> None:
        assume(self.policy.is_winning_candidate(current, winner, options))
        dominating = Scorecard(
            train=max(winner.train, other.train),
            validation=max(winner.validation, other.validation),
        )
        assert self.policy.is_winning_candidate(current, dominating, options)

    @given(scorecards, scorecards, gain_options)
    def test_lower_validation_never_wins(
        self, current: Scorecard, candidate: Scorecard, options: LoopOptions
    ) -> None:
        assume(candidate.validation < current.validation)
        assert not self.policy.is_winning_candidate(current, candidate, options)


class TestJaccard:
    sets = st.frozensets(st.sampled_from('abcdef'))

    @given(sets, sets)
    def test_score_is_symmetric_and_bounded(
        self, expected: frozenset[str], chosen: frozenset[str]
    ) -> None:
        score = jaccard(expected, chosen)
        assert 0.0 <= score <= 1.0
        assert score == jaccard(chosen, expected)
        assert (score == 1.0) is (expected == chosen)

    @pytest.mark.parametrize(
        ('expected', 'chosen', 'score'),
        [
            pytest.param(frozenset(), frozenset(), 1.0, id='correct-abstain'),
            pytest.param(frozenset({'a'}), frozenset(), 0.0, id='miss'),
            pytest.param(frozenset({'a'}), frozenset({'a', 'b'}), 0.5, id='extra'),
        ],
    )
    def test_scores(self, expected: frozenset[str], chosen: frozenset[str], score: float) -> None:
        assert jaccard(expected, chosen) == pytest.approx(score)


class TestOptionsProblem:
    policy = LoopOptionsPolicy()

    @pytest.mark.parametrize(
        ('changes', 'flag'),
        [
            pytest.param({'batch_size': 0}, '--batch-size', id='no-batch'),
            pytest.param({'max_rounds': 0}, '--max-rounds', id='no-rounds'),
            pytest.param({'patience': 0}, '--patience', id='no-patience'),
            pytest.param({'validation_fraction': 1.0}, '--validation-fraction', id='all-held-out'),
            pytest.param(
                {'routing': RoutingOptions(concurrency=0)},
                '--concurrency',
                id='no-workers',
            ),
        ],
    )
    def test_degenerate_options_are_refused(self, changes: dict[str, object], flag: str) -> None:
        options = msgspec.structs.replace(LoopOptions(), **changes)
        violation = self.policy.get_options_problem(options)
        assert violation is not None
        assert flag in str(violation)

    def test_defaults_pass(self) -> None:
        assert self.policy.get_options_problem(LoopOptions()) is None

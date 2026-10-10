"""Laws of scoring a complete set of verdicts and listing a skill's training failures."""

from hypothesis import given
from hypothesis import strategies as st
from vibe_code_cli.tune.domain.scoring import (
    Scorecard,
    SkillFailures,
    score_verdicts,
    skill_failures,
)
from vibe_code_cli.tune.domain.state import RunSetup
from vibe_code_cli.tune.domain.values import Split
from vibe_code_cli.tune.tests.strategies import run_setups, verdicts_for


class TestScoreVerdicts:
    @given(st.data())
    def test_scores_stay_between_zero_and_one(self, data: st.DataObject) -> None:
        setup = data.draw(run_setups())
        card = score_verdicts(setup.examples, data.draw(verdicts_for(setup)))
        assert 0.0 <= card.train <= 1.0
        assert 0.0 <= card.validation <= 1.0

    @given(st.data())
    def test_expected_verdicts_score_perfectly(self, data: st.DataObject) -> None:
        examples = data.draw(run_setups()).examples
        perfect = {example.request_id: example.expected for example in examples}
        assert score_verdicts(examples, perfect) == Scorecard(train=1.0, validation=1.0)


class TestSkillFailures:
    def draw_failures(self, data: st.DataObject) -> tuple[RunSetup, SkillFailures]:
        setup = data.draw(run_setups())
        verdicts = data.draw(verdicts_for(setup))
        skill = data.draw(st.sampled_from(sorted(setup.skill_names)))
        return setup, skill_failures(setup.examples, verdicts, skill)

    @given(st.data())
    def test_failures_are_disjoint_training_requests(self, data: st.DataObject) -> None:
        setup, failures = self.draw_failures(data)
        train = {e.request for e in setup.examples if e.split is Split.TRAIN}
        assert not set(failures.missed) & set(failures.false_triggers)
        assert {*failures.missed, *failures.false_triggers} <= train

    @given(st.data())
    def test_f1_is_perfect_exactly_when_nothing_failed(self, data: st.DataObject) -> None:
        _setup, failures = self.draw_failures(data)
        assert 0.0 <= failures.f1 <= 1.0
        assert (failures.f1 == 1.0) is (failures.count == 0)

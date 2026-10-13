"""Laws of decoding a judge answer, and of the listing text shown to a judge or proposer."""

from collections.abc import Sequence

import msgspec
import pytest
from hypothesis import given
from hypothesis import strategies as st
from vibe_code_cli.tune.domain.state import RunSetup, start_loop
from vibe_code_cli.tune.domain.values import LoopOptions, Skill, Split, TriggerExample
from vibe_code_cli.tune.errors import MalformedAnswerError
from vibe_code_cli.tune.schemas import (
    judge_packet,
    listing_text,
    propose_packet,
    verdicts_from_answer,
)
from vibe_code_cli.tune.tests.strategies import JudgeAnswer, broken_json

SKILL_WITH_USAGE = Skill(
    name='alpha',
    path='/alpha/SKILL.md',
    description='Use for alpha work.',
    when_to_use='When the user mentions alpha.',
)
SKILL_WITHOUT_USAGE = Skill(name='beta', path='/beta/SKILL.md', description='Use for beta work.')


class TestVerdictsFromAnswer:
    rows = st.lists(st.frozensets(st.text(max_size=12)), min_size=1, max_size=12)

    def answer_for(self, rows: Sequence[frozenset[str]]) -> JudgeAnswer:
        return {f'q{index}': sorted(row) for index, row in enumerate(rows, start=1)}

    @given(rows)
    def test_encoded_verdicts_round_trip(self, rows: list[frozenset[str]]) -> None:
        encoded = msgspec.json.encode(self.answer_for(rows))
        assert verdicts_from_answer('j1', encoded, len(rows)) == tuple(rows)

    @given(st.data())
    def test_broken_json_is_a_malformed_answer(self, data: st.DataObject) -> None:
        rows = data.draw(self.rows)
        broken = data.draw(broken_json(self.answer_for(rows)))
        with pytest.raises(MalformedAnswerError):
            verdicts_from_answer('j1', broken, len(rows))


class TestListingText:
    def test_without_when_to_use_the_listing_is_the_description(self) -> None:
        assert listing_text('Use for alpha work.', '') == 'Use for alpha work.'

    def test_with_when_to_use_the_listing_appends_it_on_a_new_line(self) -> None:
        text = listing_text('Use for alpha work.', 'When the user mentions alpha.')
        assert text == 'Use for alpha work.\nWhen the user mentions alpha.'


class TestPacketListings:
    setup = RunSetup(
        run_id='s0',
        skills=(SKILL_WITH_USAGE, SKILL_WITHOUT_USAGE),
        examples=(
            TriggerExample(
                request_id='r1',
                request='alpha please',
                expected=frozenset({'alpha'}),
                split=Split.TRAIN,
            ),
            TriggerExample(
                request_id='r2',
                request='beta please',
                expected=frozenset({'beta'}),
                split=Split.VALIDATION,
            ),
        ),
        options=LoopOptions(batch_size=5),
    )

    def test_judge_packet_shows_when_to_use_below_the_description(self) -> None:
        state = start_loop(self.setup).with_judging_planned()
        assert state.judging is not None
        packet = judge_packet(state.judging.pending[0], state)
        assert packet.skills['alpha'] == 'Use for alpha work.\nWhen the user mentions alpha.'
        assert packet.skills['beta'] == 'Use for beta work.'

    def test_propose_packet_carries_the_skills_when_to_use(self) -> None:
        wrong_verdicts = {'r1': frozenset(), 'r2': frozenset({'beta'})}
        baseline = start_loop(self.setup).with_judging_planned()
        assert baseline.judging is not None
        record = baseline.judging.pending[0]
        verdicts = [wrong_verdicts[request_id] for request_id in record.request_ids]
        judged = baseline.with_verdicts(record.packet_id, verdicts)
        assigned = judged.with_proposal_assigned()

        packet = propose_packet(assigned, ())

        assert packet is not None
        assert packet.skill == 'alpha'
        assert packet.when_to_use == 'When the user mentions alpha.'

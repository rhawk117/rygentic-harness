"""A finding's location read as one span: what submission refuses and what the merge overlaps."""

import pytest
from mightymodels_plugin.tools.review.errors import (
    FindingError,
    LineBelowOneError,
    LocationShapeError,
    ReversedRangeError,
)
from mightymodels_plugin.tools.review.finding_merge import normalized, overlaps
from mightymodels_plugin.tools.review.schema import Finding, FindingInput, Kind, Severity

SECOND_IN_THE_BATCH = 1


def submitted(location: str) -> FindingInput:
    return FindingInput.model_validate(
        {
            'sources': ['UB-1'],
            'severity': 'Low',
            'title': 'a title',
            'location': location,
            'fix': 'a fix',
            'verify': 'a check',
        }
    )


def recorded(location: str) -> Finding:
    return Finding(
        id='F1',
        sources=('UB-1',),
        severity=Severity.LOW,
        kind=Kind.DEFECT,
        security=False,
        title='a title',
        location=location,
        fix='a fix',
        verify='a check',
    )


class TestSubmission:
    REFUSED = 'finding 1: {problem} (UB-1); nothing was written'
    BELOW_ONE = 'location line 0 is below 1'
    REVERSED = 'location range 9-3 ends before it starts'
    NO_SHAPE = 'location must be path:line or path:start-end'

    @pytest.mark.parametrize(
        ('location', 'refusal', 'problem'),
        [
            pytest.param('src/q.py:0', LineBelowOneError, BELOW_ONE, id='line-zero'),
            pytest.param('src/q.py:0-3', LineBelowOneError, BELOW_ONE, id='range-from-zero'),
            pytest.param('src/q.py:3-0', LineBelowOneError, BELOW_ONE, id='range-to-zero'),
            pytest.param('src/q.py:9-3', ReversedRangeError, REVERSED, id='reversed-range'),
            pytest.param('nowhere', LocationShapeError, NO_SHAPE, id='no-line'),
        ],
    )
    def test_a_location_that_is_not_a_span_is_refused(
        self, location: str, refusal: type[FindingError], problem: str
    ) -> None:
        with pytest.raises(FindingError) as raised:
            normalized(submitted(location), SECOND_IN_THE_BATCH)

        assert type(raised.value) is refusal
        assert str(raised.value) == self.REFUSED.format(problem=problem)

    @pytest.mark.parametrize(
        'location',
        [
            pytest.param('src/q.py:1', id='single-line'),
            pytest.param('src/q.py:3-9', id='ordered-range'),
            pytest.param('src/q.py:4-4', id='one-line-range'),
        ],
    )
    def test_a_span_is_accepted_as_it_was_written(self, location: str) -> None:
        assert normalized(submitted(location), SECOND_IN_THE_BATCH).location == location


class TestOverlap:
    @pytest.mark.parametrize(
        ('recorded_at', 'incoming_at', 'overlapping'),
        [
            pytest.param('src/q.py:3-9', 'src/q.py:9-12', True, id='ranges-sharing-a-line'),
            pytest.param('src/q.py:3-9', 'src/q.py:4', True, id='line-inside-a-range'),
            pytest.param('src/q.py:3-9', 'src/q.py:10-12', False, id='disjoint-ranges'),
            pytest.param('src/q.py:3-9', 'src/r.py:3-9', False, id='same-lines-on-different-files'),
        ],
    )
    def test_two_findings_overlap_where_their_spans_share_a_line_of_one_file(
        self, recorded_at: str, incoming_at: str, overlapping: bool
    ) -> None:
        assert overlaps(recorded(recorded_at), recorded(incoming_at)) is overlapping

    @pytest.mark.parametrize(
        ('recorded_at', 'incoming_at'),
        [
            pytest.param('nowhere', 'src/q.py:3-9', id='recorded-side'),
            pytest.param('src/q.py:3-9', 'nowhere', id='incoming-side'),
            pytest.param('nowhere', 'nowhere', id='both-sides-the-same-text'),
        ],
    )
    def test_a_stored_location_that_does_not_parse_overlaps_nothing(
        self, recorded_at: str, incoming_at: str
    ) -> None:
        assert not overlaps(recorded(recorded_at), recorded(incoming_at))

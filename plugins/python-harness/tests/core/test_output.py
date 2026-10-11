"""JSON documents from dataclasses, enums, paths and collections."""

import io
import json
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path
from types import MappingProxyType

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from python_harness.core.output import (
    DEFAULT_BUDGET,
    MINIMUM_BUDGET,
    Detail,
    InvalidOutputBudgetError,
    OutputOptions,
    OutputViews,
    UnsupportedJsonValueError,
    estimate_tokens,
    fit_ranked_prefix,
    output_options,
    output_view,
    render_budgeted_document,
    to_json_value,
    write_document,
)
from python_harness.server import tool_errors


class Colour(StrEnum):
    RED = auto()
    BLUE = auto()


@dataclass(frozen=True, slots=True)
class Leaf:
    path: Path
    colours: frozenset[Colour]


@dataclass(frozen=True, slots=True)
class Branch:
    name: str
    leaves: tuple[Leaf, ...]
    _hidden: int = 0

    @property
    def leaf_count(self) -> int:
        return len(self.leaves)

    @property
    def _secret(self) -> int:
        return self._hidden


class TestToJsonValue:
    BRANCH = Branch('trunk', (Leaf(Path('a/b.py'), frozenset({Colour.RED, Colour.BLUE})),))
    EXPECTED = MappingProxyType(
        {
            'name': 'trunk',
            'leaves': [{'path': 'a/b.py', 'colours': ['blue', 'red']}],
            'leaf_count': 1,
        }
    )
    COMPACT = (
        '{"name":"trunk","leaves":[{"path":"a/b.py","colours":["blue","red"]}],"leaf_count":1}\n'
    )

    def test_dataclass_document_has_public_fields_and_properties(self) -> None:
        assert to_json_value(self.BRANCH) == self.EXPECTED

    @pytest.mark.parametrize(
        'value',
        [pytest.param(object(), id='plain-object'), pytest.param(Branch, id='class')],
    )
    def test_unsupported_values_are_rejected(self, value: object) -> None:
        with pytest.raises(UnsupportedJsonValueError):
            to_json_value(value)

    def test_write_document_emits_parseable_json(self) -> None:
        stream = io.StringIO()

        write_document(self.BRANCH, stream)

        assert json.loads(stream.getvalue()) == self.EXPECTED

    def test_write_document_is_compact_with_a_trailing_newline(self) -> None:
        stream = io.StringIO()

        write_document(self.BRANCH, stream)

        assert stream.getvalue() == self.COMPACT


def render_prefix(items: tuple[str, ...]) -> str:
    return json.dumps(items, separators=(',', ':'))


def output_views(full: object, summary: object, counts: object) -> OutputViews:
    return OutputViews(
        full=output_view(full),
        summary=output_view(summary),
        counts=output_view(counts),
    )


class TestBudgetedOutput:
    def test_options_have_the_shared_defaults_and_minimum(self) -> None:
        options = output_options()

        assert options == OutputOptions(detail=Detail.SUMMARY, budget=DEFAULT_BUDGET)
        with pytest.raises(InvalidOutputBudgetError):
            output_options(budget=MINIMUM_BUDGET - 1)

    @pytest.mark.parametrize(
        ('text', 'lexical_units', 'characters'),
        [
            pytest.param('name!', 2, 5, id='punctuation'),
            pytest.param('one two', 2, 7, id='whitespace'),
            pytest.param('abcdefghij', 1, 10, id='character-bound'),
        ],
    )
    def test_estimator_uses_the_larger_native_measure(
        self, text: str, lexical_units: int, characters: int
    ) -> None:
        assert estimate_tokens(text) == max(lexical_units, (characters + 3) // 4)

    def test_envelope_tokens_are_self_inclusive_at_digit_boundaries(self) -> None:
        for size in range(80, 160):
            rendered = render_budgeted_document(
                options=output_options(budget=MINIMUM_BUDGET),
                workspace={},
                views=output_views(
                    {'result': {'value': 'x' * size}},
                    {'result': {'value': 'x' * size}},
                    {'result': {'count': 1}},
                ),
            )
            document = json.loads(rendered)
            assert document['tokens'] == estimate_tokens(rendered)

    def test_full_summary_counts_degradation_is_explicit(self) -> None:
        rendered = render_budgeted_document(
            options=output_options(detail=Detail.FULL, budget=MINIMUM_BUDGET),
            workspace={},
            views=output_views(
                {'result': {'value': 'x' * 5000}},
                {'result': {'value': 'x' * 2000}},
                {'result': {'count': 1}},
            ),
        )

        document = json.loads(rendered)
        assert (document['detail'], document['degraded'], document['truncated']) == (
            'counts',
            True,
            True,
        )
        assert document['tokens'] <= MINIMUM_BUDGET

    def test_requested_summary_is_truncated_only_when_it_does_not_fit(self) -> None:
        complete = render_budgeted_document(
            options=output_options(budget=MINIMUM_BUDGET),
            workspace={},
            views=output_views('full', 'summary', {'count': 1}),
        )
        truncated = render_budgeted_document(
            options=output_options(budget=MINIMUM_BUDGET),
            workspace={},
            views=output_views('full', 'x' * 5000, {'count': 1}),
        )

        assert json.loads(complete)['truncated'] is False
        assert json.loads(truncated)['truncated'] is True

    def test_envelope_carries_exactly_its_seven_keys(self) -> None:
        rendered = render_budgeted_document(
            options=output_options(budget=MINIMUM_BUDGET),
            workspace={'source_roots': ['src']},
            views=output_views('full', 'summary', {'count': 1}),
        )

        assert json.loads(rendered) == {
            'detail': 'summary',
            'budget': MINIMUM_BUDGET,
            'tokens': estimate_tokens(rendered),
            'truncated': False,
            'degraded': False,
            'result': 'summary',
            'workspace': {'source_roots': ['src']},
        }

    @pytest.mark.parametrize(
        ('requested', 'sizes', 'expected'),
        [
            pytest.param(Detail.FULL, (10, 10, 1), 'full', id='full-fits'),
            pytest.param(Detail.FULL, (5000, 10, 1), 'summary', id='full-steps-down-to-summary'),
            pytest.param(Detail.FULL, (5000, 5000, 1), 'counts', id='summary-steps-down-to-counts'),
            pytest.param(Detail.SUMMARY, (10, 5000, 1), 'counts', id='summary-skips-full'),
        ],
    )
    def test_a_step_down_the_ladder_sets_degraded_and_truncated(
        self, requested: Detail, sizes: tuple[int, int, int], expected: str
    ) -> None:
        full, summary, counts = sizes
        rendered = render_budgeted_document(
            options=output_options(detail=requested, budget=MINIMUM_BUDGET),
            workspace={},
            views=output_views('x' * full, 'x' * summary, 'x' * counts),
        )

        document = json.loads(rendered)
        stepped_down = document['detail'] != requested
        assert (document['detail'], document['degraded'], document['truncated']) == (
            expected,
            stepped_down,
            stepped_down,
        )

    def test_largest_ranked_prefix_is_stable(self) -> None:
        items = ('first', 'second', 'third')
        prefix, truncated = fit_ranked_prefix(items, budget=5, render=render_prefix)

        assert (prefix, truncated) == (('first',), True)

    def test_counts_envelope_fits_at_minimum_budget(self) -> None:
        rendered = render_budgeted_document(
            options=output_options(detail=Detail.COUNTS, budget=MINIMUM_BUDGET),
            workspace={},
            views=output_views('unused', 'unused', {'count': 1}),
        )

        document = json.loads(rendered)
        assert document['detail'] == 'counts'
        assert document['tokens'] <= MINIMUM_BUDGET


class TestBudgetErrors:
    def test_a_budget_under_the_minimum_is_a_tool_error(self) -> None:
        options = OutputOptions(detail=Detail.FULL, budget=MINIMUM_BUDGET - 1)

        with pytest.raises(ToolError, match='at least 256 tokens'), tool_errors():
            render_budgeted_document(
                options=options, workspace={}, views=output_views('a', 'b', 'c')
            )

    def test_a_counts_document_over_budget_is_a_tool_error(self) -> None:
        with pytest.raises(ToolError, match='does not fit within 256 tokens'), tool_errors():
            render_budgeted_document(
                options=output_options(detail=Detail.COUNTS, budget=MINIMUM_BUDGET),
                workspace={},
                views=output_views('a', 'b', 'x' * 5000),
            )

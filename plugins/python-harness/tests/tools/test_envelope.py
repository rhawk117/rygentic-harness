"""The budgeted response envelope: options, token estimates and the step-down ladder."""

import json
from collections.abc import Callable
from functools import partial
from itertools import count

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from python_harness.server import tool_errors
from python_harness.tools import envelope
from python_harness.tools.envelope import (
    DEFAULT_BUDGET,
    MINIMUM_BUDGET,
    Detail,
    InvalidOutputBudgetError,
    OutputOptions,
    OutputView,
    OutputViews,
    estimate_tokens,
    output_view,
    render_budgeted_document,
)


def output_views(full: object, summary: object, counts: object) -> OutputViews:
    return OutputViews(
        full=partial(output_view, full),
        summary=partial(output_view, summary),
        counts=partial(output_view, counts),
    )


class TestBudgetedOutput:
    def test_options_have_the_shared_defaults_and_minimum(self) -> None:
        options = OutputOptions()

        assert options == OutputOptions(detail=Detail.SUMMARY, budget=DEFAULT_BUDGET)
        with pytest.raises(InvalidOutputBudgetError):
            OutputOptions(budget=MINIMUM_BUDGET - 1)

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
                options=OutputOptions(budget=MINIMUM_BUDGET),
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
            options=OutputOptions(detail=Detail.FULL, budget=MINIMUM_BUDGET),
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
            options=OutputOptions(budget=MINIMUM_BUDGET),
            workspace={},
            views=output_views('full', 'summary', {'count': 1}),
        )
        truncated = render_budgeted_document(
            options=OutputOptions(budget=MINIMUM_BUDGET),
            workspace={},
            views=output_views('full', 'x' * 5000, {'count': 1}),
        )

        assert json.loads(complete)['truncated'] is False
        assert json.loads(truncated)['truncated'] is True

    def test_envelope_carries_exactly_its_seven_keys(self) -> None:
        rendered = render_budgeted_document(
            options=OutputOptions(budget=MINIMUM_BUDGET),
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
            options=OutputOptions(detail=requested, budget=MINIMUM_BUDGET),
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

    def test_a_view_is_built_only_when_its_detail_level_is_tried(self) -> None:
        tried: list[Detail] = []

        def view_of(detail: Detail) -> Callable[[], OutputView]:
            def build() -> OutputView:
                tried.append(detail)
                return output_view(detail.value)

            return build

        render_budgeted_document(
            options=OutputOptions(detail=Detail.SUMMARY, budget=MINIMUM_BUDGET),
            workspace={},
            views=OutputViews(
                full=view_of(Detail.FULL),
                summary=view_of(Detail.SUMMARY),
                counts=view_of(Detail.COUNTS),
            ),
        )

        assert tried == [Detail.SUMMARY]

    def test_counts_envelope_fits_at_minimum_budget(self) -> None:
        rendered = render_budgeted_document(
            options=OutputOptions(detail=Detail.COUNTS, budget=MINIMUM_BUDGET),
            workspace={},
            views=output_views('unused', 'unused', {'count': 1}),
        )

        document = json.loads(rendered)
        assert document['detail'] == 'counts'
        assert document['tokens'] <= MINIMUM_BUDGET


class TestBudgetErrors:
    def test_a_budget_under_the_minimum_is_a_tool_error(self) -> None:
        with pytest.raises(ToolError, match='at least 256 tokens'), tool_errors():
            OutputOptions(detail=Detail.FULL, budget=MINIMUM_BUDGET - 1)

    def test_an_estimate_that_never_settles_is_a_tool_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        counter = count(1)
        monkeypatch.setattr(envelope, 'estimate_tokens', lambda _: next(counter))

        with pytest.raises(ToolError, match='did not stabilize'), tool_errors():
            render_budgeted_document(
                options=OutputOptions(budget=MINIMUM_BUDGET),
                workspace={},
                views=output_views('a', 'b', 'c'),
            )

    def test_a_counts_document_over_budget_is_a_tool_error(self) -> None:
        with pytest.raises(ToolError, match='does not fit within 256 tokens'), tool_errors():
            render_budgeted_document(
                options=OutputOptions(detail=Detail.COUNTS, budget=MINIMUM_BUDGET),
                workspace={},
                views=output_views('a', 'b', 'x' * 5000),
            )

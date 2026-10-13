"""The budgeted response envelope around a project tool's document."""

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum, auto
from functools import partial
from typing import Annotated

from pydantic import Field

from python_harness.core.errors import PythonHarnessError
from python_harness.core.output import COMPACT_SEPARATORS, JsonValue, to_json_value

DEFAULT_BUDGET = 4000
MINIMUM_BUDGET = 256
TOKEN_ESTIMATE_PASS_LIMIT = 32


class Detail(StrEnum):
    FULL = auto()
    SUMMARY = auto()
    COUNTS = auto()


type DetailLevel = Annotated[
    Detail,
    Field(
        description=(
            'How much of the report to return: full is every fact or reference for the'
            ' requested paths, summary is the totals and the highest-ranked modules, counts is'
            ' the totals only. A response that does not fit the budget steps down from full to'
            ' summary to counts.'
        )
    ),
]
type Budget = Annotated[
    int,
    Field(
        ge=MINIMUM_BUDGET,
        description=(
            f'Estimated response size in tokens, at least {MINIMUM_BUDGET}. The tool steps'
            ' down to a smaller detail level to stay within it.'
        ),
    ),
]


class InvalidOutputBudgetError(PythonHarnessError):
    def __init__(self, budget: int) -> None:
        super().__init__(f'output budget must be at least {MINIMUM_BUDGET} tokens')
        self.budget = budget
        self.minimum = MINIMUM_BUDGET


class OutputBudgetExceededError(PythonHarnessError):
    def __init__(self, budget: int) -> None:
        super().__init__(f'counts response does not fit within {budget} tokens')
        self.budget = budget


class UnstableTokenEstimateError(PythonHarnessError):
    def __init__(self) -> None:
        super().__init__('output token estimate did not stabilize')


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputOptions:
    detail: Detail = Detail.SUMMARY
    budget: int = DEFAULT_BUDGET

    def __post_init__(self) -> None:
        if self.budget < MINIMUM_BUDGET:
            raise InvalidOutputBudgetError(self.budget)


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputView:
    result: object
    truncated: bool = False


type ViewBuilder = Callable[[], OutputView]


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputViews:
    full: ViewBuilder
    summary: ViewBuilder
    counts: ViewBuilder

    def for_detail(self, detail: Detail) -> ViewBuilder:
        return {
            Detail.FULL: self.full,
            Detail.SUMMARY: self.summary,
            Detail.COUNTS: self.counts,
        }[detail]


@dataclass(frozen=True, slots=True, kw_only=True)
class ResponseEnvelope:
    detail: Detail
    budget: int
    tokens: int
    truncated: bool
    degraded: bool
    result: object
    workspace: object


def estimate_tokens(text: str) -> int:
    lexical_units = 0
    in_word = False
    for character in text:
        if character.isalnum() or character == '_':
            if not in_word:
                lexical_units += 1
                in_word = True
        else:
            in_word = False
            if not character.isspace():
                lexical_units += 1
    return max(lexical_units, (len(text) + 3) // 4)


def output_view(result: object, *, truncated: bool = False) -> OutputView:
    return OutputView(result=result, truncated=truncated)


def compact_json(value: object) -> str:
    return json.dumps(to_json_value(value), separators=COMPACT_SEPARATORS)


def render_envelope(envelope: ResponseEnvelope) -> tuple[str, int]:
    candidate = envelope
    for _ in range(TOKEN_ESTIMATE_PASS_LIMIT):
        text = compact_json(candidate)
        updated = estimate_tokens(text)
        if updated == candidate.tokens:
            return text, updated
        candidate = replace(candidate, tokens=updated)
    raise UnstableTokenEstimateError


def detail_ladder(requested: Detail) -> tuple[Detail, ...]:
    ladder = (Detail.FULL, Detail.SUMMARY, Detail.COUNTS)
    return ladder[ladder.index(requested) :]


def render_budgeted_document(
    *,
    options: OutputOptions,
    workspace: object,
    views: OutputViews,
) -> str:
    for detail in detail_ladder(options.detail):
        view = views.for_detail(detail)()
        degraded = detail != options.detail
        text, tokens = render_envelope(
            ResponseEnvelope(
                detail=detail,
                budget=options.budget,
                tokens=0,
                truncated=view.truncated or degraded,
                degraded=degraded,
                result=view.result,
                workspace=workspace,
            )
        )
        if tokens <= options.budget:
            return text
    raise OutputBudgetExceededError(options.budget)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectOutput[ReportT]:
    options: OutputOptions
    summary: Callable[[ReportT], OutputView]
    counts: Callable[[ReportT], object]

    def counts_view(self, report: ReportT) -> OutputView:
        return output_view(self.counts(report))


def render_budgeted_project_document[ReportT](
    report: ReportT, diagnostics: dict[str, JsonValue], output: ProjectOutput[ReportT]
) -> str:
    return render_budgeted_document(
        options=output.options,
        workspace=diagnostics,
        views=OutputViews(
            full=partial(output_view, report),
            summary=partial(output.summary, report),
            counts=partial(output.counts_view, report),
        ),
    )

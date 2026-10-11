"""The budgeted response envelope around a project tool's document."""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum, auto

from python_harness.core.errors import PythonHarnessError
from python_harness.core.output import COMPACT_SEPARATORS, JsonValue, to_json_value

DEFAULT_BUDGET = 4000
MINIMUM_BUDGET = 256


class Detail(StrEnum):
    FULL = auto()
    SUMMARY = auto()
    COUNTS = auto()


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputOptions:
    detail: Detail = Detail.SUMMARY
    budget: int = DEFAULT_BUDGET


class InvalidOutputBudgetError(PythonHarnessError):
    def __init__(self, budget: int) -> None:
        super().__init__(f'output budget must be at least {MINIMUM_BUDGET} tokens')
        self.budget = budget
        self.minimum = MINIMUM_BUDGET


class OutputBudgetExceededError(PythonHarnessError):
    def __init__(self, budget: int) -> None:
        super().__init__(f'counts response does not fit within {budget} tokens')
        self.budget = budget


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputView:
    result: object
    truncated: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputViews:
    full: OutputView
    summary: OutputView
    counts: OutputView

    def for_detail(self, detail: Detail) -> OutputView:
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


def output_options(
    *, detail: Detail = Detail.SUMMARY, budget: int = DEFAULT_BUDGET
) -> OutputOptions:
    options = OutputOptions(detail=Detail(detail), budget=budget)
    if violation := output_options_violation(options):
        raise violation
    return options


def output_options_violation(options: OutputOptions) -> InvalidOutputBudgetError | None:
    if options.budget < MINIMUM_BUDGET:
        return InvalidOutputBudgetError(options.budget)
    return None


def output_view(result: object, *, truncated: bool = False) -> OutputView:
    return OutputView(result=result, truncated=truncated)


def compact_json(value: object) -> str:
    return json.dumps(to_json_value(value), separators=COMPACT_SEPARATORS)


def render_envelope(envelope: ResponseEnvelope) -> tuple[str, int]:
    candidate = envelope
    for _ in range(32):
        text = compact_json(candidate)
        updated = estimate_tokens(text)
        if updated == candidate.tokens:
            return text, updated
        candidate = replace(candidate, tokens=updated)
    msg = 'output token estimate did not stabilize'
    raise RuntimeError(msg)


def detail_ladder(requested: Detail) -> tuple[Detail, ...]:
    ladder = (Detail.FULL, Detail.SUMMARY, Detail.COUNTS)
    return ladder[ladder.index(requested) :]


def render_budgeted_document(
    *,
    options: OutputOptions,
    workspace: object,
    views: OutputViews,
) -> str:
    if violation := output_options_violation(options):
        raise violation

    requested = Detail(options.detail)
    for detail in detail_ladder(requested):
        view = views.for_detail(detail)
        degraded = detail != requested
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


def fit_ranked_prefix[T](
    items: Sequence[T],
    *,
    budget: int,
    render: Callable[[tuple[T, ...]], str],
) -> tuple[tuple[T, ...], bool]:
    low = 0
    high = len(items) + 1
    while low + 1 < high:
        midpoint = (low + high) // 2
        candidate = tuple(items[:midpoint])
        if estimate_tokens(render(candidate)) <= budget:
            low = midpoint
        else:
            high = midpoint
    prefix = tuple(items[:low])
    return prefix, low < len(items)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectOutput[ReportT]:
    options: OutputOptions
    summary: Callable[[ReportT], object]
    counts: Callable[[ReportT], object]
    summary_truncated: Callable[[ReportT], bool]

    def summary_view(self, report: ReportT) -> OutputView:
        return output_view(self.summary(report), truncated=self.summary_truncated(report))

    def counts_view(self, report: ReportT) -> OutputView:
        return output_view(self.counts(report))


def render_budgeted_project_document[ReportT](
    report: ReportT, diagnostics: dict[str, JsonValue], output: ProjectOutput[ReportT]
) -> str:
    return render_budgeted_document(
        options=output.options,
        workspace=diagnostics,
        views=OutputViews(
            full=output_view(report),
            summary=output.summary_view(report),
            counts=output.counts_view(report),
        ),
    )

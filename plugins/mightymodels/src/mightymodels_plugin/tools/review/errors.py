"""Every failure the review service reports, one class each."""

from collections.abc import Sequence

from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.tools.review.schema import Decision, Persona, Result, ReviewScope


class WeightRangeError(StateError):
    def __init__(self) -> None:
        super().__init__('weights: give both personas a weight between 0 and 1')


class WeightSumError(StateError):
    def __init__(self) -> None:
        super().__init__('weights: the weights must sum to 1')


class WeightsMissingError(StateError):
    def __init__(self) -> None:
        super().__init__('weights: custom emphasis needs weights')


class PersonaChoiceError(StateError):
    def __init__(self) -> None:
        super().__init__('quick depth runs one persona and the weights tie; pass persona')


class BaseRequiredError(StateError):
    def __init__(self, scope: ReviewScope) -> None:
        super().__init__(f'{scope} scope needs base, the ref it is reviewed against')
        self.scope = scope


class SlugRequiredError(StateError):
    def __init__(self) -> None:
        super().__init__('ticket scope needs slug')


class RunNotFoundError(StateError):
    def __init__(self, run: RunId) -> None:
        super().__init__(f'no review run {run!s}; start one first')
        self.run = run


class RunExistsError(StateError):
    def __init__(self, run: RunId) -> None:
        super().__init__(f'review run {run!s} already exists; start again in a second')
        self.run = run


class OverrideSpentError(StateError):
    def __init__(self, run: RunId) -> None:
        super().__init__(f'review run {run!s} has used its one reviewer override')
        self.run = run


class ReportMissingError(StateError):
    def __init__(self, persona: Persona, relative: str) -> None:
        super().__init__(f'no {persona} report at {relative}; the reviewer writes it there first')
        self.persona = persona
        self.relative = relative


class ReportError(StateError):
    def __init__(self, problem: str) -> None:
        super().__init__(f'report: {problem}; nothing was written')
        self.problem = problem


class NoFindingsSectionError(ReportError):
    def __init__(self) -> None:
        super().__init__('there is no "## Findings" section')


class UnknownSeverityHeadingError(ReportError):
    def __init__(self, heading: str) -> None:
        super().__init__(f'{heading!r} is not a severity heading')
        self.heading = heading


class UnreadableHeadingError(ReportError):
    def __init__(self, heading: str) -> None:
        super().__init__(f'{heading!r} is not a finding heading')
        self.heading = heading


class UnplacedFindingError(ReportError):
    def __init__(self, heading: str) -> None:
        super().__init__(f'{heading!r} comes before any severity heading')
        self.heading = heading


class FindingError(StateError):
    def __init__(self, index: int, sources: Sequence[str], problem: str) -> None:
        super().__init__(f'finding {index}: {problem} ({"/".join(sources)}); nothing was written')
        self.index = index
        self.sources = tuple(sources)


class FieldRequiredError(FindingError):
    def __init__(self, index: int, sources: Sequence[str], field: str) -> None:
        super().__init__(index, sources, f'{field} is required')
        self.field = field


class LocationShapeError(FindingError):
    def __init__(self, index: int, sources: Sequence[str]) -> None:
        super().__init__(index, sources, 'location must be path:line or path:start-end')


class UnsupportedQualityError(FindingError):
    def __init__(self, index: int, sources: Sequence[str]) -> None:
        super().__init__(
            index,
            sources,
            'a quality finding at Medium or above needs structured evidence '
            '(metric, idiom, or convention); lower it to Low or cite the evidence',
        )


class ForeignSourceError(FindingError):
    def __init__(self, index: int, sources: Sequence[str], persona: Persona) -> None:
        super().__init__(index, sources, f'a {persona} report holds only its own finding ids')
        self.persona = persona


class EvidenceKindError(FindingError):
    def __init__(self, index: int, sources: Sequence[str], kind: str) -> None:
        super().__init__(
            index, sources, f'evidence kind {kind!r} is not metric, idiom or convention'
        )
        self.kind = kind


class InvalidFieldError(FindingError):
    def __init__(self, index: int, sources: Sequence[str], *, field: str, reason: str) -> None:
        super().__init__(index, sources, f'{field}: {reason}')
        self.field = field
        self.reason = reason


class UnknownDimensionError(FindingError):
    def __init__(self, index: int, sources: Sequence[str], dimension: str) -> None:
        super().__init__(
            index, sources, f'dimension {dimension!r} is not security, sdlc, quality, docs or plan'
        )
        self.dimension = dimension


class UnknownFindingError(StateError):
    def __init__(self, finding: str) -> None:
        super().__init__(f'{finding}: no such finding; nothing was written')
        self.finding = finding


class ReasonRequiredError(StateError):
    def __init__(self, finding: str, decision: Decision) -> None:
        super().__init__(f'{finding}: {decision} needs a reason; nothing was written')
        self.finding = finding
        self.decision = decision


class NotChosenError(StateError):
    def __init__(self, finding: str) -> None:
        super().__init__(f'{finding}: only a finding the user chose to fix is resolved')
        self.finding = finding


class CommitRequiredError(StateError):
    def __init__(self, finding: str) -> None:
        super().__init__(f'{finding}: fixed needs commit')
        self.finding = finding


class ResultReasonError(StateError):
    def __init__(self, finding: str, result: Result) -> None:
        super().__init__(f'{finding}: {result} needs reason')
        self.finding = finding
        self.result = result

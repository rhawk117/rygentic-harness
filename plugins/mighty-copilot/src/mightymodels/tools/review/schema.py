"""Arguments and results of the `review` tool, and the values its service and rendering share.

`FindingInput` is one finding as a persona reports it and `Finding` is one as the run holds it.
`ReviewRun` is a run as it is recorded and read back.

`StartRequest` and `DisposeRequest` are what a caller fills in, and may leave out what the tool then
asks the user. `StartPayload` and `DisposePayload` are the complete forms the service takes.

The finding id pattern is published in the tool's schema and names its digits as `[0-9]`, so the
schema and the server accept the same ASCII digits and no others. Its maximum is the length of the
column a finding id is stored in, `FINDING_ID_LIMIT`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from mightymodels.core.declarative import NAME_LIMIT
from mightymodels.core.routing import Depth
from mightymodels.core.run_id import RunId
from mightymodels.core.slug import Slug
from mightymodels.tools.request import NameText, ProseText, RequestModel

SOURCE_ID_PATTERN = r'^(MV|UB)-\d+$'
FINDING_ID_PATTERN = r'^F[0-9]+$'
FINDING_ID_LIMIT = 20

type SourceId = Annotated[str, StringConstraints(pattern=SOURCE_ID_PATTERN)]
type FindingId = Annotated[
    str, StringConstraints(pattern=FINDING_ID_PATTERN, max_length=FINDING_ID_LIMIT)
]
type Approver = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_LIMIT)
]
type Sources = Annotated[tuple[SourceId, ...], Field(min_length=1)]


class ReviewAction(StrEnum):
    START = 'start'
    OVERRIDE = 'override'
    ADD = 'add'
    GATE = 'gate'
    DISPOSE = 'dispose'
    RESOLVE = 'resolve'
    REPORT = 'report'
    LIST = 'list'


class ReviewScope(StrEnum):
    DIFF = 'diff'
    BRANCH = 'branch'
    TICKET = 'ticket'
    CODEBASE = 'codebase'


class Emphasis(StrEnum):
    RELEASE = 'release-readiness'
    MAINTAINABILITY = 'maintainability'
    BALANCED = 'balanced'
    CUSTOM = 'custom'


class Persona(StrEnum):
    MERGE_VADER = 'merge-vader'
    UNCLE_BOB = 'uncle-bob'


class Severity(StrEnum):
    CRITICAL = 'Critical'
    HIGH = 'High'
    MEDIUM = 'Medium'
    LOW = 'Low'


class ReportedSeverity(StrEnum):
    BLOCKER = 'Blocker'
    CRITICAL = 'Critical'
    HIGH = 'High'
    MEDIUM = 'Medium'
    LOW = 'Low'


class Kind(StrEnum):
    DEFECT = 'defect'
    QUALITY = 'quality'


class EvidenceKind(StrEnum):
    METRIC = 'metric'
    IDIOM = 'idiom'
    CONVENTION = 'convention'


class Decision(StrEnum):
    FIX = 'fix'
    DEFER = 'defer'
    ACCEPT_RISK = 'accept-risk'
    DISMISS = 'dismiss'


class Result(StrEnum):
    FIXED = 'fixed'
    FAILED = 'failed'
    BLOCKED = 'blocked'


class Shape(StrEnum):
    FULL = 'full'
    COMMENT = 'comment'


class Verdict(StrEnum):
    BLOCK = 'BLOCK'
    CONDITIONS = 'MERGE WITH CONDITIONS'
    CLEAR = 'CLEAR'


class Evidence(RequestModel):
    kind: EvidenceKind
    cite: ProseText


class FindingInput(RequestModel):
    sources: Sources
    severity: ReportedSeverity
    title: ProseText
    location: ProseText
    fix: ProseText
    verify: ProseText
    kind: Kind = Kind.DEFECT
    security: bool = False
    evidence: Evidence | None = None


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: FindingId
    sources: Sources
    severity: Severity
    kind: Kind
    security: bool
    title: str
    location: str
    fix: str
    verify: str
    evidence: Evidence | None = None
    conflict: str | None = None


class StartRequest(RequestModel):
    scope: ReviewScope | None = None
    depth: Depth | None = None
    emphasis: Emphasis | None = None
    slug: Slug | None = None
    base: NameText | None = None
    weights: dict[Persona, float] | None = None
    persona: Persona | None = None


class StartPayload(StartRequest):
    scope: ReviewScope
    depth: Depth
    emphasis: Emphasis


class AddPayload(RequestModel):
    persona: Persona


class Disposition(RequestModel):
    decision: Decision
    reason: ProseText = ''


class DisposeRequest(RequestModel):
    by: Approver
    decisions: dict[FindingId, Disposition] | None = None
    finding: FindingId | None = None


class DisposePayload(DisposeRequest):
    decisions: dict[FindingId, Disposition]


class ResolvePayload(RequestModel):
    finding: FindingId
    result: Result
    commit: NameText | None = None
    reason: ProseText | None = None


class ReportPayload(RequestModel):
    shape: Shape = Shape.FULL


class StartReview(RequestModel):
    action: Literal[ReviewAction.START]
    payload: StartRequest | None = None


class OverrideReview(RequestModel):
    action: Literal[ReviewAction.OVERRIDE]
    run_id: RunId


class AddReview(RequestModel):
    action: Literal[ReviewAction.ADD]
    run_id: RunId
    payload: AddPayload


class GateReview(RequestModel):
    action: Literal[ReviewAction.GATE]
    run_id: RunId


class DisposeReview(RequestModel):
    action: Literal[ReviewAction.DISPOSE]
    run_id: RunId
    payload: DisposeRequest


class ResolveReview(RequestModel):
    action: Literal[ReviewAction.RESOLVE]
    run_id: RunId
    payload: ResolvePayload


class ReportReview(RequestModel):
    action: Literal[ReviewAction.REPORT]
    run_id: RunId
    payload: ReportPayload | None = None


class ListReview(RequestModel):
    action: Literal[ReviewAction.LIST]


type ReviewRequest = Annotated[
    StartReview
    | OverrideReview
    | AddReview
    | GateReview
    | DisposeReview
    | ResolveReview
    | ReportReview
    | ListReview,
    Field(discriminator='action'),
]


class ReviewView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    run_id: str | None = None
    verdict: Verdict | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewRun:
    run_id: RunId
    slug: Slug | None
    scope: ReviewScope
    base: str | None
    head: str | None
    depth: Depth
    emphasis: Emphasis
    weights: Mapping[Persona, float]
    personas: tuple[Persona, ...]
    models: Mapping[str, str | None]
    created_at: str

"""Arguments and results of the `snapshot` tool.

`SnapshotRecord` is the JSON baton-pass writes beside the Markdown, held once in the view. The
tool takes no action from the model: `SnapshotAction` has the one member its handler is filed
under, and the schema does not show it.

`LedgerLine` is one live entry of an investigation the ticket links, with the investigation and
the entry it came from under `from`.

`NotYetRecorded` is the type of a section the database holds nothing for yet. It reads empty and
admits no entry.
"""

from enum import StrEnum, auto
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from mightymodels_plugin.core.routing import Depth, Scope
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.investigation.schema import EntryKind
from mightymodels_plugin.tools.request import RequestModel
from mightymodels_plugin.tools.review.schema import Decision
from mightymodels_plugin.tools.ticket.schema import TicketStatus, Tracker

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

type Limit = Annotated[int, Field(ge=1, le=MAX_LIMIT)]
type NotYetRecorded = tuple[()]


class SnapshotAction(StrEnum):
    TAKE = auto()


class SnapshotRequest(RequestModel):
    slug: Slug
    limit: Limit = DEFAULT_LIMIT


class TicketSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str
    status: TicketStatus
    scope: Scope
    tracker: Tracker


class RepositoryState(BaseModel):
    model_config = ConfigDict(frozen=True)

    branch: str | None
    head: str | None
    dirty_count: int | None
    dirty: tuple[str, ...]


class TaskState(BaseModel):
    model_config = ConfigDict(frozen=True)

    task: str
    status: str
    attempts: dict[str, int]
    reasons: tuple[str, ...]


class CheckState(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    state: str


class PassingCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    argv: tuple[str, ...]


class FailedAttempt(BaseModel):
    model_config = ConfigDict(frozen=True)

    task: str
    to: str
    reason: str
    head: str
    at: str


class LedgerLine(BaseModel):
    model_config = ConfigDict(frozen=True, validate_by_name=True, serialize_by_alias=True)

    kind: EntryKind
    text: str
    cite: str | None
    origin: str = Field(alias='from')


class ReviewDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    finding: str
    decision: Decision
    reason: str


class ReviewState(BaseModel):
    model_config = ConfigDict(frozen=True)

    run: str
    depth: Depth
    head: str
    findings: int
    undecided: tuple[str, ...]
    remediation_open: tuple[str, ...]
    decisions: tuple[ReviewDecision, ...]


class SnapshotRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: Slug
    generated_at: str
    ticket: TicketSummary
    repository: RepositoryState
    tasks: tuple[TaskState, ...]
    checks: tuple[CheckState, ...]
    works: tuple[PassingCommand, ...]
    decisions: tuple[LedgerLine, ...]
    open_questions: tuple[LedgerLine, ...]
    do_not_retry: tuple[FailedAttempt, ...]
    review: ReviewState | None
    answers: NotYetRecorded = ()
    subagents: NotYetRecorded = ()
    warnings: tuple[str, ...]


class SnapshotView(BaseModel):
    model_config = ConfigDict(frozen=True)

    markdown: str
    record: SnapshotRecord
    markdown_path: str
    record_path: str

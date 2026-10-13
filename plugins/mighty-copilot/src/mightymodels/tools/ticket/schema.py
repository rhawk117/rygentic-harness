"""Arguments and results of the `ticket` tool.

A `LinkedInvestigation` is the id of an investigation as a caller names it. It is held to a slug's
length here, and `validate` refuses one that is not a slug.

`TicketInterview` is the interview as a caller fills it in, and may leave out the scope, the
compaction and the branch, which the tool then asks the user. `TicketAnswers` is the complete form
the service writes.

`TicketRequest` is the tool's one argument: one model per action, told apart by `action`.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from mightymodels.core.routing import Scope
from mightymodels.core.slug import SLUG_LIMIT, Slug
from mightymodels.tools.request import NameText, ProseText, RequestModel

type LinkedInvestigation = Annotated[str, StringConstraints(max_length=SLUG_LIMIT)]


class TicketAction(StrEnum):
    WRITE = 'write'
    VALIDATE = 'validate'
    SHOW = 'show'
    UPDATE_CONTEXT = 'update-context'


class TicketStatus(StrEnum):
    STAGED = 'staged'
    IN_PROGRESS = 'in-progress'
    CLOSED = 'closed'


class BranchChoice(StrEnum):
    CURRENT = 'current'
    NEW = 'new'


class TicketInterview(RequestModel):
    summary: ProseText
    context: tuple[ProseText, ...]
    scope: Scope | None = None
    compaction: bool | None = None
    branch: NameText | None = None
    issue: int | None = None
    jira: NameText | None = None
    reference_urls: tuple[ProseText, ...] = ()
    investigations: tuple[LinkedInvestigation, ...] = ()


class TicketAnswers(TicketInterview):
    scope: Scope
    compaction: bool
    branch: NameText


class TicketContext(RequestModel):
    context: tuple[ProseText, ...]


class WriteTicket(RequestModel):
    action: Literal[TicketAction.WRITE]
    slug: Slug
    fields: TicketInterview


class ValidateTicket(RequestModel):
    action: Literal[TicketAction.VALIDATE]
    slug: Slug


class ShowTicket(RequestModel):
    action: Literal[TicketAction.SHOW]
    slug: Slug


class UpdateContextTicket(RequestModel):
    action: Literal[TicketAction.UPDATE_CONTEXT]
    slug: Slug
    fields: TicketContext


type TicketRequest = Annotated[
    WriteTicket | ValidateTicket | ShowTicket | UpdateContextTicket, Field(discriminator='action')
]


class Tracker(BaseModel):
    model_config = ConfigDict(frozen=True)

    issue: int | None
    jira: str | None


class TicketSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticket: str
    summary: str
    branch: str
    scope: Scope
    plan_first: bool
    auto_escalate: bool = False
    models: dict[str, str | None]
    tracker: Tracker
    context: tuple[str, ...]
    validated_at: str


class WorkUnit(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: Slug
    status: TicketStatus
    ticket: TicketSection
    investigations: tuple[str, ...]


class TicketView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    unit: WorkUnit | None = None

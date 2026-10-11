"""Arguments and results of the `investigation` tool.

`LedgerEntry` is one entry as a caller hands it to `add`. The tool numbers it, stamps it with the
round, the time and HEAD, and stores it; the target is the first entry of every ledger and only
`start` writes it.

A payload's `request` is what an action needs beyond the investigation and the entries: the
target and its kind for `start`, the round for `add`, the kinds and the limit for `knowns`. A
`start` request may leave the kind out, and the tool asks the user; `InvestigationStart` is the
complete form the service takes.
Each action that takes a payload has a payload model of its own, and `add` carries its entries
there. `InvestigationRequest` is the tool's one argument: one model per action, told apart by
`action`.
"""

from enum import StrEnum, auto
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from mightymodels_plugin.core.declarative import PROSE_LIMIT
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.request import ProseText, RequestModel

DEFAULT_KNOWNS_LIMIT = 40

type Cite = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PROSE_LIMIT)
]
type KnownsLimit = Annotated[int, Field(ge=1)]


class InvestigationAction(StrEnum):
    START = auto()
    ADD = auto()
    RENDER = auto()
    KNOWNS = auto()
    LIST = auto()


class EntryKind(StrEnum):
    TARGET = auto()
    KNOWN = auto()
    OPEN = auto()
    DECISION = auto()
    RESOURCE = auto()
    NEXT = auto()


class TargetKind(StrEnum):
    BEHAVIOR = auto()
    CLAIM = auto()
    RESEARCH = auto()
    CHANGE = auto()


class Source(StrEnum):
    CODE_SCOUT = 'code-scout'
    WEB_SCOUT = 'web-scout'
    USER = 'user'
    PRIMARY = 'primary'


type TableKind = Literal[EntryKind.KNOWN, EntryKind.OPEN, EntryKind.DECISION, EntryKind.RESOURCE]
type TableKinds = Annotated[tuple[TableKind, ...], Field(min_length=1)]

TABLE_KINDS: tuple[TableKind, ...] = (
    EntryKind.KNOWN,
    EntryKind.OPEN,
    EntryKind.DECISION,
    EntryKind.RESOURCE,
)


class LedgerEntry(RequestModel):
    kind: EntryKind
    text: ProseText
    source: Source
    cite: Cite | None = None
    supersedes: tuple[int, ...] = ()


class InvestigationStartRequest(RequestModel):
    target: ProseText
    kind: TargetKind | None = None


class InvestigationStart(InvestigationStartRequest):
    kind: TargetKind


class LedgerRound(RequestModel):
    round: int


class KnownsFilter(RequestModel):
    kinds: TableKinds = TABLE_KINDS
    limit: KnownsLimit = DEFAULT_KNOWNS_LIMIT


class StartInvestigationPayload(RequestModel):
    request: InvestigationStartRequest


class AddInvestigationPayload(RequestModel):
    entries: tuple[LedgerEntry, ...]
    request: LedgerRound


class KnownsInvestigationPayload(RequestModel):
    request: KnownsFilter | None = None


class StartInvestigation(RequestModel):
    action: Literal[InvestigationAction.START]
    payload: StartInvestigationPayload


class AddInvestigation(RequestModel):
    action: Literal[InvestigationAction.ADD]
    investigation_id: Slug
    payload: AddInvestigationPayload


class RenderInvestigation(RequestModel):
    action: Literal[InvestigationAction.RENDER]
    investigation_id: Slug


class KnownsInvestigation(RequestModel):
    action: Literal[InvestigationAction.KNOWNS]
    investigation_id: Slug
    payload: KnownsInvestigationPayload | None = None


class ListInvestigation(RequestModel):
    action: Literal[InvestigationAction.LIST]


type InvestigationRequest = Annotated[
    StartInvestigation
    | AddInvestigation
    | RenderInvestigation
    | KnownsInvestigation
    | ListInvestigation,
    Field(discriminator='action'),
]


class InvestigationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    investigation_id: str | None = None

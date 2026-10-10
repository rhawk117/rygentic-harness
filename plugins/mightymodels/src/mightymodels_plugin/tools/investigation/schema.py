"""Arguments and results of the `investigation` tool.

`LedgerEntry` is one entry as a caller hands it to `add`. The tool numbers it, stamps it with the
round, the time and HEAD, and stores it; the target is the first entry of every ledger and only
`start` writes it.

`InvestigationRequest` is what an action needs beyond the investigation and the entries: the
target and its kind for `start`, the round for `add`, the kinds and the limit for `knowns`. A
`start` request may leave the kind out, and the tool asks the user; `InvestigationStart` is the
complete form the service takes.
`InvestigationPayload` carries the entries and the request as the tool's one payload argument.
"""

from enum import StrEnum, auto
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from mightymodels_plugin.core.declarative import PROSE_LIMIT
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


type InvestigationRequest = InvestigationStartRequest | LedgerRound | KnownsFilter


class InvestigationPayload(RequestModel):
    entries: tuple[LedgerEntry, ...] | None = None
    request: InvestigationRequest | None = None


class InvestigationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    investigation_id: str | None = None

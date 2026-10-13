"""The seam under the investigation service: a store whose transaction hands out the ledgers.

`InvestigationStore.transaction` is a context manager, and what it yields is an
`InvestigationRepository` that lives for that one transaction. The SQLite store in `repository.py`
wraps the database, and a store in test support holds the ledgers in memory, so the investigation
service runs on either.

A repository hands out frozen values and never a row. `LedgerRecord` is one entry as it is stored,
written and read back in the same shape. A `LatestRound` is an investigation's id with the latest
round it holds.
"""

from collections.abc import Collection, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from mightymodels.core.database import Latest
from mightymodels.core.slug import Slug
from mightymodels.tools.investigation.schema import EntryKind, Source
from mightymodels.tools.similarity.schema import Duplicate

type LatestRound = tuple[str, int]


@dataclass(slots=True, kw_only=True, frozen=True)
class LedgerRecord:
    seq: int
    round: int
    kind: EntryKind
    text: str
    source: Source
    cite: str | None
    supersedes: tuple[int, ...]
    at: str
    head: str | None


@runtime_checkable
class InvestigationRepository(Protocol):
    def has_entries(self, investigation: Slug) -> bool: ...

    def entries(self, investigation: Slug) -> list[LedgerRecord]: ...

    def unrecorded(self, investigations: Collection[Slug]) -> list[Slug]: ...

    def latest_rounds(self) -> Latest[LatestRound]: ...

    def append(self, investigation: Slug, records: Iterable[LedgerRecord]) -> list[Duplicate]: ...


@runtime_checkable
class InvestigationStore(Protocol):
    def transaction(self) -> AbstractContextManager[InvestigationRepository]: ...

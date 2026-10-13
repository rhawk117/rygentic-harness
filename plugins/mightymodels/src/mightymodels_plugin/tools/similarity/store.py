"""The seam under the similarity service: a store whose transaction hands out the repository.

`SimilarityStore.transaction` is a context manager, and what it yields is a `SimilarityRepository`
that lives for that one transaction. The SQLite store in `repository.py` wraps the database and
reads its candidates from the FTS5 index, and a store in test support holds the texts in memory,
so the similarity service runs on either.

A repository hands out frozen values and never a row. `Written` is one text as a domain stores it,
under its kind and the reference that names it there. `search` answers a `Match` for every stored
text that shares a content word with the query, and a write answers a `Duplicate` for each text
that resembles an earlier one.
"""

from collections.abc import Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from mightymodels_plugin.tools.similarity.schema import (
    Duplicate,
    Match,
    SimilarityKind,
    SpooledReport,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class Written:
    kind: SimilarityKind
    reference: str
    text: str


@runtime_checkable
class SimilarityRepository(Protocol):
    def search(self, query: str, *, kind: SimilarityKind | None) -> list[Match]: ...

    def record(self, written: Written) -> Duplicate | None: ...

    def record_all(self, writes: Iterable[Written]) -> list[Duplicate]: ...

    def has_scout_report(self, report: SpooledReport) -> bool: ...

    def add_scout_report(self, report: SpooledReport) -> list[Duplicate]: ...


@runtime_checkable
class SimilarityStore(Protocol):
    def transaction(self) -> AbstractContextManager[SimilarityRepository]: ...

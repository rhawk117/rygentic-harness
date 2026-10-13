"""The investigation store kept in memory: each investigation's ledger entries.

It is built on the similarity store kept in memory, and its transaction opens that one's, so an
entry and its text are kept together as the SQLite repository stores them in one transaction. A
transaction works on a copy and keeps it only when its block ends without an error.

An entry is held as the `LedgerRecord` the repository hands out. `latest_rounds` is held to
`INVESTIGATIONS_LISTED` as the SQLite read is, and no ledger is held to `ENTRIES`.
"""

from collections.abc import Collection, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from operator import attrgetter

from mightymodels.core.database import Latest
from mightymodels.core.slug import Slug
from mightymodels.tools.investigation.repository import (
    INVESTIGATIONS_LISTED,
    TARGET_SEQ,
    written_entry,
)
from mightymodels.tools.investigation.store import LatestRound, LedgerRecord
from mightymodels.tools.similarity.schema import Duplicate
from mightymodels.tools.similarity.tests.in_memory import (
    InMemorySimilarityRepository,
    InMemorySimilarityStore,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryInvestigationRepository:
    ledgers: dict[Slug, list[LedgerRecord]]
    similarity: InMemorySimilarityRepository

    def has_entries(self, investigation: Slug) -> bool:
        return any(record.seq == TARGET_SEQ for record in self.ledgers.get(investigation, ()))

    def entries(self, investigation: Slug) -> list[LedgerRecord]:
        return sorted(self.ledgers.get(investigation, ()), key=attrgetter('seq'))

    def unrecorded(self, investigations: Collection[Slug]) -> list[Slug]:
        return [slug for slug in investigations if not self.has_entries(slug)]

    def latest_rounds(self) -> Latest[LatestRound]:
        newest_first = [
            (investigation.root, max(record.round for record in self.ledgers[investigation]))
            for investigation in sorted(self.ledgers, key=attrgetter('root'), reverse=True)
        ]
        return INVESTIGATIONS_LISTED.latest(newest_first)

    def append(self, investigation: Slug, records: Iterable[LedgerRecord]) -> list[Duplicate]:
        appended = [replace(record, supersedes=tuple(record.supersedes)) for record in records]
        self.ledgers.setdefault(investigation, []).extend(appended)
        return self.similarity.record_all(
            written_entry(investigation, record) for record in appended
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryInvestigationStore:
    similarity: InMemorySimilarityStore
    ledgers: dict[Slug, list[LedgerRecord]] = field(default_factory=dict)

    @contextmanager
    def transaction(self) -> Generator[InMemoryInvestigationRepository]:
        with self.similarity.transaction() as similarity:
            working = InMemoryInvestigationRepository(
                ledgers={slug: list(records) for slug, records in self.ledgers.items()},
                similarity=similarity,
            )
            yield working
            self.ledgers.clear()
            self.ledgers.update(working.ledgers)

"""The close store kept in memory: each closed ticket's closing.

It is built on the snapshot store kept in memory, and its transaction opens that one's, so the
repository it hands out reads what the five domains recorded and marks the ticket closed in the
one transaction, as the SQLite repository does. A transaction works on a copy and keeps it only
when its block ends without an error.

A closing is held under its ticket, as the archive record it was written from with the path of
its archive, and a ticket closed again replaces its closing.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.close.schema import ArchiveRecord
from mightymodels_plugin.tools.snapshot.tests.in_memory import (
    InMemorySnapshotRepository,
    InMemorySnapshotStore,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedClosing:
    record: ArchiveRecord
    archive: str


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryCloseRepository:
    closings: dict[Slug, RecordedClosing]
    recorded: InMemorySnapshotRepository

    def record_closing(self, record: ArchiveRecord, *, archive: str) -> None:
        self.recorded.tickets.mark_closed(record.slug)
        self.closings[record.slug] = RecordedClosing(record=record, archive=archive)


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryCloseStore:
    snapshot: InMemorySnapshotStore
    closings: dict[Slug, RecordedClosing] = field(default_factory=dict)

    @contextmanager
    def transaction(self) -> Generator[InMemoryCloseRepository]:
        with self.snapshot.transaction() as recorded:
            working = InMemoryCloseRepository(closings=dict(self.closings), recorded=recorded)
            yield working
            self.closings.clear()
            self.closings.update(working.closings)

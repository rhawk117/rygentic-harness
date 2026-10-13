"""The crashout store kept in memory: the journal, oldest first.

It is built on the similarity store kept in memory, and its transaction opens that one's, so a
crashout and its root cause's text are kept together as the SQLite repository stores them in one
transaction. A transaction works on a copy and keeps it only when its block ends without an error.

A crashout's number is its place in the journal, and `latest_crashouts` is held to
`JOURNAL_WINDOW` as the SQLite read is.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field

from mightymodels_plugin.core.database import Latest
from mightymodels_plugin.tools.crashout.repository import JOURNAL_WINDOW, written_root_cause
from mightymodels_plugin.tools.crashout.schema import JournaledCrashout
from mightymodels_plugin.tools.crashout.store import Journaled
from mightymodels_plugin.tools.similarity.tests.in_memory import (
    InMemorySimilarityRepository,
    InMemorySimilarityStore,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryCrashoutRepository:
    journaled: list[JournaledCrashout]
    similarity: InMemorySimilarityRepository

    def latest_crashouts(self) -> Latest[JournaledCrashout]:
        return JOURNAL_WINDOW.latest(self.journaled[::-1])

    def latest_crashout(self) -> JournaledCrashout | None:
        return self.journaled[-1] if self.journaled else None

    def journal(self, crashout: JournaledCrashout) -> Journaled:
        self.journaled.append(crashout)
        number = len(self.journaled)
        written = written_root_cause(crashout, number)
        return Journaled(number=number, duplicates=self.similarity.record_all([written]))


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryCrashoutStore:
    similarity: InMemorySimilarityStore
    journaled: list[JournaledCrashout] = field(default_factory=list)

    @contextmanager
    def transaction(self) -> Generator[InMemoryCrashoutRepository]:
        with self.similarity.transaction() as similarity:
            working = InMemoryCrashoutRepository(
                journaled=list(self.journaled), similarity=similarity
            )
            yield working
            self.journaled[:] = working.journaled

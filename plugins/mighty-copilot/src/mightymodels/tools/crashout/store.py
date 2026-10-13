"""The seam under the crashout service: a store whose transaction hands out the journal.

`CrashoutStore.transaction` is a context manager, and what it yields is a `CrashoutRepository`
that lives for that one transaction. The SQLite store in `repository.py` wraps the database, and a
store in test support holds the journal in memory, so the crashout service runs on either.

A repository hands out frozen values and never a row: a crashout is read back as the
`JournaledCrashout` it was journaled as. `Journaled` is the answer to a write, the crashout's
number in the journal and the earlier texts its root cause resembles.
"""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from mightymodels.core.database import Latest
from mightymodels.tools.crashout.schema import JournaledCrashout
from mightymodels.tools.similarity.schema import Duplicate


@dataclass(slots=True, kw_only=True, frozen=True)
class Journaled:
    number: int
    duplicates: list[Duplicate]


@runtime_checkable
class CrashoutRepository(Protocol):
    def latest_crashouts(self) -> Latest[JournaledCrashout]: ...

    def latest_crashout(self) -> JournaledCrashout | None: ...

    def journal(self, crashout: JournaledCrashout) -> Journaled: ...


@runtime_checkable
class CrashoutStore(Protocol):
    def transaction(self) -> AbstractContextManager[CrashoutRepository]: ...

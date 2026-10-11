"""The seam under the close service: a store whose transaction hands out the close repository.

`CloseStore.transaction` is a context manager, and what it yields is a `CloseRepository` that
lives for that one transaction. The SQLite store in `repository.py` wraps the database, and a
store in test support holds the closings in memory, so the close service runs on either.

The repository's `recorded` is the `SnapshotRepository` of the same transaction: what the ticket,
task, contract, review and investigation domains recorded, which blocks a closing and which a
closing archives. `record_closing` is the only write. It marks the ticket closed and stores the
closing together, and nothing here reads a closing back.
"""

from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from mightymodels_plugin.tools.close.schema import ArchiveRecord
from mightymodels_plugin.tools.snapshot.store import SnapshotRepository


@runtime_checkable
class CloseRepository(Protocol):
    @property
    def recorded(self) -> SnapshotRepository: ...

    def record_closing(self, record: ArchiveRecord, *, archive: str) -> None: ...


@runtime_checkable
class CloseStore(Protocol):
    def transaction(self) -> AbstractContextManager[CloseRepository]: ...

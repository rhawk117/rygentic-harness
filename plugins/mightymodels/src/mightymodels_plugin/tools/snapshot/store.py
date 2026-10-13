"""The seam under the snapshot service: a store whose transaction hands out the five repositories.

`SnapshotStore.transaction` is a context manager, and what it yields is a `SnapshotRepository`
that lives for that one transaction. The SQLite store in `repository.py` wraps the database, and a
store in test support opens the five domains' stores kept in memory, so the snapshot service runs
on either.

A snapshot stores nothing of its own. Its repository hands out the ticket, task, contract, review
and investigation repositories of the one transaction, each as the Protocol its own domain names,
so every read of a snapshot sees the same state. The close domain builds on it: a closing reads
what a snapshot reads, in the transaction it writes in.
"""

from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from mightymodels_plugin.tools.contract.store import ContractRepository
from mightymodels_plugin.tools.investigation.store import InvestigationRepository
from mightymodels_plugin.tools.review.store import ReviewRepository
from mightymodels_plugin.tools.task.store import TaskRepository
from mightymodels_plugin.tools.ticket.store import TicketRepository


@runtime_checkable
class SnapshotRepository(Protocol):
    @property
    def tickets(self) -> TicketRepository: ...

    @property
    def tasks(self) -> TaskRepository: ...

    @property
    def contracts(self) -> ContractRepository: ...

    @property
    def reviews(self) -> ReviewRepository: ...

    @property
    def investigations(self) -> InvestigationRepository: ...


@runtime_checkable
class SnapshotStore(Protocol):
    def transaction(self) -> AbstractContextManager[SnapshotRepository]: ...

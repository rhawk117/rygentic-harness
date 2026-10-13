"""The snapshot store kept in memory: the five domains' stores, opened in one transaction.

It holds nothing of its own, as a snapshot has no table. It is built on the task, review and
investigation stores kept in memory, and its transaction opens theirs. The task store opens the
ticket store and the contract store, so the repository hands out the ticket and the contract
repository the task repository carries, as the SQLite repository builds the three on one session.
Each of those transactions works on a copy and keeps it only when its block ends without an error.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from mightymodels.tools.contract.tests.in_memory import InMemoryContractRepository
from mightymodels.tools.investigation.tests.in_memory import (
    InMemoryInvestigationRepository,
    InMemoryInvestigationStore,
)
from mightymodels.tools.review.tests.in_memory import (
    InMemoryReviewRepository,
    InMemoryReviewStore,
)
from mightymodels.tools.task.tests.in_memory import InMemoryTaskRepository, InMemoryTaskStore
from mightymodels.tools.ticket.tests.in_memory import InMemoryTicketRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemorySnapshotRepository:
    tickets: InMemoryTicketRepository
    tasks: InMemoryTaskRepository
    contracts: InMemoryContractRepository
    reviews: InMemoryReviewRepository
    investigations: InMemoryInvestigationRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemorySnapshotStore:
    tasks: InMemoryTaskStore
    reviews: InMemoryReviewStore
    investigations: InMemoryInvestigationStore

    @contextmanager
    def transaction(self) -> Generator[InMemorySnapshotRepository]:
        with (
            self.tasks.transaction() as tasks,
            self.reviews.transaction() as reviews,
            self.investigations.transaction() as investigations,
        ):
            yield InMemorySnapshotRepository(
                tickets=tasks.tickets,
                tasks=tasks,
                contracts=tasks.contracts,
                reviews=reviews,
                investigations=investigations,
            )

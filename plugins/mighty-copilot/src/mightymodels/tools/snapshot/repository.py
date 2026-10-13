"""What the ticket, task, contract, review and investigation domains recorded, in one transaction.

A snapshot stores nothing and has no table. `SqliteSnapshotStore` is the snapshot store over the
database: its `transaction` opens one and hands out the five domains' repositories, all built here
on that transaction's session, so the snapshot service never sees a session and one transaction
serves every read, and `snapshot_store` builds it as the `SnapshotStore` a service holds. Each of
the five holds the key of the git repository the database was opened for.

The repository holds that session because the close domain builds its own repository over it:
closing a ticket reads the same rows and writes in the same transaction. The session is no part of
the `SnapshotRepository` a service sees.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mightymodels.core.database import Database
from mightymodels.tools.contract.repository import SqliteContractRepository
from mightymodels.tools.investigation.repository import SqliteInvestigationRepository
from mightymodels.tools.review.repository import (
    SqliteDecisionRepository,
    SqliteReviewRepository,
)
from mightymodels.tools.snapshot.store import SnapshotStore
from mightymodels.tools.task.repository import SqliteTaskRepository
from mightymodels.tools.ticket.repository import SqliteTicketRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteSnapshotRepository:
    session: Session
    tickets: SqliteTicketRepository
    tasks: SqliteTaskRepository
    contracts: SqliteContractRepository
    reviews: SqliteReviewRepository
    investigations: SqliteInvestigationRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteSnapshotStore:
    database: Database

    @contextmanager
    def transaction(self) -> Generator[SqliteSnapshotRepository]:
        with self.database.transaction() as session:
            repository_key = self.database.repository_key
            tickets = SqliteTicketRepository(session=session, repository_key=repository_key)
            contracts = SqliteContractRepository(session=session, repository_key=repository_key)
            yield SqliteSnapshotRepository(
                session=session,
                tickets=tickets,
                tasks=SqliteTaskRepository(
                    session=session,
                    repository_key=repository_key,
                    tickets=tickets,
                    contracts=contracts,
                ),
                contracts=contracts,
                reviews=SqliteReviewRepository(
                    session=session,
                    repository_key=repository_key,
                    tickets=tickets,
                    decisions=SqliteDecisionRepository(
                        session=session, repository_key=repository_key
                    ),
                ),
                investigations=SqliteInvestigationRepository(
                    session=session, repository_key=repository_key
                ),
            )


def snapshot_store(database: Database) -> SnapshotStore:
    return SqliteSnapshotStore(database=database)

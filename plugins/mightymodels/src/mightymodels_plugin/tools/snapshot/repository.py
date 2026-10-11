"""What the ticket, task, contract, review and investigation domains recorded, in one transaction.

A snapshot stores nothing and has no table. `snapshot_transaction` opens one transaction on the
database and hands out the five domains' repositories, all built here on that transaction's
session, so the snapshot service never sees a session and one transaction serves every read. Each
of the five holds the key of the git repository the database was opened for.

The repository holds that session because the close domain builds its own repository over it:
closing a ticket reads the same rows and writes in the same transaction.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.tools.contract.repository import SqliteContractRepository
from mightymodels_plugin.tools.investigation.repository import SqliteInvestigationRepository
from mightymodels_plugin.tools.review.repository import (
    SqliteDecisionRepository,
    SqliteReviewRepository,
)
from mightymodels_plugin.tools.task.repository import SqliteTaskRepository
from mightymodels_plugin.tools.ticket.repository import SqliteTicketRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotRepository:
    session: Session
    tickets: SqliteTicketRepository
    tasks: SqliteTaskRepository
    contracts: SqliteContractRepository
    reviews: SqliteReviewRepository
    investigations: SqliteInvestigationRepository


@contextmanager
def snapshot_transaction(database: Database) -> Generator[SnapshotRepository]:
    with database.transaction() as session:
        repository_key = database.repository_key
        tickets = SqliteTicketRepository(session=session, repository_key=repository_key)
        contracts = SqliteContractRepository(session=session, repository_key=repository_key)
        yield SnapshotRepository(
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
                decisions=SqliteDecisionRepository(session=session, repository_key=repository_key),
            ),
            investigations=SqliteInvestigationRepository(
                session=session, repository_key=repository_key
            ),
        )

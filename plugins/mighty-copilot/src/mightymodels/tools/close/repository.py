"""A ticket's closing, written with the ticket's closed status in one transaction.

`SqliteCloseStore` is the close store over the database: its `transaction` opens the snapshot
store's and hands out the close repository built on that transaction's session, so the close
service never sees a session, and `close_store` builds it as the `CloseStore` a service holds. The
repository carries the snapshot repository as `recorded`: a closing is blocked by, and archives,
what the ticket, task, contract, review and investigation domains recorded, and it reads those
rows in the transaction it writes in.

`record_closing` is the only write. It marks the ticket closed and stores the closing's row
together, so no ticket reads closed without its closing. The closing is stored under the key of
the git repository the database was opened for, as the ticket's own row is.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mightymodels.core.database import Database
from mightymodels.core.repository_key import RepositoryKey
from mightymodels.tools.close.schema import ArchiveRecord
from mightymodels.tools.close.store import CloseStore
from mightymodels.tools.close.tables import ClosingRow
from mightymodels.tools.snapshot.repository import (
    SqliteSnapshotRepository,
    SqliteSnapshotStore,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteCloseRepository:
    session: Session
    repository_key: RepositoryKey
    recorded: SqliteSnapshotRepository

    def record_closing(self, record: ArchiveRecord, *, archive: str) -> None:
        self.recorded.tickets.mark_closed(record.slug)
        self.session.merge(
            ClosingRow(
                repository_key=self.repository_key.root,
                slug=record.slug.root,
                closed_at=record.closed_at,
                head=record.head,
                shipped=record.shipped,
                pr=record.pr,
                gotchas=list(record.gotchas),
                archive=archive,
            )
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteCloseStore:
    database: Database

    @contextmanager
    def transaction(self) -> Generator[SqliteCloseRepository]:
        with SqliteSnapshotStore(database=self.database).transaction() as recorded:
            yield SqliteCloseRepository(
                session=recorded.session,
                repository_key=self.database.repository_key,
                recorded=recorded,
            )


def close_store(database: Database) -> CloseStore:
    return SqliteCloseStore(database=database)

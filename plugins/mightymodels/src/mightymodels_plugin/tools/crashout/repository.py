"""The crashout journal, reached only through a repository.

`crashout_transaction` opens a transaction on the database and hands out the repository, which
holds that transaction's session, so the crashout service never sees a session. `journal` is the
only write: it adds one row and answers its number, and nothing updates or deletes a crashout. It
stores the root cause in the similarity table in the same transaction and answers the
near-duplicates of earlier rows that it turned up.

The repository holds the key of the git repository the database was opened for, and reads and
writes the journal under that key only. A crashout's number is its place in that repository's
journal, so each repository counts from 1 whatever the others journaled.

`latest_rows` is the newest end of the journal, oldest first, and no more than `JOURNAL_WINDOW`
of it: the journal only grows, and a read of all of it would grow with it.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

import sqlalchemy as sql
from sqlalchemy.orm import Session

from mightymodels_plugin.core.database import Database, Latest, ReadLimit
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.tools.crashout.schema import JournaledCrashout
from mightymodels_plugin.tools.crashout.tables import CrashoutRow
from mightymodels_plugin.tools.similarity.repository import SimilarityRepository, Written
from mightymodels_plugin.tools.similarity.schema import Duplicate, SimilarityKind

JOURNAL_WINDOW = ReadLimit(rows=100, kept='crashouts')


@dataclass(slots=True, kw_only=True, frozen=True)
class Journaled:
    number: int
    duplicates: list[Duplicate]


def crashout_row(crashout: JournaledCrashout, *, repository_key: RepositoryKey) -> CrashoutRow:
    return CrashoutRow(
        repository_key=repository_key.root,
        at=crashout.at,
        ticket=crashout.ticket,
        branch=crashout.branch,
        severity=crashout.severity,
        verdict=crashout.verdict,
        rant=crashout.rant,
        failures=list(crashout.failures),
        root_cause=crashout.root_cause,
        corrective_action=crashout.corrective_action,
        barked_back=crashout.barked_back,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutRepository:
    session: Session
    repository_key: RepositoryKey

    def latest_rows(self) -> Latest[CrashoutRow]:
        query = (
            sql.select(CrashoutRow)
            .where(CrashoutRow.repository_key == self.repository_key.root)
            .order_by(CrashoutRow.id.desc())
            .limit(JOURNAL_WINDOW.fetched)
        )
        return JOURNAL_WINDOW.latest(self.session.scalars(query).all())

    def latest_row(self) -> CrashoutRow | None:
        query = (
            sql.select(CrashoutRow)
            .where(CrashoutRow.repository_key == self.repository_key.root)
            .order_by(CrashoutRow.id.desc())
            .limit(1)
        )
        return self.session.scalars(query).first()

    def journal(self, crashout: JournaledCrashout) -> Journaled:
        self.session.add(crashout_row(crashout, repository_key=self.repository_key))
        journaled = (
            sql.select(sql.func.count())
            .select_from(CrashoutRow)
            .where(CrashoutRow.repository_key == self.repository_key.root)
        )
        number = self.session.scalars(journaled).one()
        similarity = SimilarityRepository(session=self.session, repository_key=self.repository_key)
        written = Written(
            kind=SimilarityKind.CRASHOUT, reference=f'#{number}', text=crashout.root_cause
        )
        return Journaled(number=number, duplicates=similarity.record_all([written]))


@contextmanager
def crashout_transaction(database: Database) -> Generator[CrashoutRepository]:
    with database.transaction() as session:
        yield CrashoutRepository(session=session, repository_key=database.repository_key)

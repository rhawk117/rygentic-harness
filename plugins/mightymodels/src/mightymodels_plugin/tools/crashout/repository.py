"""The crashout journal, reached only through a repository.

`SqliteCrashoutStore` is the crashout store over the database: its `transaction` opens one and
hands out the repository, which holds that transaction's session, so the crashout service never
sees a session, and `crashout_store` builds it as the `CrashoutStore` a service holds. `journal`
is the only write: it adds one row and answers its number, and nothing updates or deletes a
crashout. It stores the root cause in the similarity table in the same transaction and answers the
near-duplicates of earlier rows that it turned up.

The repository holds the key of the git repository the database was opened for, and reads and
writes the journal under that key only. A crashout's number is its place in that repository's
journal, so each repository counts from 1 whatever the others journaled.

`latest_crashouts` is the newest end of the journal, oldest first, and no more than
`JOURNAL_WINDOW` of it: the journal only grows, and a read of all of it would grow with it.

No row leaves the repository: a read hands out the `JournaledCrashout` that `crashout_of` maps a
row to.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

import sqlalchemy as sql
from sqlalchemy.orm import Session

from mightymodels_plugin.core.database import Database, Latest, ReadLimit
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.tools.crashout.schema import JournaledCrashout, Severity, Verdict
from mightymodels_plugin.tools.crashout.store import CrashoutStore, Journaled
from mightymodels_plugin.tools.crashout.tables import CrashoutRow
from mightymodels_plugin.tools.similarity.repository import SqliteSimilarityRepository
from mightymodels_plugin.tools.similarity.schema import SimilarityKind
from mightymodels_plugin.tools.similarity.store import Written

JOURNAL_WINDOW = ReadLimit(rows=100, kept='crashouts')


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


def crashout_of(row: CrashoutRow) -> JournaledCrashout:
    return JournaledCrashout(
        at=row.at,
        ticket=row.ticket,
        branch=row.branch,
        severity=Severity(row.severity),
        verdict=Verdict(row.verdict),
        rant=row.rant,
        failures=tuple(row.failures),
        root_cause=row.root_cause,
        corrective_action=row.corrective_action,
        barked_back=row.barked_back,
    )


def written_root_cause(crashout: JournaledCrashout, number: int) -> Written:
    return Written(kind=SimilarityKind.CRASHOUT, reference=f'#{number}', text=crashout.root_cause)


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteCrashoutRepository:
    session: Session
    repository_key: RepositoryKey

    def latest_crashouts(self) -> Latest[JournaledCrashout]:
        query = (
            sql.select(CrashoutRow)
            .where(CrashoutRow.repository_key == self.repository_key.root)
            .order_by(CrashoutRow.id.desc())
            .limit(JOURNAL_WINDOW.fetched)
        )
        newest_first = [crashout_of(row) for row in self.session.scalars(query)]
        return JOURNAL_WINDOW.latest(newest_first)

    def latest_crashout(self) -> JournaledCrashout | None:
        query = (
            sql.select(CrashoutRow)
            .where(CrashoutRow.repository_key == self.repository_key.root)
            .order_by(CrashoutRow.id.desc())
            .limit(1)
        )
        row = self.session.scalars(query).first()
        return None if row is None else crashout_of(row)

    def journal(self, crashout: JournaledCrashout) -> Journaled:
        self.session.add(crashout_row(crashout, repository_key=self.repository_key))
        journaled = (
            sql.select(sql.func.count())
            .select_from(CrashoutRow)
            .where(CrashoutRow.repository_key == self.repository_key.root)
        )
        number = self.session.scalars(journaled).one()
        similarity = SqliteSimilarityRepository(
            session=self.session, repository_key=self.repository_key
        )
        written = written_root_cause(crashout, number)
        return Journaled(number=number, duplicates=similarity.record_all([written]))


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteCrashoutStore:
    database: Database

    @contextmanager
    def transaction(self) -> Generator[SqliteCrashoutRepository]:
        with self.database.transaction() as session:
            yield SqliteCrashoutRepository(
                session=session, repository_key=self.database.repository_key
            )


def crashout_store(database: Database) -> CrashoutStore:
    return SqliteCrashoutStore(database=database)

"""An investigation's ledger entries, reached only through a repository.

`SqliteInvestigationStore` is the investigation store over the database: its `transaction` opens
one and hands out the repository, which holds that transaction's session, so the investigation
service never sees a session, and `investigation_store` builds it as the `InvestigationStore` a
service holds. A domain that reads a ledger inside its own transaction builds a
`SqliteInvestigationRepository` on that transaction's session. The repository holds the key of the
git repository the database was opened for, and reads and writes entries under that key only.

An investigation has no row of its own. It exists once its target is stored, which is entry 1 of
its ledger, so `has_entries` asks for that row. `append` is the only write and nothing updates or
deletes an entry: a later entry retires an earlier one by naming it in `supersedes`. It stores each
entry's text in the similarity table in the same transaction and answers the near-duplicates of
earlier rows that the texts turned up.

A ledger is read whole, and the read is refused once an investigation holds more than `ENTRIES`.
`append` is refused with `WriteLimitError` when the investigation would hold more than `ENTRIES`,
and then stores none of the entries it was given.
`latest_rounds` lists the newest investigations by id, which starts with the day, and no more than
`INVESTIGATIONS_LISTED` of them. `unrecorded` asks for the targets of all the investigations it
is given in one read.

No row leaves the repository: a read hands out the `LedgerRecord` that `record_of` maps a row to.
"""

from collections.abc import Collection, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass

import sqlalchemy as sql
from sqlalchemy.orm import Session

from mightymodels_plugin.core.database import Database, Latest, ReadLimit
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.investigation.schema import EntryKind, Source
from mightymodels_plugin.tools.investigation.store import (
    InvestigationStore,
    LatestRound,
    LedgerRecord,
)
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow
from mightymodels_plugin.tools.similarity.repository import SqliteSimilarityRepository
from mightymodels_plugin.tools.similarity.schema import Duplicate, SimilarityKind
from mightymodels_plugin.tools.similarity.store import Written

TARGET_SEQ = 1
ENTRIES = ReadLimit(rows=2000, kept='ledger entries')
INVESTIGATIONS_LISTED = ReadLimit(rows=100, kept='investigations')


def entry_row(
    investigation: Slug, record: LedgerRecord, *, repository_key: RepositoryKey
) -> LedgerEntryRow:
    return LedgerEntryRow(
        repository_key=repository_key.root,
        investigation_id=investigation.root,
        seq=record.seq,
        round=record.round,
        kind=record.kind,
        text=record.text,
        source=record.source,
        cite=record.cite,
        supersedes=list(record.supersedes),
        at=record.at,
        head=record.head,
    )


def record_of(row: LedgerEntryRow) -> LedgerRecord:
    return LedgerRecord(
        seq=row.seq,
        round=row.round,
        kind=EntryKind(row.kind),
        text=row.text,
        source=Source(row.source),
        cite=row.cite,
        supersedes=tuple(row.supersedes),
        at=row.at,
        head=row.head,
    )


def written_entry(investigation: Slug, record: LedgerRecord) -> Written:
    return Written(
        kind=SimilarityKind.LEDGER_ENTRY,
        reference=f'{investigation} e{record.seq}',
        text=record.text,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteInvestigationRepository:
    session: Session
    repository_key: RepositoryKey

    def has_entries(self, investigation: Slug) -> bool:
        target = (self.repository_key.root, investigation.root, TARGET_SEQ)
        return self.session.get(LedgerEntryRow, target) is not None

    def entries(self, investigation: Slug) -> list[LedgerRecord]:
        query = (
            sql.select(LedgerEntryRow)
            .where(
                LedgerEntryRow.repository_key == self.repository_key.root,
                LedgerEntryRow.investigation_id == investigation.root,
            )
            .order_by(LedgerEntryRow.seq)
            .limit(ENTRIES.fetched)
        )
        rows = list(self.session.scalars(query))
        if (error := ENTRIES.error(rows, owner=f'investigation {investigation}')) is not None:
            raise error
        return list(map(record_of, rows))

    def unrecorded(self, investigations: Collection[Slug]) -> list[Slug]:
        query = (
            sql.select(LedgerEntryRow.investigation_id)
            .where(
                LedgerEntryRow.repository_key == self.repository_key.root,
                LedgerEntryRow.investigation_id.in_([slug.root for slug in investigations]),
                LedgerEntryRow.seq == TARGET_SEQ,
            )
            .limit(len(investigations))
        )
        recorded = set(self.session.scalars(query))
        return [slug for slug in investigations if slug.root not in recorded]

    def latest_rounds(self) -> Latest[LatestRound]:
        query = (
            sql.select(LedgerEntryRow.investigation_id, sql.func.max(LedgerEntryRow.round))
            .where(LedgerEntryRow.repository_key == self.repository_key.root)
            .group_by(LedgerEntryRow.investigation_id)
            .order_by(LedgerEntryRow.investigation_id.desc())
            .limit(INVESTIGATIONS_LISTED.fetched)
        )
        newest_first = [
            (investigation, latest) for investigation, latest in self.session.execute(query)
        ]
        return INVESTIGATIONS_LISTED.latest(newest_first)

    def append(self, investigation: Slug, records: Iterable[LedgerRecord]) -> list[Duplicate]:
        appended = list(records)
        self.session.add_all(
            entry_row(investigation, record, repository_key=self.repository_key)
            for record in appended
        )
        self.session.flush()
        held = (
            sql.select(sql.func.count())
            .select_from(LedgerEntryRow)
            .where(
                LedgerEntryRow.repository_key == self.repository_key.root,
                LedgerEntryRow.investigation_id == investigation.root,
            )
        )
        error = ENTRIES.write_error(
            self.session.scalars(held).one(), owner=f'investigation {investigation}'
        )
        if error is not None:
            raise error
        similarity = SqliteSimilarityRepository(
            session=self.session, repository_key=self.repository_key
        )
        return similarity.record_all(written_entry(investigation, record) for record in appended)


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteInvestigationStore:
    database: Database

    @contextmanager
    def transaction(self) -> Generator[SqliteInvestigationRepository]:
        with self.database.transaction() as session:
            yield SqliteInvestigationRepository(
                session=session, repository_key=self.database.repository_key
            )


def investigation_store(database: Database) -> InvestigationStore:
    return SqliteInvestigationStore(database=database)

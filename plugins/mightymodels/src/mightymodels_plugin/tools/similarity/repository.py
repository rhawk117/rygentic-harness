"""The similarity rows and scout reports, reached only through a repository.

`SqliteSimilarityStore` is the similarity store over the database: its `transaction` opens one and
hands out the repository, and `similarity_store` builds it as the `SimilarityStore` a service
holds. A domain that writes a text builds a `SqliteSimilarityRepository` on its own transaction's
session, so the text and its similarity row are stored together or not at all. The repository
holds the key of the git repository the database was opened for, and reads and writes under that
key only.

`record` stores one text and answers the earlier row it resembles, if any: the candidates are read
before the text is stored, so a text never matches itself, and a text stored again under its own
kind and reference is not matched against the row it replaces. The text is redacted on its way to
the column, and one that redaction lengthens past the column is refused. `search` reads the same
candidates for a query and answers every one.

A candidate read returns at most `CANDIDATE_CAP` rows, best BM25 rank first, and every statement
that reads the index binds its values. `candidates` and `stored_row` hand out rows, so they are
methods of the SQLite repository alone and no part of the `SimilarityRepository` a service sees.
"""

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from operator import attrgetter

import sqlalchemy as sql
from sqlalchemy.orm import Session

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.declarative import NAME_LIMIT, REPORT_LIMIT
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.redaction import redact, redact_within
from mightymodels_plugin.tools.similarity.matching import (
    CANDIDATE_CAP,
    MATCH_OVERLAP,
    content_words,
    index_query,
    overlap,
)
from mightymodels_plugin.tools.similarity.schema import (
    Duplicate,
    Match,
    SimilarityKind,
    SpooledReport,
)
from mightymodels_plugin.tools.similarity.store import SimilarityStore, Written
from mightymodels_plugin.tools.similarity.tables import ScoutReportRow, SimilarityRow

CANDIDATES = """SELECT similarity.* FROM similarity_index
JOIN similarity ON similarity.id = similarity_index.rowid
WHERE similarity_index MATCH :query
  AND similarity.repository_key = :repository_key
  AND (:kind IS NULL OR similarity.kind = :kind)
  AND (:excluded_reference IS NULL
       OR similarity.kind != :excluded_kind OR similarity.reference != :excluded_reference)
ORDER BY bm25(similarity_index)
LIMIT :cap"""


def match_of(row: SimilarityRow, words: frozenset[str]) -> Match:
    return Match(
        kind=SimilarityKind(row.kind),
        reference=row.reference,
        text=row.text,
        overlap=overlap(words, content_words(row.text)),
    )


def closest(matches: Iterable[Match]) -> Match | None:
    close = [match for match in matches if match.overlap >= MATCH_OVERLAP]
    return max(close, key=attrgetter('overlap'), default=None)


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteSimilarityRepository:
    session: Session
    repository_key: RepositoryKey

    def candidates(
        self, words: frozenset[str], *, kind: SimilarityKind | None, excluding: Written | None
    ) -> list[SimilarityRow]:
        if not words:
            return []
        statement = sql.text(CANDIDATES).bindparams(
            query=index_query(words),
            repository_key=self.repository_key.root,
            kind=kind,
            excluded_kind=None if excluding is None else excluding.kind,
            excluded_reference=None if excluding is None else excluding.reference,
            cap=CANDIDATE_CAP,
        )
        return list(self.session.scalars(sql.select(SimilarityRow).from_statement(statement)))

    def search(self, query: str, *, kind: SimilarityKind | None) -> list[Match]:
        words = content_words(query)
        rows = self.candidates(words, kind=kind, excluding=None)
        return [match_of(row, words) for row in rows]

    def stored_row(self, written: Written) -> SimilarityRow | None:
        query = sql.select(SimilarityRow).where(
            SimilarityRow.repository_key == self.repository_key.root,
            SimilarityRow.kind == written.kind,
            SimilarityRow.reference == written.reference,
        )
        return self.session.scalars(query).one_or_none()

    def record(self, written: Written) -> Duplicate | None:
        stored = redact_within(written.text, 'text', REPORT_LIMIT)
        words = content_words(stored)
        rows = self.candidates(words, kind=None, excluding=written)
        earlier = closest(match_of(row, words) for row in rows)
        row = self.stored_row(written)
        if row is None:
            self.session.add(
                SimilarityRow(
                    repository_key=self.repository_key.root,
                    kind=written.kind,
                    reference=written.reference,
                    text=stored,
                )
            )
        else:
            row.text = stored
        return None if earlier is None else Duplicate(written=written.reference, earlier=earlier)

    def record_all(self, writes: Iterable[Written]) -> list[Duplicate]:
        duplicates = [self.record(written) for written in writes]
        return [duplicate for duplicate in duplicates if duplicate is not None]

    def has_scout_report(self, report: SpooledReport) -> bool:
        query = sql.select(ScoutReportRow.id).where(
            ScoutReportRow.repository_key == self.repository_key.root,
            ScoutReportRow.scout == report.scout,
            ScoutReportRow.target == redact(report.target),
        )
        return self.session.scalars(query.limit(1)).first() is not None

    def add_scout_report(self, report: SpooledReport) -> list[Duplicate]:
        row = ScoutReportRow(
            repository_key=self.repository_key.root,
            scout=report.scout,
            target=redact_within(report.target, 'target', NAME_LIMIT),
            report=redact_within(report.report, 'report', REPORT_LIMIT),
        )
        self.session.add(row)
        self.session.flush()
        written = Written(kind=SimilarityKind.SCOUT_REPORT, reference=str(row.id), text=row.report)
        return self.record_all([written])


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteSimilarityStore:
    database: Database

    @contextmanager
    def transaction(self) -> Generator[SqliteSimilarityRepository]:
        with self.database.transaction() as session:
            yield SqliteSimilarityRepository(
                session=session, repository_key=self.database.repository_key
            )


def similarity_store(database: Database) -> SimilarityStore:
    return SqliteSimilarityStore(database=database)

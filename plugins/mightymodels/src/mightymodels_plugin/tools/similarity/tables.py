"""The `similarity` and `scout_reports` tables, and the FTS5 index over the first.

A similarity row is the text of one ledger entry, scout report, review finding or crashout, with
the kind it came from and a reference to its source row. A kind and a reference name one row of a
repository, so a text written again under the same reference replaces the row's text. A scout
report row is a report as a scout wrote it, and it has a similarity row of its own.

`similarity_index` is an FTS5 index with no copy of the text: it reads the `text` column of
`similarity` as its content. SQLite does not keep an external-content index current, so three
triggers carry every insert, update and delete of a similarity row into the index, and a row
leaves the index in the statement that deletes it. The index, its triggers and FTS5's own tables
are created by the DDL below after the tables of `Base.metadata`, which `database.py` creates
only once the schema stamp is accepted. Each statement is `IF NOT EXISTS`, so a file whose tables
were made but whose index was not gets the index at the next open.

FTS5 keeps one set of term statistics for the whole index, which holds the text of every
repository, so every read of it joins `similarity` and filters on the repository key.
"""

from typing import Annotated

import sqlalchemy as sql
from sqlalchemy.event import listen
from sqlalchemy.orm import Mapped, mapped_column

from mightymodels_plugin.core.declarative import (
    Base,
    Name,
    ReportProse,
    RepositoryName,
    Serial,
    Timestamp,
    Word,
)
from mightymodels_plugin.core.repository_key import REPOSITORY_KEY_LIMIT

INDEX_STATEMENTS = (
    """CREATE VIRTUAL TABLE IF NOT EXISTS similarity_index
USING fts5(text, content='similarity', content_rowid='id', tokenize='unicode61')""",
    """CREATE TRIGGER IF NOT EXISTS similarity_index_insert AFTER INSERT ON similarity BEGIN
  INSERT INTO similarity_index(rowid, text) VALUES (new.id, new.text);
END""",
    """CREATE TRIGGER IF NOT EXISTS similarity_index_delete AFTER DELETE ON similarity BEGIN
  INSERT INTO similarity_index(similarity_index, rowid, text) VALUES ('delete', old.id, old.text);
END""",
    """CREATE TRIGGER IF NOT EXISTS similarity_index_update AFTER UPDATE ON similarity BEGIN
  INSERT INTO similarity_index(similarity_index, rowid, text) VALUES ('delete', old.id, old.text);
  INSERT INTO similarity_index(rowid, text) VALUES (new.id, new.text);
END""",
)

type IndexedRepositoryName = Annotated[
    str, mapped_column(sql.String(REPOSITORY_KEY_LIMIT), index=True)
]


class SimilarityRow(Base):
    __tablename__ = 'similarity'
    __table_args__ = (sql.UniqueConstraint('repository_key', 'kind', 'reference'),)

    id: Mapped[Serial]
    repository_key: Mapped[RepositoryName]
    kind: Mapped[Word]
    reference: Mapped[Name]
    text: Mapped[ReportProse]
    at: Mapped[Timestamp]


class ScoutReportRow(Base):
    __tablename__ = 'scout_reports'

    id: Mapped[Serial]
    repository_key: Mapped[IndexedRepositoryName]
    scout: Mapped[Word]
    target: Mapped[Name]
    report: Mapped[ReportProse]
    at: Mapped[Timestamp]


for statement in INDEX_STATEMENTS:
    listen(Base.metadata, 'after_create', sql.DDL(statement))

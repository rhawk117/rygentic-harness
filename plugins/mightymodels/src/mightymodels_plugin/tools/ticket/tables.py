"""The `tickets` table: one row per staged ticket.

A ticket is the row every task, closing and the rest of a ticket's work hangs from. Its ticket
file is its own, so no two tickets of a repository name the same one.

`auto_escalate` was added after files of this schema version were in use, and the version did not
change for it: the column has a server default, so a row written without it reads as off. A file
whose `tickets` table was made before the column gets it added, as it is declared here, after the
`create_all` of every open, which `database.py` runs under its write lock once the schema stamp is
accepted. A file that has the column, or no `tickets` table, is left as it is.
"""

from typing import Annotated

import sqlalchemy as sql
from sqlalchemy.event import listen
from sqlalchemy.orm import Mapped, mapped_column

from mightymodels_plugin.core.declarative import (
    WORD_LIMIT,
    Base,
    Models,
    Name,
    Prose,
    RepositoryKeyPart,
    SlugKeyPart,
    Texts,
    TextsIfAny,
    Timestamp,
    Word,
)
from mightymodels_plugin.tools.ticket.schema import TicketStatus

type StagedAtFirst = Annotated[
    str, mapped_column(sql.String(WORD_LIMIT), server_default=TicketStatus.STAGED)
]
type OffAtFirst = Annotated[bool, mapped_column(server_default=sql.false())]


class TicketRow(Base):
    __tablename__ = 'tickets'
    __table_args__ = (sql.UniqueConstraint('repository_key', 'ticket'),)

    repository_key: Mapped[RepositoryKeyPart]
    slug: Mapped[SlugKeyPart]
    status: Mapped[StagedAtFirst]
    ticket: Mapped[Name]
    summary: Mapped[Prose]
    branch: Mapped[Name]
    scope: Mapped[Word]
    plan_first: Mapped[bool]
    issue: Mapped[int | None]
    jira: Mapped[Name | None]
    models: Mapped[Models]
    context: Mapped[Texts]
    investigations: Mapped[TextsIfAny]
    validated_at: Mapped[Timestamp]
    auto_escalate: Mapped[OffAtFirst]


def add_auto_escalate_to_an_older_file(
    _metadata: sql.MetaData, connection: sql.Connection, **_given: object
) -> None:
    tickets = Base.metadata.tables[TicketRow.__tablename__]
    column = tickets.columns[TicketRow.auto_escalate.key]
    stored = sql.inspect(connection)
    if not stored.has_table(tickets.name):
        return
    if column.name in {held['name'] for held in stored.get_columns(tickets.name)}:
        return
    declared = sql.schema.CreateColumn(column).compile(dialect=connection.dialect)
    connection.exec_driver_sql(f'ALTER TABLE {tickets.name} ADD COLUMN {declared}')


listen(Base.metadata, 'after_create', add_auto_escalate_to_an_older_file)

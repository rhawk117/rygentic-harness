"""The `tickets` table: one row per staged ticket.

A ticket is the row every task, closing and the rest of a ticket's work hangs from. Its ticket
file is its own, so no two tickets of a repository name the same one.
"""

from typing import Annotated

import sqlalchemy as sql
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

"""The `closings` table: one row per closed ticket, holding what the user said as it closed.

A closing belongs to the ticket it closes, and its archive file is its own.
"""

import sqlalchemy as sql
from sqlalchemy.orm import Mapped

from mightymodels.core.declarative import (
    Base,
    Name,
    Prose,
    RepositoryKeyPart,
    Sha,
    SlugKeyPart,
    TextsIfAny,
    Timestamp,
    child_of,
)
from mightymodels.tools.ticket.tables import TicketRow


class ClosingRow(Base):
    __tablename__ = 'closings'
    __table_args__ = (child_of(TicketRow), sql.UniqueConstraint('repository_key', 'archive'))

    repository_key: Mapped[RepositoryKeyPart]
    slug: Mapped[SlugKeyPart]
    closed_at: Mapped[Timestamp]
    head: Mapped[Sha | None]
    shipped: Mapped[Prose]
    pr: Mapped[Prose | None]
    gotchas: Mapped[TextsIfAny]
    archive: Mapped[Name]

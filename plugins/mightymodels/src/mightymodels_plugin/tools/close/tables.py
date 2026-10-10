"""The `closings` table: one row per closed ticket, holding what the user said as it closed.

A closing belongs to the ticket it closes, and its archive file is its own.
"""

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped

from mightymodels_plugin.core.declarative import (
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
from mightymodels_plugin.tools.ticket.tables import TicketRow


class ClosingRow(Base):
    __tablename__ = 'closings'
    __table_args__ = (child_of(TicketRow), UniqueConstraint('repository_key', 'archive'))

    repository_key: Mapped[RepositoryKeyPart]
    slug: Mapped[SlugKeyPart]
    closed_at: Mapped[Timestamp]
    head: Mapped[Sha | None]
    shipped: Mapped[Prose]
    pr: Mapped[Prose | None]
    gotchas: Mapped[TextsIfAny]
    archive: Mapped[Name]

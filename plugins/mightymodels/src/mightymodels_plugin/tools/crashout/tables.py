"""The `crashouts` table: one row per journaled crashout, numbered in the order it was added.

A crashout may name a ticket, staged or not, so it has no parent row.
"""

from typing import Annotated

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from mightymodels_plugin.core.declarative import (
    Base,
    Name,
    Prose,
    Serial,
    SlugName,
    Texts,
    Timestamp,
    Word,
)
from mightymodels_plugin.core.repository_key import REPOSITORY_KEY_LIMIT

type IndexedRepositoryName = Annotated[str, mapped_column(String(REPOSITORY_KEY_LIMIT), index=True)]


class CrashoutRow(Base):
    __tablename__ = 'crashouts'

    id: Mapped[Serial]
    repository_key: Mapped[IndexedRepositoryName]
    at: Mapped[Timestamp]
    ticket: Mapped[SlugName | None]
    branch: Mapped[Name | None]
    severity: Mapped[Word]
    verdict: Mapped[Word]
    rant: Mapped[Prose]
    failures: Mapped[Texts]
    root_cause: Mapped[Prose]
    corrective_action: Mapped[Prose]
    barked_back: Mapped[bool]

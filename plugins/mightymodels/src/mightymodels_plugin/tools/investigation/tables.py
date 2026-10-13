"""The `ledger_entries` table: one row per entry of an investigation's ledger, the target first.

An investigation has no row of its own, so an entry has no parent row.
"""

from typing import Annotated

import sqlalchemy as sql
from sqlalchemy.orm import Mapped, mapped_column

from mightymodels_plugin.core.declarative import (
    EMPTY_LIST,
    Base,
    Prose,
    RepositoryKeyPart,
    Serial,
    Sha,
    SlugKeyPart,
    Timestamp,
    Word,
)

type EntryNumbers = Annotated[list[int], mapped_column(sql.JSON, server_default=EMPTY_LIST)]


class LedgerEntryRow(Base):
    __tablename__ = 'ledger_entries'

    repository_key: Mapped[RepositoryKeyPart]
    investigation_id: Mapped[SlugKeyPart]
    seq: Mapped[Serial]
    round: Mapped[int]
    kind: Mapped[Word]
    text: Mapped[Prose]
    source: Mapped[Word]
    cite: Mapped[Prose | None]
    supersedes: Mapped[EntryNumbers]
    at: Mapped[Timestamp]
    head: Mapped[Sha | None]

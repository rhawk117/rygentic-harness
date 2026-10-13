"""The `contract_commands` and `receipts` tables: a ticket's approved commands and their runs.

A receipt belongs to the approved command it is a run of. A command is approved for a ticket by
its slug alone, staged or not, so no ticket row stands behind it.
"""

from typing import Annotated

import sqlalchemy as sql
from sqlalchemy.orm import Mapped, mapped_column

from mightymodels_plugin.core.declarative import (
    NAME_LIMIT,
    Base,
    Name,
    RepositoryKeyPart,
    RepositoryName,
    Serial,
    Sha,
    SlugKeyPart,
    SlugName,
    TaskName,
    Texts,
    Timestamp,
    Word,
    child_of,
)
from mightymodels_plugin.tools.contract.executor import TAIL_CHARS
from mightymodels_plugin.tools.contract.schema import DEFAULT_TIMEOUT

type CommandKeyPart = Annotated[str, mapped_column(sql.String(NAME_LIMIT), primary_key=True)]
type ExitZeroAtFirst = Annotated[int, mapped_column(server_default=sql.text('0'))]
type DefaultTimeoutAtFirst = Annotated[
    int, mapped_column(server_default=sql.text(str(DEFAULT_TIMEOUT)))
]
type Tail = Annotated[str, mapped_column(sql.String(TAIL_CHARS))]


class CommandRow(Base):
    __tablename__ = 'contract_commands'

    repository_key: Mapped[RepositoryKeyPart]
    slug: Mapped[SlugKeyPart]
    command_id: Mapped[CommandKeyPart]
    task_id: Mapped[TaskName | None]
    argv: Mapped[Texts]
    expect_exit: Mapped[ExitZeroAtFirst]
    timeout: Mapped[DefaultTimeoutAtFirst]
    approved_by: Mapped[Name]
    approved_at: Mapped[Timestamp]
    head: Mapped[Sha | None]


class ReceiptRow(Base):
    __tablename__ = 'receipts'
    __table_args__ = (
        child_of(CommandRow),
        sql.Index('ix_receipts_command', 'repository_key', 'slug', 'command_id'),
    )

    id: Mapped[Serial]
    repository_key: Mapped[RepositoryName]
    slug: Mapped[SlugName]
    command_id: Mapped[Name]
    argv: Mapped[Texts]
    outcome: Mapped[Word]
    exit: Mapped[int | None]
    duration_ms: Mapped[int]
    stdout_tail: Mapped[Tail]
    stderr_tail: Mapped[Tail]
    digest: Mapped[Sha]
    head: Mapped[Sha | None]
    phase: Mapped[Word]
    at: Mapped[Timestamp]

"""A ticket's approved commands and their receipts, reached only through a repository.

`SqliteContractStore` is the contract store over the database: its `transaction` opens one and
hands out the repository, which holds that transaction's session, so the contract service never
sees a session, and `contract_store` builds it as the `ContractStore` a service holds. A domain
that reads commands or receipts inside its own transaction builds a `SqliteContractRepository` on
that transaction's session. The repository holds the key of the git repository the database was
opened for, and reads and writes rows under that key only.

No row leaves the repository: a command is handed out as a `RecordedCommand` and a receipt as the
`Receipt` it was recorded from.

A read returns every command of a ticket, or the latest receipt of every command, and is refused
once a ticket holds more than `COMMANDS`. The latest receipt of each command is chosen by the
database, so a read fetches one row per command however often each was run.

`approve` is refused with `WriteLimitError` when the ticket would hold more than `COMMANDS`, and
then stores none of the commands it was given. A receipt belongs to a command, so the latest
receipts of a ticket are never more than its commands.
"""

import re
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass

import sqlalchemy as sql
from sqlalchemy.orm import Session

from mightymodels_plugin.core.database import Database, ReadLimit
from mightymodels_plugin.core.repository_key import RepositoryKey
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.task_id import TASK_ID_PATTERN
from mightymodels_plugin.tools.contract.schema import ContractCommand, Outcome, Phase, Receipt
from mightymodels_plugin.tools.contract.store import Approval, ContractStore, RecordedCommand
from mightymodels_plugin.tools.contract.tables import CommandRow, ReceiptRow

TASK_ID = re.compile(TASK_ID_PATTERN)
COMMANDS = ReadLimit(rows=1000, kept='contract commands')


def owning_task(command_id: str) -> str | None:
    task_id, separator, _ = command_id.partition('.')
    return task_id if separator and TASK_ID.match(task_id) else None


def command_row(
    slug: Slug, command: ContractCommand, approval: Approval, *, repository_key: RepositoryKey
) -> CommandRow:
    return CommandRow(
        repository_key=repository_key.root,
        slug=slug.root,
        command_id=command.id,
        task_id=owning_task(command.id),
        argv=list(command.argv),
        expect_exit=command.expect_exit,
        timeout=command.timeout,
        approved_by=command.approved_by,
        approved_at=approval.at,
        head=approval.head,
    )


def receipt_row(slug: Slug, receipt: Receipt, *, repository_key: RepositoryKey) -> ReceiptRow:
    return ReceiptRow(
        repository_key=repository_key.root,
        slug=slug.root,
        command_id=receipt.id,
        argv=list(receipt.argv),
        outcome=receipt.outcome,
        exit=receipt.exit,
        duration_ms=receipt.duration_ms,
        stdout_tail=receipt.stdout_tail,
        stderr_tail=receipt.stderr_tail,
        digest=receipt.digest,
        head=receipt.head,
        phase=receipt.phase,
        at=receipt.at,
    )


def recorded_command(row: CommandRow) -> RecordedCommand:
    return RecordedCommand(
        id=row.command_id,
        task_id=row.task_id,
        argv=tuple(row.argv),
        expect_exit=row.expect_exit,
        timeout=row.timeout,
    )


def receipt_of(row: ReceiptRow) -> Receipt:
    return Receipt(
        id=row.command_id,
        argv=tuple(row.argv),
        outcome=Outcome(row.outcome),
        exit=row.exit,
        duration_ms=row.duration_ms,
        stdout_tail=row.stdout_tail,
        stderr_tail=row.stderr_tail,
        digest=row.digest,
        head=row.head,
        phase=Phase(row.phase),
        at=row.at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteContractRepository:
    session: Session
    repository_key: RepositoryKey

    def commands(self, slug: Slug) -> list[RecordedCommand]:
        query = (
            sql.select(CommandRow)
            .where(
                CommandRow.repository_key == self.repository_key.root,
                CommandRow.slug == slug.root,
            )
            .order_by(CommandRow.command_id)
            .limit(COMMANDS.fetched)
        )
        rows = list(self.session.scalars(query))
        if (error := COMMANDS.error(rows, owner=f'ticket {slug}')) is not None:
            raise error
        return list(map(recorded_command, rows))

    def latest_receipts(self, slug: Slug) -> dict[str, Receipt]:
        latest_of_each_command = (
            sql.select(sql.func.max(ReceiptRow.id))
            .where(
                ReceiptRow.repository_key == self.repository_key.root,
                ReceiptRow.slug == slug.root,
            )
            .group_by(ReceiptRow.command_id)
        )
        query = (
            sql.select(ReceiptRow)
            .where(ReceiptRow.id.in_(latest_of_each_command))
            .limit(COMMANDS.fetched)
        )
        rows = list(self.session.scalars(query))
        if (error := COMMANDS.error(rows, owner=f'ticket {slug}')) is not None:
            raise error
        return {row.command_id: receipt_of(row) for row in rows}

    def approve(self, slug: Slug, commands: Iterable[ContractCommand], approval: Approval) -> None:
        self.session.add_all(
            command_row(slug, command, approval, repository_key=self.repository_key)
            for command in commands
        )
        self.session.flush()
        held = (
            sql.select(sql.func.count())
            .select_from(CommandRow)
            .where(
                CommandRow.repository_key == self.repository_key.root,
                CommandRow.slug == slug.root,
            )
        )
        error = COMMANDS.write_error(self.session.scalars(held).one(), owner=f'ticket {slug}')
        if error is not None:
            raise error

    def record(self, slug: Slug, receipts: Iterable[Receipt]) -> None:
        self.session.add_all(
            receipt_row(slug, receipt, repository_key=self.repository_key) for receipt in receipts
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteContractStore:
    database: Database

    @contextmanager
    def transaction(self) -> Generator[SqliteContractRepository]:
        with self.database.transaction() as session:
            yield SqliteContractRepository(
                session=session, repository_key=self.database.repository_key
            )


def contract_store(database: Database) -> ContractStore:
    return SqliteContractStore(database=database)

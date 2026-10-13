"""The contract store kept in memory: what was approved for each ticket, and every receipt.

A transaction works on a copy and keeps it only when its block ends without an error, as a
database transaction does. An approved command is held with who approved it and the approval it
came in, as its row holds them, and a receipt in the order it was recorded, so the latest of a
command is the last one.
"""

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from operator import attrgetter

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.contract.repository import owning_task
from mightymodels_plugin.tools.contract.schema import ContractCommand, Receipt
from mightymodels_plugin.tools.contract.store import Approval, RecordedCommand

type CommandKey = tuple[Slug, str]


@dataclass(slots=True, kw_only=True, frozen=True)
class ApprovedCommandRecord:
    command: RecordedCommand
    approved_by: str
    approval: Approval


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedReceipt:
    slug: Slug
    receipt: Receipt


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryContractRepository:
    approved: dict[CommandKey, ApprovedCommandRecord]
    receipts: list[RecordedReceipt]

    def commands(self, slug: Slug) -> list[RecordedCommand]:
        of_the_ticket = (
            record.command for (owner, _), record in self.approved.items() if owner == slug
        )
        return sorted(of_the_ticket, key=attrgetter('id'))

    def latest_receipts(self, slug: Slug) -> dict[str, Receipt]:
        return {
            recorded.receipt.id: recorded.receipt
            for recorded in self.receipts
            if recorded.slug == slug
        }

    def approve(self, slug: Slug, commands: Iterable[ContractCommand], approval: Approval) -> None:
        for command in commands:
            recorded = RecordedCommand(
                id=command.id,
                task_id=owning_task(command.id),
                argv=command.argv,
                expect_exit=command.expect_exit,
                timeout=command.timeout,
            )
            self.approved[slug, command.id] = ApprovedCommandRecord(
                command=recorded, approved_by=command.approved_by, approval=approval
            )

    def record(self, slug: Slug, receipts: Iterable[Receipt]) -> None:
        self.receipts.extend(RecordedReceipt(slug=slug, receipt=receipt) for receipt in receipts)


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryContractStore:
    approved: dict[CommandKey, ApprovedCommandRecord] = field(default_factory=dict)
    receipts: list[RecordedReceipt] = field(default_factory=list)

    @contextmanager
    def transaction(self) -> Generator[InMemoryContractRepository]:
        working = InMemoryContractRepository(
            approved=dict(self.approved), receipts=list(self.receipts)
        )
        yield working
        self.approved.clear()
        self.approved.update(working.approved)
        self.receipts[:] = working.receipts

"""The seam under the contract service: a store whose transaction hands out the repository.

`ContractStore.transaction` is a context manager, and what it yields is a `ContractRepository` that
lives for that one transaction. The SQLite store in `repository.py` wraps the database, and a
store in test support holds the commands and receipts in memory, so the service runs on either.

A repository hands out frozen values and never a row. A receipt is the `Receipt` the executor
made. A command is a `RecordedCommand`: what `verify run` executes, and the task that owns it, which
the task domain reads and `ApprovedCommand` does not hold. `Approval` is when a command was
approved and the HEAD it was approved at.
"""

from collections.abc import Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from mightymodels.core.slug import Slug
from mightymodels.tools.contract.schema import ContractCommand, Receipt


@dataclass(slots=True, kw_only=True, frozen=True)
class Approval:
    at: str
    head: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedCommand:
    id: str
    task_id: str | None
    argv: tuple[str, ...]
    expect_exit: int
    timeout: int


@runtime_checkable
class ContractRepository(Protocol):
    def commands(self, slug: Slug) -> list[RecordedCommand]: ...

    def latest_receipts(self, slug: Slug) -> dict[str, Receipt]: ...

    def approve(
        self, slug: Slug, commands: Iterable[ContractCommand], approval: Approval
    ) -> None: ...

    def record(self, slug: Slug, receipts: Iterable[Receipt]) -> None: ...


@runtime_checkable
class ContractStore(Protocol):
    def transaction(self) -> AbstractContextManager[ContractRepository]: ...

"""The contract service: the commands a ticket may run to prove its work, and `verify run`.

`approve` records the commands the user approved, and an approved id never changes its argv.
`status` reads each command's latest receipt against the current HEAD. `run_approved` is
`verify run`: it takes ids only and looks each one up in the ticket's contract, so nothing outside
what the user approved runs through it. It reads the commands in one transaction, runs them with
no transaction open, and records a receipt for every run in a second.

The service is built once by whoever owns the workspace and the database, the server in its
lifespan and the `verify run` command for its one run, and holds both. A method opens a
transaction through `contract_transaction`, which hands it the repository. Everything above the
class reads no service state. The command line imports this module, so nothing it imports may
load `mcp`.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from mightymodels_plugin.clock import now
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.process import ProcessRunner
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.head import SHORT_SHA, short_head
from mightymodels_plugin.tools.contract.executor import receipt_for
from mightymodels_plugin.tools.contract.repository import Approval, contract_transaction
from mightymodels_plugin.tools.contract.schema import (
    ApprovedCommand,
    CommandState,
    ContractCommand,
    ContractView,
    Outcome,
    Phase,
    Receipt,
)
from mightymodels_plugin.tools.contract.tables import CommandRow, ReceiptRow

type ArgvById = Mapping[str, tuple[str, ...]]


class MissingApprovalError(StateError):
    def __init__(self) -> None:
        super().__init__('approved_by is required: who approved these commands')


class ChangedCommandError(StateError):
    def __init__(self, command_id: str) -> None:
        super().__init__(
            f'{command_id} is already approved with a different argv; give it a new id'
        )
        self.command_id = command_id


class NoContractError(StateError):
    def __init__(self, slug: Slug) -> None:
        super().__init__(f'{slug} has no approved commands; record a contract first')
        self.slug = slug


class UnknownCommandError(StateError):
    def __init__(self, unknown: list[str]) -> None:
        super().__init__(f'not in the contract: {unknown}; approve them with contract first')
        self.unknown = unknown


@dataclass(slots=True, kw_only=True, frozen=True)
class RunRequest:
    ids: tuple[str, ...] | None
    phase: Phase


@dataclass(slots=True, kw_only=True, frozen=True)
class RunResult:
    text: str
    passed: bool


def new_commands(
    commands: Iterable[ContractCommand], recorded: ArgvById
) -> dict[str, ContractCommand]:
    new: dict[str, ContractCommand] = {}
    for command in commands:
        if command.id not in recorded:
            new.setdefault(command.id, command)
    return new


def changed_command_error(
    commands: Iterable[ContractCommand], approved: ArgvById
) -> ChangedCommandError | None:
    changed = next(
        (command.id for command in commands if approved[command.id] != command.argv), None
    )
    return None if changed is None else ChangedCommandError(changed)


def state_of(command: CommandRow, latest: ReceiptRow | None, head: str | None) -> str:
    if latest is None:
        return 'never-run'
    if latest.head != head:
        return f'stale ({latest.outcome} at {str(latest.head)[:SHORT_SHA]})'
    return f'{latest.outcome} {latest.phase} expect={command.expect_exit}'


def approved_commands(
    rows: Iterable[CommandRow], slug: Slug, ids: Sequence[str] | None
) -> list[ApprovedCommand]:
    commands = {row.command_id: row for row in rows}
    if not commands:
        raise NoContractError(slug)
    selected = sorted(commands) if ids is None else list(ids)
    unknown = [command_id for command_id in selected if command_id not in commands]
    if unknown:
        raise UnknownCommandError(unknown)
    return [
        ApprovedCommand(
            id=command_id,
            argv=tuple(commands[command_id].argv),
            expect_exit=commands[command_id].expect_exit,
            timeout=commands[command_id].timeout,
        )
        for command_id in selected
    ]


def receipt_text(receipt: Receipt) -> str:
    seconds = receipt.duration_ms / 1000
    line = f'{receipt.id} {receipt.outcome} exit={receipt.exit} {seconds:.1f}s\n'
    if receipt.outcome is Outcome.PASSED:
        return line
    detail = receipt.stderr_tail or receipt.stdout_tail
    return line + ''.join(f'  | {text}\n' for text in detail.splitlines())


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractService:
    workspace: Workspace
    database: Database
    processes: ProcessRunner

    def approve(self, slug: Slug, commands: Sequence[ContractCommand]) -> ContractView:
        if any(not command.approved_by.strip() for command in commands):
            raise MissingApprovalError
        approval = Approval(at=now(), head=self.workspace.git.resolve_head())
        with contract_transaction(self.database) as repository:
            recorded = {row.command_id: tuple(row.argv) for row in repository.commands(slug)}
            new = new_commands(commands, recorded)
            approved = recorded | {command_id: command.argv for command_id, command in new.items()}
            if (error := changed_command_error(commands, approved)) is not None:
                raise error
            repository.approve(slug, new.values(), approval)
        text = f'contract: {len(approved)} commands ({len(new)} new)\n'
        return ContractView(text=text, passing=True)

    def status(self, slug: Slug) -> ContractView:
        head = self.workspace.git.resolve_head()
        with contract_transaction(self.database) as repository:
            latest = repository.latest_receipts(slug)
            states = tuple(
                CommandState(
                    id=command.command_id,
                    argv=tuple(command.argv),
                    state=state_of(command, latest.get(command.command_id), head),
                )
                for command in repository.commands(slug)
            )
        rows = ''.join(f'{state.id} {state.state}\n' for state in states)
        header = f'HEAD {short_head(head)}\n'
        return ContractView(
            text=header + (rows or 'no matching commands\n'),
            passing=all(state.state.split(' ', 1)[0] == Outcome.PASSED for state in states),
            commands=states,
        )

    def run_approved(self, slug: Slug, request: RunRequest) -> RunResult:
        with contract_transaction(self.database) as repository:
            commands = approved_commands(repository.commands(slug), slug, request.ids)
        receipts = [
            receipt_for(command, self.workspace, request.phase, processes=self.processes)
            for command in commands
        ]
        with contract_transaction(self.database) as repository:
            repository.record(slug, receipts)
        return RunResult(
            text=''.join(map(receipt_text, receipts)),
            passed=all(receipt.outcome is Outcome.PASSED for receipt in receipts),
        )

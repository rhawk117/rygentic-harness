"""What a hook command is given: Claude Code's JSON on standard input, the environment and the
directory the session started in.

A hook command never refuses. When it cannot work it says why on standard error and exits 0
(`rejection.skipped`), because exit code 2 keeps a subagent from stopping or a compaction from
running. This module loads no database or server package: the command line imports it.
`HookContext.started_by` and `HookContext.tickets_on_branch` load them when they are called, and
only the dispatch of an implementer calls them. Neither opens the state of a repository that has no
ticket directory, a directory under `.mightymodels/` other than the archives, at the project
directory or above it: such a repository has no ticket, so its answer is no task and no ticket.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from mightymodels_plugin.commands.dispatch_hook import (
    PLUGIN_PREFIX,
    BranchTickets,
    BranchTicketsOrUnreadable,
    StartedOrUnreadable,
    decoded_object,
    worker_named,
)
from mightymodels_plugin.core.data_directory import (
    PLUGIN_DATA_VARIABLE,
    DataDirectory,
    data_directory_from,
)
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import Worker

AGENT_TYPE_KEY = 'agent_type'


class UnreadableHookInputError(StateError):
    def __init__(self) -> None:
        super().__init__('the hook input is not a JSON object')


@dataclass(slots=True, kw_only=True, frozen=True)
class HookContext:
    stdin: TextIO
    environ: Mapping[str, str]
    cwd: Path

    def fields(self) -> dict[str, object] | UnreadableHookInputError:
        try:
            text = self.stdin.read()
        except (OSError, UnicodeDecodeError):
            return UnreadableHookInputError()
        decoded = decoded_object(text)
        return UnreadableHookInputError() if decoded is None else decoded

    def data_directory(self) -> DataDirectory:
        return data_directory_from(self.environ, PLUGIN_DATA_VARIABLE)

    def has_ticket_directory(self) -> bool:
        from mightymodels_plugin.core.slug import ARCHIVES_DIRECTORY  # noqa: PLC0415 - core.workspace on the next line loads core.slug, so this import is paid with that one
        from mightymodels_plugin.core.workspace import STATE_DIRECTORY, find_root  # noqa: PLC0415 - importing core.workspace (Pydantic) took 0.094 s on top of cli, the lowest of 3 runs measured with -X importtime, and a dispatch that reads no state must not pay it

        start = find_root(self.environ, self.cwd)
        return any(
            ticket_directories(directory.joinpath(STATE_DIRECTORY), ARCHIVES_DIRECTORY)
            for directory in (start, *start.parents)
        )

    def started_by(self, worker: Worker) -> StartedOrUnreadable:
        if not self.has_ticket_directory():
            return ()
        from mightymodels_plugin.commands.started_tasks import started_for_hook  # noqa: PLC0415 - importing commands.started_tasks (SQLAlchemy and Pydantic) took 0.47 s on top of cli, the lowest of 3 runs measured with -X importtime, and every dispatch of another type must not pay it

        return started_for_hook(self, worker)

    def tickets_on_branch(self) -> BranchTicketsOrUnreadable:
        if not self.has_ticket_directory():
            return BranchTickets()
        from mightymodels_plugin.commands.started_tasks import tickets_for_hook  # noqa: PLC0415 - commands.started_tasks is the import `started_by` defers, for the reason given there

        return tickets_for_hook(self)


def ticket_directories(state_directory: Path, archives: str) -> list[Path]:
    if not state_directory.is_dir():
        return []
    return [
        entry for entry in state_directory.iterdir() if entry.is_dir() and entry.name != archives
    ]


def plugin_worker(fields: Mapping[str, object]) -> Worker | None:
    agent_type = fields.get(AGENT_TYPE_KEY)
    if not isinstance(agent_type, str) or not agent_type.startswith(PLUGIN_PREFIX):
        return None
    return worker_named(agent_type)

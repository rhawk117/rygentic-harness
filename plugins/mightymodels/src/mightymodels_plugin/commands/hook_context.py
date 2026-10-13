"""What a hook command is given: Claude Code's JSON on standard input, the environment and the
directory the session started in.

A hook command never refuses. When it cannot work it says why on standard error and exits 0
(`rejection.skipped`), because exit code 2 keeps a subagent from stopping or a compaction from
running.

`HookContext.has_ticket_directory` says whether the repository has a ticket directory: a directory
under `.mightymodels/` other than the archives, at the project directory or above it. A repository
without one has no ticket.

`HookContext.ticket_directory_holds` says whether a path is in a ticket directory, existing or
not. It compares the resolved path, so a relative path counts from the working directory, and `..`
or a symbolic link that leads out of the directory leads out of the answer too.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from mightymodels_plugin.commands.dispatch_hook import PLUGIN_PREFIX, decoded_object, worker_named
from mightymodels_plugin.core.data_directory import (
    PLUGIN_DATA_VARIABLE,
    DataDirectory,
    data_directory_from,
)
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import Worker
from mightymodels_plugin.core.slug import ARCHIVES_DIRECTORY
from mightymodels_plugin.core.workspace import STATE_DIRECTORY, find_root

AGENT_TYPE_KEY = 'agent_type'
NUL = '\0'


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

    def state_directories(self) -> list[Path]:
        start = find_root(self.environ, self.cwd)
        return [directory.joinpath(STATE_DIRECTORY) for directory in (start, *start.parents)]

    def has_ticket_directory(self) -> bool:
        return any(
            ticket_directories(state_directory, ARCHIVES_DIRECTORY)
            for state_directory in self.state_directories()
        )

    def ticket_directory_holds(self, file_path: str) -> bool:
        if NUL in file_path:
            return False
        resolved = self.cwd.joinpath(file_path).resolve()
        return any(
            in_a_ticket_directory(resolved, state_directory.resolve(), ARCHIVES_DIRECTORY)
            for state_directory in self.state_directories()
        )


def ticket_directories(state_directory: Path, archives: str) -> list[Path]:
    if not state_directory.is_dir():
        return []
    return [
        entry for entry in state_directory.iterdir() if entry.is_dir() and entry.name != archives
    ]


def in_a_ticket_directory(resolved: Path, state_directory: Path, archives: str) -> bool:
    if not resolved.is_relative_to(state_directory):
        return False
    below = resolved.relative_to(state_directory).parts
    return len(below) > 1 and below[0] != archives


def plugin_worker(fields: Mapping[str, object]) -> Worker | None:
    agent_type = fields.get(AGENT_TYPE_KEY)
    if not isinstance(agent_type, str) or not agent_type.startswith(PLUGIN_PREFIX):
        return None
    return worker_named(agent_type)

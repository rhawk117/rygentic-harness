"""The `mightymodels session-start` command, which the plugin's SessionStart hook runs.

A command run through the Bash tool has none of the plugin's variables, so `verify run` could not
find the state database the server opened. The hook has the data directory and the session's env
file, and Claude Code sets what that file exports in every later Bash command of the session, a
subagent's included. The command appends one line there, the export of the data directory, unless
the file already holds that line, and does nothing else: it creates no directory and prints
nothing. A last line that has no newline is read as a whole line:
when it is the export the file is left as it is, and when it is anything else the command ends it
with a newline first, so the export starts a line of its own. The file is read and written with no
newline translation and the export is looked for as the text the command writes, where a line
starts, so one whose directory name holds a newline, a form feed or a carriage return is found as
well. When the variable or the env file is missing it says so on standard error and exits 0.
"""

from collections.abc import Mapping
from pathlib import Path

from mightymodels.commands.rejection import skipped
from mightymodels.core.data_directory import (
    PLUGIN_DATA_VARIABLE,
    DataDirectoryMissingError,
    data_directory_from,
    export_line,
)
from mightymodels.core.errors import StateError

ENV_FILE_VARIABLE = 'CLAUDE_ENV_FILE'


class EnvFileMissingError(StateError):
    def __init__(self) -> None:
        super().__init__(
            f'{ENV_FILE_VARIABLE} is not set, so there is no session env file to export the '
            'plugin data directory to; Claude Code sets it for a SessionStart hook'
        )


def export_data_directory(environ: Mapping[str, str]) -> int:
    data_directory = data_directory_from(environ, PLUGIN_DATA_VARIABLE)
    if isinstance(data_directory, DataDirectoryMissingError):
        return skipped(data_directory)
    env_file = environ.get(ENV_FILE_VARIABLE, '')
    if not env_file:
        return skipped(EnvFileMissingError())
    line = export_line(data_directory)
    exports = Path(env_file)
    held = exports.read_text(encoding='utf-8', newline='') if exports.is_file() else ''
    missing_newline = '\n' if held and not held.endswith('\n') else ''
    whole_lines = f'{held}{missing_newline}'
    if whole_lines.startswith(line) or f'\n{line}' in whole_lines:
        return 0
    with exports.open('a', encoding='utf-8', newline='') as file:
        file.write(f'{missing_newline}{line}')
    return 0

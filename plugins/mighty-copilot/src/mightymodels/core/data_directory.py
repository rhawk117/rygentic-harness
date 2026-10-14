"""The plugin data directory, where the state database is kept, and how each edge learns it.

Claude Code sets `PLUGIN_DATA_VARIABLE` for the plugin's MCP server and for its hook commands, and
for nothing started through the Bash tool. `verify run` reads `SESSION_DATA_VARIABLE`, a name of
this plugin's own, so a second plugin's `PLUGIN_DATA_VARIABLE` is never mistaken for it.

Each edge reads exactly one of the two and there is no fallback from one to the other. An unset
or empty variable is the absence the edge refuses on, naming the variable.
"""

from collections.abc import Mapping
from pathlib import Path

from mightymodels.core.errors import StateError

PLUGIN_DATA_VARIABLE = 'CLAUDE_PLUGIN_DATA'
SESSION_DATA_VARIABLE = 'MIGHTYMODELS_DATA_DIR'


class DataDirectoryMissingError(StateError):
    def __init__(self, variable: str) -> None:
        super().__init__(
            f'{variable} is not set, so there is no plugin data directory to keep the state '
            f'database in; Claude Code sets {PLUGIN_DATA_VARIABLE} for the state server, and the '
            f'commands a session runs read {SESSION_DATA_VARIABLE}'
        )
        self.variable = variable


type DataDirectory = Path | DataDirectoryMissingError


def data_directory_from(environ: Mapping[str, str], variable: str) -> DataDirectory:
    directory = environ.get(variable, '')
    return Path(directory) if directory else DataDirectoryMissingError(variable)

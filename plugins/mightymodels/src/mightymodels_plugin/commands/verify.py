"""The `mightymodels verify run` command: the one way an approved contract command executes.

The command is its own edge: it opens the state as the server's lifespan does, the workspace at
the git toplevel and the database in the plugin data directory, builds the contract service over
the two, and disposes the engine before it returns. It loads no MCP module.

It refuses before it creates anything when the data directory, git or the work tree is missing:
the reason goes to standard error, naming what is missing, and the exit code says refused. The
data directory comes from the variable the plugin's SessionStart hook exports, because a command
run through the Bash tool has none of the plugin's own.
"""

import argparse
import os
import sys
from pathlib import Path

from mightymodels_plugin.commands.rejection import rejected
from mightymodels_plugin.core.data_directory import SESSION_DATA_VARIABLE, data_directory_from
from mightymodels_plugin.core.edge import open_state
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.slug import InvalidSlugError, parsed_slug
from mightymodels_plugin.core.workspace import find_root
from mightymodels_plugin.tools.contract.schema import Phase
from mightymodels_plugin.tools.contract.service import ContractService, RunRequest
from mightymodels_plugin.tools.row_types import ROW_TYPES

EXIT_FAILED = 1


def verify_run(arguments: argparse.Namespace) -> int:
    slug = parsed_slug(arguments.slug)
    if isinstance(slug, InvalidSlugError):
        return rejected(slug)
    ids = None if arguments.all else tuple(arguments.id)
    request = RunRequest(ids=ids, phase=Phase(arguments.phase))
    start = find_root(os.environ, Path.cwd())
    data_directory = data_directory_from(os.environ, SESSION_DATA_VARIABLE)
    try:
        with open_state(start, data_directory, ROW_TYPES) as state:
            contracts = ContractService(workspace=state.workspace, database=state.database)
            result = contracts.run_approved(slug, request)
    except StateError as error:
        return rejected(error)
    sys.stdout.write(result.text)
    return 0 if result.passed else EXIT_FAILED

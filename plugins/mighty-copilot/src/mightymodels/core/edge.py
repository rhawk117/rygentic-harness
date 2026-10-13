"""What both edges do first: find the repository, name it, and open the database for it.

The server's lifespan and `verify run` start in whatever directory the session did. `open_state`
takes that directory, the plugin data directory the edge read from its environment and the row
types the database holds a table for, and hands out the workspace at the git toplevel, the git
that answers there, the database opened under that repository's key, and the data directory itself
for the spool beside the database. So the two edges of one session open the same file and see the
same rows.

Every refusal comes before anything is created: no data directory, no git executable, no work
tree, and a database file of another schema version. Each is a `StateError` naming what is
missing, which the edge shows its caller. An origin remote that is not an owner and a name is no
refusal: that repository is keyed by its toplevel path. Only with the database open is
`.mightymodels/` excluded from git, before anything is written there.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from mightymodels.core.data_directory import DataDirectory, DataDirectoryMissingError
from mightymodels.core.database import DATABASE_NAME, Database, RowTypes, open_database
from mightymodels.core.workspace import (
    Checkout,
    Git,
    Workspace,
    exclude_state,
    git_at,
    workspace_of,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class OpenState:
    workspace: Workspace
    git: Git
    database: Database
    data_directory: Path


def exclude_state_from_git(git: Git) -> None:
    common_directory = git.common_directory()
    if common_directory is None:
        return
    exclude_state(common_directory)


@contextmanager
def open_state(
    start: Path, data_directory: DataDirectory, row_types: RowTypes
) -> Generator[OpenState]:
    if isinstance(data_directory, DataDirectoryMissingError):
        raise data_directory
    started = git_at(start)
    checkout = started.checkout()
    if not isinstance(checkout, Checkout):
        raise checkout
    repository_key = checkout.repository_key()
    git = replace(started, root=checkout.toplevel)
    database_file = data_directory.joinpath(DATABASE_NAME)
    with open_database(database_file, repository_key, row_types) as database:
        exclude_state_from_git(git)
        yield OpenState(
            workspace=workspace_of(checkout.toplevel),
            git=git,
            database=database,
            data_directory=data_directory,
        )

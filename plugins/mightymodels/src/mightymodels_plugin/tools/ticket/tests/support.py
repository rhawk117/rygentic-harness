from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.workspace import Workspace, workspace_at
from mightymodels_plugin.tools.tests.support import workspace_database
from mightymodels_plugin.tools.ticket.service import TicketService


@contextmanager
def ticket_service_at(root: Path, data_directory: Path) -> Generator[TicketService]:
    workspace = workspace_at(root)
    workspace.exclude_state_from_git()
    with workspace_database(workspace, data_directory) as database:
        yield TicketService(workspace=workspace, database=database)


@pytest.fixture
def ticket_service(repository_workspace: Workspace, repository_database: Database) -> TicketService:
    return TicketService(workspace=repository_workspace, database=repository_database)

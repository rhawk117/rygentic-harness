from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.core.workspace import Workspace, workspace_at
from mightymodels_plugin.tools.tests.support import workspace_database
from mightymodels_plugin.tools.ticket.repository import ticket_store
from mightymodels_plugin.tools.ticket.service import TicketService
from mightymodels_plugin.tools.ticket.tests.in_memory import InMemoryTicketStore


@contextmanager
def ticket_service_at(root: Path, data_directory: Path) -> Generator[TicketService]:
    workspace = workspace_at(root)
    workspace.exclude_state_from_git()
    with workspace_database(workspace, data_directory) as database:
        yield TicketService(workspace=workspace, store=ticket_store(database), git=workspace.git)


@pytest.fixture
def ticket_service(repository_workspace: Workspace, repository_database: Database) -> TicketService:
    return TicketService(
        workspace=repository_workspace,
        store=ticket_store(repository_database),
        git=repository_workspace.git,
    )


@pytest.fixture
def in_memory_ticket_store() -> InMemoryTicketStore:
    return InMemoryTicketStore()


@pytest.fixture
def in_memory_ticket_service(
    gitless_workspace: Workspace,
    in_memory_ticket_store: InMemoryTicketStore,
    in_memory_git: InMemoryGit,
) -> TicketService:
    return TicketService(
        workspace=gitless_workspace, store=in_memory_ticket_store, git=in_memory_git
    )

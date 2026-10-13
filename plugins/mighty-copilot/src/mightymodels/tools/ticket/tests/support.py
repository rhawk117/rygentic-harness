from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from mightymodels.core.database import Database
from mightymodels.core.edge import exclude_state_from_git
from mightymodels.core.tests.in_memory_git import InMemoryGit
from mightymodels.core.workspace import Git, Workspace, git_at, workspace_at
from mightymodels.tools.tests.support import workspace_database
from mightymodels.tools.ticket.repository import ticket_store
from mightymodels.tools.ticket.service import TicketService
from mightymodels.tools.ticket.tests.in_memory import InMemoryTicketStore


@contextmanager
def ticket_service_at(root: Path, data_directory: Path) -> Generator[TicketService]:
    git = git_at(root)
    exclude_state_from_git(git)
    workspace = workspace_at(root)
    with workspace_database(workspace, data_directory) as database:
        yield TicketService(workspace=workspace, store=ticket_store(database), git=git)


@pytest.fixture
def ticket_service(
    repository_workspace: Workspace, repository_database: Database, repository_git: Git
) -> TicketService:
    return TicketService(
        workspace=repository_workspace,
        store=ticket_store(repository_database),
        git=repository_git,
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

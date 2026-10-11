import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.core.workspace import Git, Workspace
from mightymodels_plugin.tools.contract.tests.in_memory import InMemoryContractStore
from mightymodels_plugin.tools.task.repository import task_store
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.task.tests.in_memory import InMemoryTaskStore
from mightymodels_plugin.tools.ticket.tests.in_memory import InMemoryTicketStore


@pytest.fixture
def task_service(
    repository_workspace: Workspace, repository_database: Database, repository_git: Git
) -> TaskService:
    return TaskService(
        workspace=repository_workspace,
        store=task_store(repository_database),
        git=repository_git,
    )


@pytest.fixture
def in_memory_task_store(
    in_memory_ticket_store: InMemoryTicketStore, in_memory_contract_store: InMemoryContractStore
) -> InMemoryTaskStore:
    return InMemoryTaskStore(tickets=in_memory_ticket_store, contracts=in_memory_contract_store)


@pytest.fixture
def in_memory_task_service(
    gitless_workspace: Workspace,
    in_memory_task_store: InMemoryTaskStore,
    in_memory_git: InMemoryGit,
) -> TaskService:
    return TaskService(workspace=gitless_workspace, store=in_memory_task_store, git=in_memory_git)

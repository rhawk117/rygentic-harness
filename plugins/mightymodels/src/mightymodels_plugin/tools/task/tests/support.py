import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.core.workspace import Git, Workspace
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.contract.tests.in_memory import InMemoryContractStore
from mightymodels_plugin.tools.task.repository import task_store
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.task.tests.in_memory import InMemoryTaskStore
from mightymodels_plugin.tools.task.tests.repo import ANSWERS, TICKET, TaskRepo
from mightymodels_plugin.tools.ticket.service import TicketService
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


@pytest.fixture
def task_repo_without_a_commit_or_a_ticket(
    in_memory_task_service: TaskService,
    in_memory_contract_service: ContractService,
    in_memory_task_store: InMemoryTaskStore,
    in_memory_git: InMemoryGit,
) -> TaskRepo:
    return TaskRepo(
        tasks=in_memory_task_service,
        contracts=in_memory_contract_service,
        store=in_memory_task_store,
        history=in_memory_git,
    )


@pytest.fixture
def unstaged_task_repo(task_repo_without_a_commit_or_a_ticket: TaskRepo) -> TaskRepo:
    task_repo_without_a_commit_or_a_ticket.commit('src/queue.py')
    return task_repo_without_a_commit_or_a_ticket


@pytest.fixture
def task_repo(unstaged_task_repo: TaskRepo, in_memory_ticket_service: TicketService) -> TaskRepo:
    in_memory_ticket_service.write(TICKET, ANSWERS)
    in_memory_ticket_service.validate(TICKET)
    return unstaged_task_repo


@pytest.fixture
def unborn_task_repo(
    task_repo_without_a_commit_or_a_ticket: TaskRepo, in_memory_ticket_service: TicketService
) -> TaskRepo:
    in_memory_ticket_service.write(TICKET, ANSWERS)
    in_memory_ticket_service.validate(TICKET)
    return task_repo_without_a_commit_or_a_ticket

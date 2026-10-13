import pytest

from mightymodels.core.database import Database
from mightymodels.core.tests.in_memory_git import InMemoryGit
from mightymodels.core.workspace import Git, Workspace
from mightymodels.tools.close.repository import close_store
from mightymodels.tools.close.service import CloseService
from mightymodels.tools.close.tests.in_memory import InMemoryCloseStore
from mightymodels.tools.close.tests.repo import CloseRepo
from mightymodels.tools.contract.service import ContractService
from mightymodels.tools.review.service import ReviewService
from mightymodels.tools.snapshot.tests.in_memory import InMemorySnapshotStore
from mightymodels.tools.ticket.service import TicketService


@pytest.fixture
def close_service(
    repository_workspace: Workspace, repository_database: Database, repository_git: Git
) -> CloseService:
    return CloseService(
        workspace=repository_workspace,
        store=close_store(repository_database),
        git=repository_git,
    )


@pytest.fixture
def in_memory_close_store(in_memory_snapshot_store: InMemorySnapshotStore) -> InMemoryCloseStore:
    return InMemoryCloseStore(snapshot=in_memory_snapshot_store)


@pytest.fixture
def in_memory_close_service(
    gitless_workspace: Workspace,
    in_memory_close_store: InMemoryCloseStore,
    in_memory_git: InMemoryGit,
) -> CloseService:
    return CloseService(workspace=gitless_workspace, store=in_memory_close_store, git=in_memory_git)


@pytest.fixture
def staged_close_repo(
    in_memory_close_service: CloseService,
    in_memory_ticket_service: TicketService,
    in_memory_contract_service: ContractService,
    in_memory_review_service: ReviewService,
    in_memory_git: InMemoryGit,
    ticket_branch: str,
) -> CloseRepo:
    space = CloseRepo(
        closings=in_memory_close_service,
        tickets=in_memory_ticket_service,
        contracts=in_memory_contract_service,
        reviews=in_memory_review_service,
        git=in_memory_git,
    )
    space.stage(ticket_branch)
    space.approve_with_a_passing_receipt('T1.AC-1', ('uv', 'run', 'pytest'))
    return space


@pytest.fixture
def committed_close_repo(staged_close_repo: CloseRepo) -> CloseRepo:
    staged_close_repo.git.commit('queue.py')
    return staged_close_repo


@pytest.fixture
def close_repo(committed_close_repo: CloseRepo) -> CloseRepo:
    committed_close_repo.record_verified_work()
    return committed_close_repo

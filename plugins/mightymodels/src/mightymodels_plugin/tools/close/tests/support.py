import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.core.workspace import Git, Workspace
from mightymodels_plugin.tools.close.repository import close_store
from mightymodels_plugin.tools.close.service import CloseService
from mightymodels_plugin.tools.close.tests.in_memory import InMemoryCloseStore
from mightymodels_plugin.tools.snapshot.tests.in_memory import InMemorySnapshotStore


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

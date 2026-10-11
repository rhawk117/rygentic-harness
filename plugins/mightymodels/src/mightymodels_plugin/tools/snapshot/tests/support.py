import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.core.workspace import Git, Workspace
from mightymodels_plugin.tools.investigation.tests.in_memory import InMemoryInvestigationStore
from mightymodels_plugin.tools.review.tests.in_memory import InMemoryReviewStore
from mightymodels_plugin.tools.snapshot.repository import snapshot_store
from mightymodels_plugin.tools.snapshot.service import SnapshotService
from mightymodels_plugin.tools.snapshot.tests.in_memory import InMemorySnapshotStore
from mightymodels_plugin.tools.task.tests.in_memory import InMemoryTaskStore


@pytest.fixture
def snapshot_service(
    repository_workspace: Workspace, repository_database: Database, repository_git: Git
) -> SnapshotService:
    return SnapshotService(
        workspace=repository_workspace,
        store=snapshot_store(repository_database),
        git=repository_git,
    )


@pytest.fixture
def in_memory_snapshot_store(
    in_memory_task_store: InMemoryTaskStore,
    in_memory_review_store: InMemoryReviewStore,
    in_memory_investigation_store: InMemoryInvestigationStore,
) -> InMemorySnapshotStore:
    return InMemorySnapshotStore(
        tasks=in_memory_task_store,
        reviews=in_memory_review_store,
        investigations=in_memory_investigation_store,
    )


@pytest.fixture
def in_memory_snapshot_service(
    gitless_workspace: Workspace,
    in_memory_snapshot_store: InMemorySnapshotStore,
    in_memory_git: InMemoryGit,
) -> SnapshotService:
    return SnapshotService(
        workspace=gitless_workspace, store=in_memory_snapshot_store, git=in_memory_git
    )

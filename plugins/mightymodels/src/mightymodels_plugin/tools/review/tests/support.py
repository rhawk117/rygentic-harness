import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.tools.review.repository import review_store
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.review.tests.in_memory import InMemoryReviewStore
from mightymodels_plugin.tools.similarity.tests.in_memory import InMemorySimilarityStore


@pytest.fixture
def review_service(repository_workspace: Workspace, repository_database: Database) -> ReviewService:
    return ReviewService(
        workspace=repository_workspace,
        store=review_store(repository_database),
        git=repository_workspace.git,
    )


@pytest.fixture
def in_memory_review_store(
    in_memory_similarity_store: InMemorySimilarityStore,
) -> InMemoryReviewStore:
    return InMemoryReviewStore(similarity=in_memory_similarity_store)


@pytest.fixture
def in_memory_review_service(
    gitless_workspace: Workspace,
    in_memory_review_store: InMemoryReviewStore,
    in_memory_git: InMemoryGit,
) -> ReviewService:
    return ReviewService(
        workspace=gitless_workspace, store=in_memory_review_store, git=in_memory_git
    )

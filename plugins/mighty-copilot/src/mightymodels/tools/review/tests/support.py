import pytest

from mightymodels.core.database import Database
from mightymodels.core.tests.in_memory_git import InMemoryGit
from mightymodels.core.workspace import Git, Workspace
from mightymodels.tools.review.repository import review_store
from mightymodels.tools.review.service import ReviewService
from mightymodels.tools.review.tests.in_memory import InMemoryReviewStore
from mightymodels.tools.review.tests.workspace import Workspace as ReviewWorkspace
from mightymodels.tools.similarity.tests.in_memory import InMemorySimilarityStore


@pytest.fixture
def review_service(
    repository_workspace: Workspace, repository_database: Database, repository_git: Git
) -> ReviewService:
    return ReviewService(
        workspace=repository_workspace,
        store=review_store(repository_database),
        git=repository_git,
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


@pytest.fixture
def review_workspace(
    in_memory_review_service: ReviewService, in_memory_git: InMemoryGit
) -> ReviewWorkspace:
    return ReviewWorkspace(reviews=in_memory_review_service, git=in_memory_git)

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.core.workspace import Workspace, workspace_at
from mightymodels_plugin.tools.investigation.repository import investigation_store
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.investigation.tests.in_memory import InMemoryInvestigationStore
from mightymodels_plugin.tools.similarity.tests.in_memory import InMemorySimilarityStore
from mightymodels_plugin.tools.tests.support import workspace_database


@contextmanager
def investigation_service_at(root: Path, data_directory: Path) -> Generator[InvestigationService]:
    workspace = workspace_at(root)
    workspace.exclude_state_from_git()
    with workspace_database(workspace, data_directory) as database:
        yield InvestigationService(store=investigation_store(database), git=workspace.git)


@pytest.fixture
def investigation_service(
    repository_workspace: Workspace, repository_database: Database
) -> InvestigationService:
    return InvestigationService(
        store=investigation_store(repository_database), git=repository_workspace.git
    )


@pytest.fixture
def in_memory_investigation_store(
    in_memory_similarity_store: InMemorySimilarityStore,
) -> InMemoryInvestigationStore:
    return InMemoryInvestigationStore(similarity=in_memory_similarity_store)


@pytest.fixture
def in_memory_investigation_service(
    in_memory_investigation_store: InMemoryInvestigationStore, in_memory_git: InMemoryGit
) -> InvestigationService:
    return InvestigationService(store=in_memory_investigation_store, git=in_memory_git)

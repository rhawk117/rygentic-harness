from pathlib import Path

import pytest

from mightymodels.core.database import Database
from mightymodels.core.repository_key import local_key
from mightymodels.core.workspace import Workspace
from mightymodels.tools.similarity.repository import similarity_store
from mightymodels.tools.similarity.service import SimilarityService
from mightymodels.tools.similarity.spool import SPOOL_DIRECTORY
from mightymodels.tools.similarity.tests.in_memory import InMemorySimilarityStore
from mightymodels.tools.tests.support import repository_key_of


@pytest.fixture
def spool(data_directory: Path) -> Path:
    return data_directory.joinpath(SPOOL_DIRECTORY)


@pytest.fixture
def similarity_service(repository_database: Database, spool: Path) -> SimilarityService:
    return SimilarityService(
        store=similarity_store(repository_database),
        spool=spool,
        repository_key=repository_database.repository_key,
    )


@pytest.fixture
def in_memory_similarity_store() -> InMemorySimilarityStore:
    return InMemorySimilarityStore()


@pytest.fixture
def in_memory_similarity_service(
    in_memory_similarity_store: InMemorySimilarityStore, tmp_path: Path
) -> SimilarityService:
    return SimilarityService(
        store=in_memory_similarity_store,
        spool=tmp_path.joinpath(SPOOL_DIRECTORY),
        repository_key=local_key(tmp_path),
    )


@pytest.fixture
def similarity_own_key(repository_workspace: Workspace) -> str:
    return repository_key_of(repository_workspace).root

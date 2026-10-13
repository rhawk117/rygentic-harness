import pytest

from mightymodels.core.database import Database
from mightymodels.tools.crashout.repository import crashout_store
from mightymodels.tools.crashout.service import CrashoutService
from mightymodels.tools.crashout.tests.in_memory import InMemoryCrashoutStore
from mightymodels.tools.similarity.tests.in_memory import InMemorySimilarityStore


@pytest.fixture
def crashout_service(repository_database: Database) -> CrashoutService:
    return CrashoutService(store=crashout_store(repository_database))


@pytest.fixture
def in_memory_crashout_store(
    in_memory_similarity_store: InMemorySimilarityStore,
) -> InMemoryCrashoutStore:
    return InMemoryCrashoutStore(similarity=in_memory_similarity_store)


@pytest.fixture
def in_memory_crashout_service(in_memory_crashout_store: InMemoryCrashoutStore) -> CrashoutService:
    return CrashoutService(store=in_memory_crashout_store)

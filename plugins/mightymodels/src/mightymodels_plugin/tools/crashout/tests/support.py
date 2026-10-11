import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.tools.crashout.repository import crashout_store
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.crashout.tests.in_memory import InMemoryCrashoutStore
from mightymodels_plugin.tools.similarity.tests.in_memory import InMemorySimilarityStore


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

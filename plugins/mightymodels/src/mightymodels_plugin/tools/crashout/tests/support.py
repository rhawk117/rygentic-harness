import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.tools.crashout.service import CrashoutService


@pytest.fixture
def crashout_service(repository_database: Database) -> CrashoutService:
    return CrashoutService(database=repository_database)

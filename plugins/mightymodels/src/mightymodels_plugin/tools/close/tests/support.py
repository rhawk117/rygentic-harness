import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.tools.close.service import CloseService


@pytest.fixture
def close_service(repository_workspace: Workspace, repository_database: Database) -> CloseService:
    return CloseService(workspace=repository_workspace, database=repository_database)

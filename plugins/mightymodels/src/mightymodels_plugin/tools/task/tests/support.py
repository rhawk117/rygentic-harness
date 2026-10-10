import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.tools.task.service import TaskService


@pytest.fixture
def task_service(repository_workspace: Workspace, repository_database: Database) -> TaskService:
    return TaskService(workspace=repository_workspace, database=repository_database)

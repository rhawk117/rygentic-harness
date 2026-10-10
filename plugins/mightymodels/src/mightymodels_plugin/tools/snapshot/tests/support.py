import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.tools.snapshot.service import SnapshotService


@pytest.fixture
def snapshot_service(
    repository_workspace: Workspace, repository_database: Database
) -> SnapshotService:
    return SnapshotService(workspace=repository_workspace, database=repository_database)

import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.tools.review.service import ReviewService


@pytest.fixture
def review_service(repository_workspace: Workspace, repository_database: Database) -> ReviewService:
    return ReviewService(workspace=repository_workspace, database=repository_database)

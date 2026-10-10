from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.workspace import Workspace, workspace_at
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.tests.support import workspace_database


@contextmanager
def investigation_service_at(root: Path, data_directory: Path) -> Generator[InvestigationService]:
    workspace = workspace_at(root)
    workspace.exclude_state_from_git()
    with workspace_database(workspace, data_directory) as database:
        yield InvestigationService(workspace=workspace, database=database)


@pytest.fixture
def investigation_service(
    repository_workspace: Workspace, repository_database: Database
) -> InvestigationService:
    return InvestigationService(workspace=repository_workspace, database=repository_database)

import pytest

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.workspace import Workspace
from mightymodels_plugin.tools.contract.service import ContractService


@pytest.fixture
def contract_service(
    repository_workspace: Workspace, repository_database: Database
) -> ContractService:
    return ContractService(workspace=repository_workspace, database=repository_database)

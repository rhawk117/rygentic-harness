import pytest

from mightymodels.core.database import Database
from mightymodels.core.process import process_runner
from mightymodels.core.tests.in_memory_git import InMemoryGit
from mightymodels.core.workspace import Git, Workspace
from mightymodels.tools.contract.repository import contract_store
from mightymodels.tools.contract.service import ContractService
from mightymodels.tools.contract.tests.in_memory import InMemoryContractStore


@pytest.fixture
def contract_service(
    repository_workspace: Workspace, repository_database: Database, repository_git: Git
) -> ContractService:
    return ContractService(
        workspace=repository_workspace,
        store=contract_store(repository_database),
        git=repository_git,
        processes=process_runner(),
    )


@pytest.fixture
def in_memory_contract_store() -> InMemoryContractStore:
    return InMemoryContractStore()


@pytest.fixture
def in_memory_contract_service(
    gitless_workspace: Workspace,
    in_memory_contract_store: InMemoryContractStore,
    in_memory_git: InMemoryGit,
) -> ContractService:
    return ContractService(
        workspace=gitless_workspace,
        store=in_memory_contract_store,
        git=in_memory_git,
        processes=process_runner(),
    )

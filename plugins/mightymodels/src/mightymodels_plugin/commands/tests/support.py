from pathlib import Path

import pytest

from mightymodels_plugin.commands.tests.hook_inputs import Hook
from mightymodels_plugin.commands.tests.ticket_checkout import BRANCH, TICKET, TicketCheckout
from mightymodels_plugin.core.data_directory import PLUGIN_DATA_VARIABLE
from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.tests.support import GitRunner
from mightymodels_plugin.core.workspace import PROJECT_DIR_VARIABLE
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.ticket.service import TicketService


@pytest.fixture
def hook_command(
    hook_repository: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Hook:
    return Hook(repository=hook_repository, monkeypatch=monkeypatch, capsys=capsys)


@pytest.fixture
def hook_repository(
    repository: Path, data_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setenv(PLUGIN_DATA_VARIABLE, str(data_directory))
    monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(repository))
    return repository


@pytest.fixture
def ticket_checkout(
    hook_repository: Path,
    ticket_service: TicketService,
    contract_service: ContractService,
    repository_database: Database,
    git: GitRunner,
) -> TicketCheckout:
    return TicketCheckout(
        root=hook_repository,
        tickets=ticket_service,
        contracts=contract_service,
        database=repository_database,
        runner=git,
    )


@pytest.fixture
def checked_out_ticket(ticket_checkout: TicketCheckout) -> TicketCheckout:
    ticket_checkout.git('symbolic-ref', 'HEAD', f'refs/heads/{BRANCH}')
    ticket_checkout.stage(TICKET)
    ticket_checkout.commit()
    return ticket_checkout

"""The command line of `verify run` takes ids and never a command line of its own.

This test moved whole from test_contract_service.py, which runs the contract service on the store
kept in memory. It drives `mightymodels verify run` itself, so it stands on a real repository and
a SQLite store.
"""

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sql
from mightymodels.cli import main
from mightymodels.core.data_directory import SESSION_DATA_VARIABLE
from mightymodels.core.database import Database
from mightymodels.core.errors import StateError
from mightymodels.core.slug import Slug
from mightymodels.tools.contract.schema import ContractCommand
from mightymodels.tools.contract.service import ContractService
from mightymodels.tools.contract.tables import ReceiptRow
from pydantic import ValidationError

SLUG = 'retry-queue'
PASSED, REJECTED = 0, 2
PYTHON = sys.executable


def python(code: str, *args: str) -> list[str]:
    return [PYTHON, '-c', code, *args]


@dataclass(frozen=True, slots=True, kw_only=True)
class Outcome:
    code: int
    out: str
    err: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Workspace:
    contracts: ContractService
    database: Database
    capsys: pytest.CaptureFixture[str]

    @property
    def root(self) -> Path:
        return self.contracts.workspace.root

    def run(self, *argv: str, slug: str = SLUG) -> Outcome:
        code = main(['verify', 'run', '--slug', slug, *argv])
        captured = self.capsys.readouterr()
        return Outcome(code=code, out=captured.out, err=captured.err)

    def approve(self, *commands: Mapping[str, object], slug: str = SLUG) -> Outcome:
        try:
            approved = [
                ContractCommand.model_validate({'approved_by': 'user', **command})
                for command in commands
            ]
            view = self.contracts.approve(Slug(slug), approved)
        except (StateError, ValidationError) as error:
            return Outcome(code=REJECTED, out='', err=str(error))
        return Outcome(code=PASSED, out=view.text, err='')

    def receipts(self) -> list[str]:
        query = sql.select(ReceiptRow.command_id).order_by(ReceiptRow.id)
        with self.database.transaction() as session:
            return list(session.scalars(query))


@pytest.fixture
def workspace(
    contract_service: ContractService,
    repository_database: Database,
    data_directory: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Workspace:
    monkeypatch.chdir(str(contract_service.workspace.root))
    monkeypatch.setenv(SESSION_DATA_VARIABLE, str(data_directory))
    return Workspace(contracts=contract_service, database=repository_database, capsys=capsys)


class TestVerifyRunAllowlist:
    MARKER = 'ran.txt'

    def touch(self, *arguments: str) -> list[str]:
        code = (
            'import sys; from pathlib import Path; '
            f'Path({self.MARKER!r}).write_text(" ".join(sys.argv[1:]))'
        )
        return python(code, *arguments)

    def test_verify_run_allowlist_takes_ids_and_never_a_command_line(
        self, workspace: Workspace
    ) -> None:
        workspace.approve({'id': 'T1.AC-1', 'argv': python('print(1)')})

        with pytest.raises(SystemExit) as exit_info:
            workspace.run('--id', 'T1.AC-1', '--', *self.touch())

        assert exit_info.value.code == REJECTED
        assert not workspace.root.joinpath(self.MARKER).exists()
        assert workspace.receipts() == []

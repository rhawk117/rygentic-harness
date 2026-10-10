import os
import subprocess
import sys
from pathlib import Path

import pytest
from mightymodels_plugin.cli import build_parser, main
from mightymodels_plugin.core.data_directory import SESSION_DATA_VARIABLE
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import PROJECT_DIR_VARIABLE
from mightymodels_plugin.tools.contract.schema import ContractCommand
from mightymodels_plugin.tools.contract.service import ContractService
from pytest_mock import MockerFixture

SLUG = 'retry-queue'
LOADED_PACKAGES = (
    'import sys\n'
    'from mightymodels_plugin.cli import main\n'
    'try:\n'
    '    code = main(sys.argv[1:])\n'
    'except SystemExit as stop:\n'
    '    code = stop.code\n'
    "heavy = {'mcp', 'sqlalchemy', 'pydantic'}\n"
    'print(code, sorted(heavy.intersection(sys.modules)))\n'
)


def loaded_packages(root: Path, data_directory: Path, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - this interpreter runs the package's own entry point with fixed arguments
        [sys.executable, '-c', LOADED_PACKAGES, *arguments],
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
        env={
            **os.environ,
            PROJECT_DIR_VARIABLE: str(root),
            SESSION_DATA_VARIABLE: str(data_directory),
        },
    )
    return completed.stdout.splitlines()[-1]


class TestCli:
    def test_help_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            build_parser().parse_args(['--help'])

        assert exit_info.value.code == 0
        assert 'serve' in capsys.readouterr().out

    def test_a_command_is_required(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main([])

        assert exit_info.value.code == 2
        assert 'usage: mightymodels' in capsys.readouterr().err

    def test_serve_starts_the_server(self, mocker: MockerFixture) -> None:
        serve = mocker.patch('mightymodels_plugin.server.serve')

        assert main(['serve']) == 0
        serve.assert_called_once_with()


class TestVerifyRun:
    @pytest.fixture
    def approved_command(self, contract_service: ContractService) -> None:
        command = ContractCommand(id='I1', argv=('git', '--version'), approved_by='user')
        contract_service.approve(Slug(SLUG), [command])

    def test_help_shows_its_options(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['verify', 'run', '--help'])

        shown = capsys.readouterr().out
        assert exit_info.value.code == 0
        assert [option in shown for option in ('--slug', '--id', '--all', '--phase')] == [True] * 4

    @pytest.mark.parametrize(
        'arguments',
        [
            pytest.param(['--slug', SLUG], id='neither-ids-nor-all'),
            pytest.param(['--slug', SLUG, '--id', 'I1', '--all'], id='ids-and-all'),
            pytest.param(['--all'], id='no-slug'),
            pytest.param(['--slug', SLUG, '--all', '--phase', 'shipping'], id='unknown-phase'),
        ],
    )
    def test_refuses_a_command_line_it_does_not_define(
        self, arguments: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['verify', 'run', *arguments])

        assert exit_info.value.code == 2
        assert 'usage: mightymodels verify run' in capsys.readouterr().err

    def test_help_loads_no_database_or_server_package(
        self, repository: Path, data_directory: Path
    ) -> None:
        assert loaded_packages(repository, data_directory, 'verify', 'run', '--help') == '0 []'

    @pytest.mark.usefixtures('approved_command')
    def test_verify_run_does_not_import_mcp(self, repository: Path, data_directory: Path) -> None:
        arguments = ('verify', 'run', '--slug', SLUG, '--id', 'I1')
        loaded = loaded_packages(repository, data_directory, *arguments)

        assert loaded == "0 ['pydantic', 'sqlalchemy']"


class TestReviewSignals:
    WINDOW_OPTIONS = ('--target', '--since', '--baseline-ref', '--max-commits', '--all-history')

    @pytest.mark.parametrize('report', ['code-churn', 'change-coupling', 'code-hotspots'])
    def test_help_shows_the_window_options_of_each_report(
        self, report: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(['review-signals', report, '--help'])

        shown = capsys.readouterr().out
        assert exit_info.value.code == 0
        assert [option in shown for option in self.WINDOW_OPTIONS] == [True] * 5

import sqlite3
from contextlib import closing
from pathlib import Path
from types import MappingProxyType

import pytest
from mightymodels_plugin.commands.session_start import ENV_FILE_VARIABLE
from mightymodels_plugin.commands.tests.hook_inputs import (
    SKIPPED,
    Hook,
    hook_input,
    implementer_stop,
    scout_stop,
)
from mightymodels_plugin.core.data_directory import PLUGIN_DATA_VARIABLE
from mightymodels_plugin.core.database import DATABASE_NAME
from mightymodels_plugin.core.workspace import PROJECT_DIR_VARIABLE
from mightymodels_plugin.tools.similarity.spool import SPOOL_DIRECTORY


def database_with_another_schema_version(data_directory: Path) -> None:
    data_directory.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(data_directory.joinpath(DATABASE_NAME))) as connection:
        connection.execute('CREATE TABLE other (x INTEGER)')
        connection.execute('PRAGMA user_version = 99')


INPUTS = MappingProxyType(
    {
        'session-start': '{}',
        'subagent-record': scout_stop(),
        'completion-gate': implementer_stop(),
        'pre-compact': hook_input('PreCompact'),
    }
)


class TestWhenAHookCannotWork:
    @pytest.fixture
    def without_a_data_directory(
        self, hook_repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Path:
        monkeypatch.delenv(PLUGIN_DATA_VARIABLE)
        monkeypatch.setenv(ENV_FILE_VARIABLE, str(tmp_path.joinpath('session-env.sh')))
        return hook_repository

    @pytest.fixture
    def outside_a_repository(self, hook_repository: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        outside = hook_repository.parent.joinpath('outside')
        outside.mkdir()
        monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(outside))
        return outside

    @pytest.fixture
    def with_a_refused_database(self, data_directory: Path) -> Path:
        database_with_another_schema_version(data_directory)
        return data_directory.joinpath(DATABASE_NAME)

    @pytest.mark.usefixtures('without_a_data_directory')
    @pytest.mark.parametrize('command', INPUTS)
    def test_without_a_data_directory_it_exits_0_blocking_nothing_and_says_why(
        self, command: str, hook_command: Hook
    ) -> None:
        code, out, err = hook_command.run(command, INPUTS[command])

        assert (code, out) == (0, '')
        assert err.startswith(f'{SKIPPED}{PLUGIN_DATA_VARIABLE} is not set')

    @pytest.mark.usefixtures('outside_a_repository')
    @pytest.mark.parametrize('command', ['subagent-record', 'completion-gate', 'pre-compact'])
    def test_outside_a_git_repository_it_exits_0_blocking_nothing_and_says_why(
        self, command: str, hook_command: Hook, data_directory: Path
    ) -> None:
        code, out, err = hook_command.run(command, INPUTS[command])

        assert (code, out) == (0, '')
        assert 'is not inside a git repository' in err
        assert not data_directory.joinpath(SPOOL_DIRECTORY).exists()

    @pytest.mark.usefixtures('with_a_refused_database')
    @pytest.mark.parametrize('command', ['completion-gate', 'pre-compact'])
    def test_with_a_refused_database_it_exits_0_blocking_nothing_and_says_why(
        self, command: str, hook_command: Hook
    ) -> None:
        code, out, err = hook_command.run(command, INPUTS[command])

        assert (code, out) == (0, '')
        assert 'schema version 99' in err

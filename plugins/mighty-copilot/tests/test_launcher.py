import json
import os
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PLUGIN_ROOT.joinpath('bin', 'mightymodels')
MCP_CONFIG = PLUGIN_ROOT.joinpath('mcp.json')


@pytest.fixture(scope='module')
def launcher_text() -> str:
    return LAUNCHER.read_text(encoding='utf-8')


class TestLauncher:
    def test_is_an_executable_posix_sh_script(self, launcher_text: str) -> None:
        assert os.access(LAUNCHER, os.X_OK)
        assert launcher_text.splitlines()[0] == '#!/bin/sh'

    def test_parses_under_sh(self) -> None:
        completed = subprocess.run(  # noqa: S603 - fixed argv with the launcher path as one word
            ['sh', '-n', str(LAUNCHER)],  # noqa: S607 - sh is resolved from PATH
            check=False,
            capture_output=True,
        )

        assert completed.returncode == 0, completed.stderr

    def test_runs_the_lock_with_the_source_on_the_path(self, launcher_text: str) -> None:
        assert 'uv tool run' in launcher_text
        assert '--compile-bytecode' in launcher_text
        assert '--with-requirements "${root}/requirements.lock"' in launcher_text
        assert 'PYTHONPATH="${root}/src"' in launcher_text
        assert 'python -P -m mightymodels "$@"' in launcher_text

    def test_help_exits_zero_from_another_directory(self, tmp_path: Path) -> None:
        completed = subprocess.run(  # noqa: S603 - the launcher is this plugin's own script
            [str(LAUNCHER), '--help'],
            check=False,
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )

        assert completed.returncode == 0, completed.stderr
        assert 'usage: mightymodels' in completed.stdout


class TestEveryFileInBin:
    @pytest.mark.parametrize(
        'file',
        [
            pytest.param(file, id=file.name)
            for file in sorted(PLUGIN_ROOT.joinpath('bin').iterdir())
        ],
    )
    def test_is_executable(self, file: Path) -> None:
        assert os.access(file, os.X_OK), file.name


class TestMcpConfig:
    def test_registers_only_the_state_server_through_the_launcher(self) -> None:
        servers = json.loads(MCP_CONFIG.read_text(encoding='utf-8'))['mcpServers']

        assert list(servers) == ['state']
        assert servers['state']['command'] == '${PLUGIN_ROOT}/bin/mightymodels'

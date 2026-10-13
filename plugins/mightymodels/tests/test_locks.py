import os
import shutil
import subprocess
from pathlib import Path

import pytest
import tomllib

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_DIRECTORIES = sorted(
    path.parent for path in REPOSITORY_ROOT.glob('plugins/*/pyproject.toml')
)


def package_name(plugin_dir: Path) -> str:
    pyproject = tomllib.loads(plugin_dir.joinpath('pyproject.toml').read_text(encoding='utf-8'))
    return pyproject['project']['name']


def exported_lock(package: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed uv argv, the package name comes from a checked-in pyproject
        [
            str(shutil.which('uv')),
            'export',
            '--package',
            package,
            '--no-dev',
            '--no-emit-workspace',
            '--no-hashes',
            '--frozen',
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
        env={**os.environ, 'NO_COLOR': '1'},
    )
    return completed.stdout


class TestRequirementsLock:
    @pytest.mark.parametrize(
        'plugin_dir', PLUGIN_DIRECTORIES, ids=[path.name for path in PLUGIN_DIRECTORIES]
    )
    def test_requirements_lock_matches_the_workspace_export(self, plugin_dir: Path) -> None:
        lock = plugin_dir.joinpath('requirements.lock').read_text(encoding='utf-8')

        assert lock == exported_lock(package_name(plugin_dir))

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mightymcp.paths import PROJECT_DIR_VARS, git_output

PAYLOADS = Path(__file__).parent.joinpath('payloads')


@pytest.fixture
def git() -> Callable[..., str]:
    """Run git for test setup, failing the test when the command fails."""

    def run(root: Path, *args: str) -> str:
        output = git_output(list(args), cwd=root)
        assert output is not None, f'git {" ".join(args)} failed in {root}'
        return output

    return run


@pytest.fixture
def make_repo(tmp_path: Path, git: Callable[..., str]) -> Callable[[str], Path]:
    """Build a named git repository under tmp_path."""

    def build(name: str) -> Path:
        root = tmp_path.joinpath(name).resolve()
        root.mkdir()
        git(tmp_path, 'init', '-q', '-b', 'main', str(root))
        return root

    return build


@pytest.fixture
def repo(make_repo: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch) -> Path:
    """A git repository wired up as the project dir every ticket tool resolves to."""
    root = make_repo('repo')
    monkeypatch.delenv('CLAUDE_PROJECT_DIR', raising=False)
    monkeypatch.setenv('MIGHTYMCP_PROJECT_DIR', str(root))
    return root


@pytest.fixture
def commit(git: Callable[..., str]) -> Callable[[Path, str], str]:
    """Commit one named file into a repository and return the new commit's hash."""

    def run(root: Path, name: str) -> str:
        root.joinpath(name).write_text(name, encoding='utf-8')
        git(root, 'add', '-A')
        git(
            root,
            '-c',
            'user.email=test@example.com',
            '-c',
            'user.name=test',
            '-c',
            'commit.gpgsign=false',
            'commit',
            '-q',
            '-m',
            name,
        )
        return git(root, 'rev-parse', 'HEAD')

    return run


@pytest.fixture
def ticket_root(repo: Path) -> Path:
    """The .mightymodels/demo directory, with the subdirectories a ticket carries."""
    directory = repo.joinpath('.mightymodels', 'demo')
    directory.joinpath('briefs').mkdir(parents=True)
    directory.joinpath('handoffs').mkdir()
    return directory


@pytest.fixture
def payload() -> Callable[[str], dict[str, Any]]:
    """Load one hook payload fixture by name, e.g. SessionStart-startup."""

    def load(name: str) -> dict[str, Any]:
        return json.loads(PAYLOADS.joinpath(f'{name}.json').read_text(encoding='utf-8'))

    return load


@pytest.fixture
def run_hook_script() -> Callable[..., subprocess.CompletedProcess[str]]:
    """Run a hook script the way Claude Code does: stdin payload, cwd at the repo.

    The project-dir variables are dropped from the child environment so the hook
    resolves the repository from its cwd, as it does in a real session.
    """

    def run(
        script: Path, stdin: str, cwd: Path, **env: str
    ) -> subprocess.CompletedProcess[str]:
        inherited = {k: v for k, v in os.environ.items() if k not in PROJECT_DIR_VARS}
        return subprocess.run(  # noqa: S603 -- argv is this interpreter and a script
            [sys.executable, str(script)],
            input=stdin,
            cwd=cwd,
            env=inherited | env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    return run

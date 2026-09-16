from collections.abc import Callable
from pathlib import Path

import pytest
from mightymcp.paths import git_output


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
def ticket_root(repo: Path) -> Path:
    """The .mightymodels/demo directory, with the subdirectories a ticket carries."""
    directory = repo.joinpath('.mightymodels', 'demo')
    directory.joinpath('briefs').mkdir(parents=True)
    directory.joinpath('handoffs').mkdir()
    return directory

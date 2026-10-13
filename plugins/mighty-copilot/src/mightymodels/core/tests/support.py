import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import pytest

from mightymodels.core.tests.in_memory_git import InMemoryGit
from mightymodels.core.workspace import Workspace, workspace_at

RECORDER_SOURCE = """#!{python}
import json
import sys
from pathlib import Path

call = {{'argv': sys.argv, 'cwd': str(Path.cwd())}}
with Path({log!r}).open('a', encoding='utf-8') as log:
    log.write(json.dumps(call) + '\\n')
print(0)
"""


@runtime_checkable
class GitRunner(Protocol):
    def __call__(self, directory: Path, /, *arguments: str) -> str: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedCall:
    argv: list[str]
    cwd: Path


@dataclass(slots=True, kw_only=True, frozen=True)
class Recorder:
    executable: str
    log: Path

    def calls(self) -> list[RecordedCall]:
        lines = self.log.read_text(encoding='utf-8').splitlines() if self.log.is_file() else []
        return [
            RecordedCall(argv=call['argv'], cwd=Path(call['cwd']))
            for call in map(json.loads, lines)
        ]


@pytest.fixture
def recorder(tmp_path: Path) -> Recorder:
    directory = tmp_path.joinpath('recorder')
    directory.mkdir()
    log = directory.joinpath('calls.jsonl')
    executable = directory.joinpath('record')
    executable.write_text(
        RECORDER_SOURCE.format(python=sys.executable, log=str(log)), encoding='utf-8'
    )
    executable.chmod(0o700)
    return Recorder(executable=str(executable), log=log)


@pytest.fixture
def in_memory_git() -> InMemoryGit:
    return InMemoryGit()


@pytest.fixture
def gitless_workspace(tmp_path: Path) -> Workspace:
    directory = tmp_path.joinpath('gitless')
    directory.mkdir()
    return workspace_at(directory)


def run_git(directory: Path, *arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed git argv, every argument is a separate word
        ['git', '-C', str(directory), *arguments],  # noqa: S607 - git is resolved from PATH by name
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


@pytest.fixture
def git() -> GitRunner:
    return run_git


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('repository')
    root.mkdir()
    run_git(root, 'init', '--quiet')
    return root

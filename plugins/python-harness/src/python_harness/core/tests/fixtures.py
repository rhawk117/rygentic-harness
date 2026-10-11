"""Shared pytest fixtures: throwaway projects on disk, with or without git."""

import shutil
import subprocess
import textwrap
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from python_harness.core.errors import UvWorkspaceError
from python_harness.core.workspace import Workspace, open_workspace

STUBBED_UV_REASON = 'uv is stubbed out in tests'
STUBBED_UV_DIAGNOSTIC = f'uv workspace discovery failed: {STUBBED_UV_REASON}'


def stubbed_uv(_: Path) -> str:
    raise UvWorkspaceError(STUBBED_UV_REASON)


@dataclass(frozen=True, slots=True)
class ProjectBuilder:
    root: Path

    def write(self, files: Mapping[str, str]) -> Workspace:
        for relative, text in files.items():
            target = self.root.joinpath(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(textwrap.dedent(text).lstrip(), encoding='utf-8')
        return open_workspace(self.root, uv_runner=stubbed_uv)


@dataclass(frozen=True, slots=True)
class GitProject:
    builder: ProjectBuilder
    executable: str

    def git(self, *arguments: str) -> None:
        subprocess.run(  # noqa: S603  fixed git verbs for building test repositories.
            (self.executable, *arguments),
            cwd=self.builder.root,
            check=True,
            capture_output=True,
        )

    def commit(self, files: Mapping[str, str], message: str) -> Workspace:
        workspace = self.builder.write(files)
        self.git('add', '--all')
        self.git('commit', '--quiet', '--message', message)
        return workspace

    def switch_to_new_branch(self, name: str) -> None:
        self.git('switch', '--quiet', '--create', name)


@pytest.fixture
def project_builder(tmp_path: Path) -> ProjectBuilder:
    return ProjectBuilder(tmp_path)


@pytest.fixture
def git_project(project_builder: ProjectBuilder) -> GitProject:
    executable = shutil.which('git')
    if executable is None:
        pytest.skip('git is not installed')
    project = GitProject(project_builder, executable)
    project.git('init', '--quiet', '--initial-branch', 'main')
    project.git('config', 'user.email', 'tests@example.invalid')
    project.git('config', 'user.name', 'python-harness tests')
    return project

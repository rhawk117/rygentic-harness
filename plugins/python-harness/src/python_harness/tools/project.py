"""The project the inspection tools read: its root is CLAUDE_PROJECT_DIR and nothing else."""

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

from pydantic import Field, StringConstraints

from python_harness.core.output import JsonValue
from python_harness.core.workspace import UvRunner, Workspace, open_workspace
from python_harness.imports.domain import ImportGraph
from python_harness.imports.services import unindexed_packages_for
from python_harness.tools.errors import ProjectRootRelativeError, ProjectRootUnsetError

PROJECT_ROOT_VARIABLE = 'CLAUDE_PROJECT_DIR'

type ProjectPath = Annotated[str, StringConstraints(pattern=r'^[^\x00]+$')]
type ProjectPaths = Annotated[
    tuple[ProjectPath, ...],
    Field(
        min_length=1,
        description=(
            'Python files or directories inside the project, relative to its root;'
            ' a directory stands for every Python file under it.'
        ),
    ),
]


def check_project_root(
    declared: str,
) -> ProjectRootUnsetError | ProjectRootRelativeError | None:
    if declared == '':
        return ProjectRootUnsetError(PROJECT_ROOT_VARIABLE)
    if not Path(declared).is_absolute():
        return ProjectRootRelativeError(PROJECT_ROOT_VARIABLE, declared)
    return None


def open_project(environment: Mapping[str, str], uv_runner: UvRunner) -> Workspace:
    declared = environment.get(PROJECT_ROOT_VARIABLE, '')
    if (problem := check_project_root(declared)) is not None:
        raise problem
    return open_workspace(Path(declared), uv_runner=uv_runner)


def workspace_diagnostics(workspace: Workspace, graph: ImportGraph) -> dict[str, JsonValue]:
    return {
        'source_roots': [workspace.relative(root) for root in workspace.source_roots],
        'fallback_diagnostics': list(workspace.fallback_diagnostics),
        'unindexed_packages': [
            {'name': package.name, 'directory': package.directory}
            for package in unindexed_packages_for(workspace, graph)
        ],
    }

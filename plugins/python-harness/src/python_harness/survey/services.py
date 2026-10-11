"""Reading pyproject.toml, layout markers and imports into a survey of the project."""

from collections.abc import Iterator
from itertools import chain
from pathlib import Path

import tomllib

from python_harness.core.output import JsonValue, dataclass_to_json
from python_harness.core.toml import TomlTable, read_table
from python_harness.core.workspace import Workspace
from python_harness.imports.domain import ImportGraph
from python_harness.imports.services import load_project_index
from python_harness.survey.domain import (
    NO_MANIFEST,
    PYPROJECT,
    RUFF_CONFIG_FILES,
    TY_CONFIG_FILES,
    UV_LOCK,
    LayoutFacts,
    ProjectSurvey,
    SurveyOptions,
)
from python_harness.survey.errors import ManifestUnreadableError
from python_harness.survey.policy import detect_domains, infer_mode
from python_harness.survey.util import declares_ruff_config, manifest_from_document


def survey_document(survey: ProjectSurvey) -> JsonValue:
    document = dataclass_to_json(survey)
    if survey.manifest is NO_MANIFEST:
        return document | {'manifest': None}
    return document


def load_pyproject(workspace: Workspace) -> TomlTable | None:
    path = workspace.root.joinpath(PYPROJECT)
    if not path.is_file():
        return None
    try:
        return tomllib.loads(path.read_text(encoding='utf-8'))
    except tomllib.TOMLDecodeError as error:
        raise ManifestUnreadableError(path, error.msg) from error
    except UnicodeDecodeError as error:
        raise ManifestUnreadableError(path, str(error)) from error


def walk_file_names(base: Path, excluded: frozenset[str]) -> Iterator[str]:
    for _, subdirectories, filenames in base.walk():
        subdirectories[:] = [name for name in subdirectories if name not in excluded]
        yield from filenames


def collect_package_file_names(workspace: Workspace) -> frozenset[str]:
    discovery = workspace.options
    excluded = discovery.excluded_directories | discovery.test_directory_names
    bases = workspace.source_roots or (workspace.root,)
    return frozenset(chain.from_iterable(walk_file_names(base, excluded) for base in bases))


def read_layout(workspace: Workspace) -> LayoutFacts:
    file_names = collect_package_file_names(workspace)
    test_directories = (
        workspace.root.joinpath(name) for name in workspace.options.test_directory_names
    )
    return LayoutFacts(
        has_py_typed='py.typed' in file_names,
        has_dunder_main='__main__.py' in file_names,
        has_src_layout=bool(workspace.source_roots),
        has_tests_directory=any(path.is_dir() for path in test_directories),
        has_uv_lock=workspace.root.joinpath(UV_LOCK).is_file(),
    )


def ruff_config_name(directory: Path, pyproject: TomlTable | None) -> str | None:
    candidates = (directory.joinpath(name) for name in RUFF_CONFIG_FILES)
    dedicated = next((path.name for path in candidates if path.is_file()), None)
    if dedicated is not None:
        return dedicated
    if pyproject is None or not declares_ruff_config(pyproject):
        return None
    return PYPROJECT


def find_ruff_config(workspace: Workspace, pyproject: TomlTable | None) -> str | None:
    return ruff_config_name(workspace.root, pyproject)


def ty_config_name(directory: Path, pyproject: TomlTable | None) -> str | None:
    candidates = (directory.joinpath(name) for name in TY_CONFIG_FILES)
    dedicated = next((path.name for path in candidates if path.is_file()), None)
    if dedicated is not None:
        return dedicated
    if pyproject is None or 'ty' not in read_table(pyproject, 'tool'):
        return None
    return PYPROJECT


def find_ty_config(workspace: Workspace, pyproject: TomlTable | None) -> str | None:
    return ty_config_name(workspace.root, pyproject)


def survey_indexed_project(
    workspace: Workspace, graph: ImportGraph, options: SurveyOptions | None = None
) -> ProjectSurvey:
    chosen = SurveyOptions() if options is None else options
    pyproject = load_pyproject(workspace)
    manifest = NO_MANIFEST if pyproject is None else manifest_from_document(pyproject)
    layout = read_layout(workspace)
    external_packages = tuple(sorted(graph.external_packages))
    return ProjectSurvey(
        root=workspace.root.as_posix(),
        manifest=manifest,
        layout=layout,
        mode=infer_mode(manifest, layout),
        domains=detect_domains(manifest, external_packages, layout, options=chosen),
        ruff_config=find_ruff_config(workspace, pyproject),
        external_packages=external_packages,
        source_roots=tuple(workspace.relative(root) for root in workspace.source_roots),
        ty_config=find_ty_config(workspace, pyproject),
    )


def survey_project(workspace: Workspace, options: SurveyOptions | None = None) -> ProjectSurvey:
    return survey_indexed_project(workspace, load_project_index(workspace).graph, options)

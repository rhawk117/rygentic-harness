"""Reading a parsed pyproject.toml into manifest facts, including uv's default groups."""

import re
from collections.abc import Iterable, Iterator, Mapping
from itertools import chain
from types import MappingProxyType

from python_harness.core.toml import (
    TomlTable,
    normalize_name,
    read_items,
    read_nested_table,
    read_string,
    read_strings,
    read_table,
    select_strings,
)
from python_harness.survey.domain import ProjectManifest

type DependencyGroups = Mapping[str, tuple[object, ...]]

SCRIPT_TABLES = ('scripts', 'gui-scripts')
LEGACY_BUILD_BACKEND = 'setuptools.build_meta:__legacy__'
REQUIREMENT_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*')
DEV_GROUP = 'dev'
ALL_GROUPS = 'all'
DEFAULT_GROUPS_KEY = 'default-groups'
POETRY_PYTHON = 'python'


def read_strings_of_every_key(table: TomlTable) -> Iterator[str]:
    return chain.from_iterable(read_strings(table, key) for key in table)


def distribution_name_of(requirement: str) -> str | None:
    found = REQUIREMENT_NAME.match(requirement.strip())
    if found is None:
        return None
    return normalize_name(found.group())


def normalize_requirements(requirements: Iterable[str]) -> tuple[str, ...]:
    names = (distribution_name_of(requirement) for requirement in requirements)
    return tuple(sorted({name for name in names if name is not None}))


def read_build_backend(document: TomlTable) -> str | None:
    if 'build-system' not in document:
        return None
    build_system = read_table(document, 'build-system')
    return read_string(build_system, 'build-backend') or LEGACY_BUILD_BACKEND


def list_script_names(project: TomlTable) -> tuple[str, ...]:
    tables = (read_table(project, key) for key in SCRIPT_TABLES)
    return tuple(sorted(chain.from_iterable(tables)))


def read_uv_settings(document: TomlTable) -> TomlTable:
    return read_nested_table(document, 'tool', 'uv')


def read_dependency_groups(document: TomlTable) -> DependencyGroups:
    declared = read_table(document, 'dependency-groups')
    groups = {normalize_name(name): read_items(declared, name) for name in declared}
    legacy = read_items(read_uv_settings(document), 'dev-dependencies')
    groups[DEV_GROUP] = (*groups.get(DEV_GROUP, ()), *legacy)
    return MappingProxyType(groups)


def read_default_group_names(document: TomlTable, groups: DependencyGroups) -> frozenset[str]:
    settings = read_uv_settings(document)
    configured = settings.get(DEFAULT_GROUPS_KEY)
    if configured is None:
        return frozenset({DEV_GROUP})
    if configured == ALL_GROUPS:
        return frozenset(groups)
    named = read_strings(settings, DEFAULT_GROUPS_KEY)
    return frozenset(normalize_name(name) for name in named)


def included_group_name(item: object) -> str | None:
    if not isinstance(item, Mapping):
        return None
    name = item.get('include-group')
    if not isinstance(name, str):
        return None
    return normalize_name(name)


def list_included_groups(groups: DependencyGroups, names: Iterable[str]) -> Iterator[str]:
    items = chain.from_iterable(groups.get(name, ()) for name in names)
    included = (included_group_name(item) for item in items)
    return (name for name in included if name is not None)


def close_over_includes(
    groups: DependencyGroups, names: frozenset[str], reached: frozenset[str]
) -> frozenset[str]:
    fresh = names - reached
    if not fresh:
        return reached
    included = frozenset(list_included_groups(groups, fresh))
    return close_over_includes(groups, included, reached | fresh)


def expand_default_groups(document: TomlTable, groups: DependencyGroups) -> frozenset[str]:
    named = read_default_group_names(document, groups)
    return close_over_includes(groups, named, frozenset())


def read_group_requirements(groups: DependencyGroups, names: Iterable[str]) -> Iterator[str]:
    return select_strings(chain.from_iterable(groups.get(name, ()) for name in names))


def read_poetry_settings(document: TomlTable) -> TomlTable:
    return read_nested_table(document, 'tool', 'poetry')


def poetry_keys(table: TomlTable) -> Iterator[str]:
    return (key for key in table if key != POETRY_PYTHON)


def poetry_group_keys(poetry: TomlTable, *, optional: bool) -> Iterator[str]:
    groups = read_table(poetry, 'group')
    tables = (read_table(groups, name) for name in groups)
    chosen = (table for table in tables if (table.get('optional') is True) is optional)
    return chain.from_iterable(poetry_keys(read_table(table, 'dependencies')) for table in chosen)


def runtime_requirements(document: TomlTable) -> Iterator[str]:
    project = read_table(document, 'project')
    poetry = read_poetry_settings(document)
    return chain(
        read_strings(project, 'dependencies'),
        poetry_keys(read_table(poetry, 'dependencies')),
    )


def development_requirements(document: TomlTable, groups: DependencyGroups) -> Iterator[str]:
    poetry = read_poetry_settings(document)
    return chain(
        read_group_requirements(groups, expand_default_groups(document, groups)),
        poetry_keys(read_table(poetry, 'dev-dependencies')),
        poetry_group_keys(poetry, optional=False),
    )


def optional_requirements(document: TomlTable, groups: DependencyGroups) -> Iterator[str]:
    project = read_table(document, 'project')
    other_groups = groups.keys() - expand_default_groups(document, groups)
    return chain(
        read_strings_of_every_key(read_table(project, 'optional-dependencies')),
        read_group_requirements(groups, other_groups),
        poetry_group_keys(read_poetry_settings(document), optional=True),
    )


def manifest_from_document(document: TomlTable) -> ProjectManifest:
    project = read_table(document, 'project')
    groups = read_dependency_groups(document)
    return ProjectManifest(
        name=read_string(project, 'name'),
        requires_python=read_string(project, 'requires-python'),
        build_backend=read_build_backend(document),
        entry_points=list_script_names(project),
        classifiers=read_strings(project, 'classifiers'),
        dependencies=normalize_requirements(runtime_requirements(document)),
        dev_dependencies=normalize_requirements(development_requirements(document, groups)),
        optional_dependencies=normalize_requirements(optional_requirements(document, groups)),
    )

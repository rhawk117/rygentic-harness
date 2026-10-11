"""Mapping where target modules' symbols are referenced, with per-module coupling."""

from collections.abc import Iterable

from python_harness.calls.domain import CallsReport, SymbolReferencesReport, TargetedProject
from python_harness.calls.policy import check_targets_known
from python_harness.calls.util.references import (
    describe_symbol_usage,
    index_references,
)
from python_harness.calls.util.summaries import summarize_module
from python_harness.calls.util.symbols import select_targets
from python_harness.core.workspace import Workspace
from python_harness.imports.domain import ProjectIndex


def targeted_project_for(
    workspace: Workspace, index: ProjectIndex, paths: Iterable[str]
) -> TargetedProject:
    found = workspace.python_files_in(paths)
    target_paths = frozenset(workspace.relative(path) for path in found)
    problem = check_targets_known(index, target_paths)
    if problem is not None:
        raise problem
    return select_targets(index, target_paths)


def map_call_sites_for(
    workspace: Workspace, index: ProjectIndex, paths: Iterable[str]
) -> CallsReport:
    project = targeted_project_for(workspace, index, paths)
    references = index_references(project.definitions, project.scopes.values())
    modules = (summarize_module(scope, references, project.graph) for scope in project.targets)
    return CallsReport(tuple(modules), project.unparsable)


def find_symbol_references_for(
    workspace: Workspace, index: ProjectIndex, paths: Iterable[str], *, name: str
) -> SymbolReferencesReport:
    project = targeted_project_for(workspace, index, paths)
    matching = tuple(item for item in project.definitions if item.matches(name))
    references = index_references(matching, project.scopes.values())
    usages = describe_symbol_usage(matching, references)
    return SymbolReferencesReport(name, usages, project.unparsable)

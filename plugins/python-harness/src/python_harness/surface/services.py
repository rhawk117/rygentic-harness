"""Choosing the review surface and planning one pylens dispatch per import cluster."""

from types import MappingProxyType

from python_harness.core.git import list_changed_python_files
from python_harness.core.workspace import Workspace
from python_harness.imports.domain import ProjectIndex
from python_harness.surface.domain import (
    DiffTarget,
    SurfaceGraph,
    SurfaceOptions,
    SurfacePlan,
    Target,
)
from python_harness.surface.policy import (
    assemble_clusters,
    cluster_modules,
    select_paths_with_code,
)


def resolve_surface_paths(workspace: Workspace, target: Target) -> tuple[str, ...]:
    if isinstance(target, DiffTarget):
        return list_changed_python_files(workspace, target.base, target.head)
    found = workspace.python_files_in(target.paths)
    return tuple(workspace.relative(path) for path in found)


def index_surface(index: ProjectIndex, surface_paths: frozenset[str]) -> SurfaceGraph:
    modules = index.sources.modules
    lines = {module.source.path: module.source.line_count for module in modules}
    reviewable = select_paths_with_code(modules, surface_paths)
    refs = tuple(index.graph.modules.values())
    surface = frozenset(ref.name for ref in refs if ref.path in reviewable)
    line_counts = MappingProxyType({ref.name: lines[ref.path] for ref in refs})
    return SurfaceGraph(index.graph, surface, line_counts)


def plan_surface(
    workspace: Workspace,
    index: ProjectIndex,
    target: Target,
    *,
    options: SurfaceOptions | None = None,
) -> SurfacePlan:
    chosen = SurfaceOptions() if options is None else options
    surface_paths = frozenset(resolve_surface_paths(workspace, target))
    if not surface_paths:
        return SurfacePlan(target, (), (), chosen)
    view = index_surface(index, surface_paths)
    groups = cluster_modules(view, options=chosen)
    reported = index.sources.unparsable
    unparsable = tuple(item for item in reported if item.path in surface_paths)
    return SurfacePlan(target, assemble_clusters(groups, view), unparsable, chosen)

"""The module graph of the measured files, its cycles, and Martin's component metrics.

An import becomes an edge when it resolves to a measured file. Cycles are the strongly connected
components of more than one module, found with Tarjan's algorithm in two steps: one depth-first
walk on an explicit stack records where each module is discovered and the order the walk leaves
them, then each module's lowlink is settled in that leaving order. Cycles are listed in the order
their roots are left. Modules roll up to packages of `depth` path components, and each package
carries its fan-in (Ca), fan-out (Ce), instability I = Ce/(Ca+Ce), abstractness A and distance
from the main sequence D = |A + I - 1|.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from mightymodels.review_metrics.shapes import (
    FileMetric,
    Graph,
    PackageMetric,
    PackageReport,
)
from mightymodels.review_metrics.sources import JS_SUFFIXES, TS_SUFFIXES, module_name_for

LAYOUT_DIRS = ('src', 'lib', 'app')
SRC_PREFIX = 'src.'


def package_of(module: str, depth: int = 1) -> str:
    parts = module.split('.')
    while len(parts) > 1 and parts[0] in LAYOUT_DIRS:
        parts = parts[1:]
    return '.'.join(parts[: max(depth, 1)]) if len(parts) > 1 else parts[0]


def module_lookup(names: list[str]) -> dict[str, str]:
    lookup = {name: name for name in names}
    for name in names:
        if name.startswith(SRC_PREFIX):
            lookup.setdefault(name.removeprefix(SRC_PREFIX), name)
    return lookup


def build_module_graph(metrics: list[FileMetric]) -> Graph:
    names = [module_name_for(Path(m.path)) for m in metrics]
    lookup = module_lookup(names)
    graph: Graph = {name: set() for name in names}
    for metric, source in zip(metrics, names, strict=True):
        targets = {resolve_internal(imp, metric, lookup) for imp in metric.imports}
        graph[source] |= {target for target in targets if target and target != source}
    return graph


def resolve_python_internal(imp: str, lookup: dict[str, str]) -> str | None:
    candidate = imp
    while candidate and candidate not in lookup:
        candidate = candidate.rpartition('.')[0]
    return lookup[candidate] if candidate else None


def normalized_parts(parts: tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for part in parts:
        if part == '..':
            normalized = normalized[:-1]
            continue
        if part not in {'.', ''}:
            normalized.append(part)
    return normalized


def resolve_javascript_internal(imp: str, metric: FileMetric, lookup: dict[str, str]) -> str | None:
    if not imp.startswith('.'):
        return None
    joined = Path(metric.path).parent.joinpath(imp)
    if joined.suffix in JS_SUFFIXES | TS_SUFFIXES:
        joined = joined.with_suffix('')
    parts = normalized_parts(joined.parts)
    if parts and parts[-1] == 'index':
        parts = parts[:-1]
    return lookup.get('.'.join(parts))


def resolve_internal(imp: str, metric: FileMetric, lookup: dict[str, str]) -> str | None:
    if metric.language == 'python':
        return resolve_python_internal(imp, lookup)
    return resolve_javascript_internal(imp, metric, lookup)


@dataclass(slots=True, kw_only=True, frozen=True)
class DepthFirstWalk:
    discovered: Mapping[str, int]
    left: tuple[str, ...]


def depth_first_walk(graph: Graph) -> DepthFirstWalk:
    discovered: dict[str, int] = {}
    left: list[str] = []
    path: list[str] = []
    unexplored = [iter(sorted(graph))]
    while unexplored:
        child = next((node for node in unexplored[-1] if node not in discovered), None)
        if child is not None:
            discovered[child] = len(discovered)
            path.append(child)
            unexplored.append(iter(sorted(graph.get(child, ()))))
            continue
        unexplored.pop()
        if path:
            left.append(path.pop())
    return DepthFirstWalk(discovered=MappingProxyType(discovered), left=tuple(left))


def tarjan_sccs(graph: Graph) -> list[list[str]]:
    walk = depth_first_walk(graph)
    discovered = walk.discovered
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    closed: set[str] = set()
    sccs: list[list[str]] = []
    for node in walk.left:
        reached = [
            lowlinks[child] if discovered[child] > discovered[node] else discovered[child]
            for child in graph.get(node, ())
            if child not in closed
        ]
        lowlinks[node] = min([discovered[node], *reached])
        if lowlinks[node] < discovered[node]:
            stack.append(node)
            continue
        component = [node]
        while stack and discovered[stack[-1]] > discovered[node]:
            component.append(stack.pop())
        closed.update(component)
        sccs.append(sorted(component))
    return [scc for scc in sccs if len(scc) > 1]


def package_edges(graph: Graph, depth: int) -> set[tuple[str, str]]:
    pairs = {
        (package_of(source, depth), package_of(target, depth))
        for source, targets in graph.items()
        for target in targets
    }
    return {(source, target) for source, target in pairs if source != target}


def package_members(metrics: list[FileMetric], depth: int) -> dict[str, list[FileMetric]]:
    members: dict[str, list[FileMetric]] = {}
    for metric in metrics:
        package = package_of(module_name_for(Path(metric.path)), depth)
        members.setdefault(package, []).append(metric)
    return members


def distance_of(instability: float | None, abstractness: float | None) -> float | None:
    if instability is None or abstractness is None:
        return None
    return round(abs(abstractness + instability - 1), 3)


def package_metric(
    name: str, members: list[FileMetric], edges: set[tuple[str, str]]
) -> PackageMetric:
    ce = sum(1 for source, _ in edges if source == name)
    ca = sum(1 for _, target in edges if target == name)
    classes = sum(member.classes for member in members)
    abstract_classes = sum(member.abstract_classes for member in members)
    instability = round(ce / (ca + ce), 3) if (ca + ce) else None
    abstractness = round(abstract_classes / classes, 3) if classes else None
    return PackageMetric(
        modules=len(members),
        classes=classes,
        abstract_classes=abstract_classes,
        loc=sum(member.loc for member in members),
        fan_in_ca=ca,
        fan_out_ce=ce,
        instability_i=instability,
        abstractness_a=abstractness,
        distance_d=distance_of(instability, abstractness),
    )


def package_graph(edges: set[tuple[str, str]]) -> Graph:
    graph: Graph = {}
    for source, target in edges:
        graph.setdefault(source, set()).add(target)
        graph.setdefault(target, set())
    return graph


def package_metrics(graph: Graph, metrics: list[FileMetric], depth: int = 1) -> PackageReport:
    edges = package_edges(graph, depth)
    packages = {
        name: package_metric(name, members, edges)
        for name, members in package_members(metrics, depth).items()
    }
    return PackageReport(packages=packages, package_cycles=tarjan_sccs(package_graph(edges)))

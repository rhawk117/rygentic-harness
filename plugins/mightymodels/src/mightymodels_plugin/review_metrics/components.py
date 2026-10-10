"""The module graph of the measured files, its cycles, and Martin's component metrics.

An import becomes an edge when it resolves to a measured file. Cycles are the strongly connected
components of more than one module, found with Tarjan's algorithm on an explicit stack and listed
in the order the search closes them. Modules roll up to packages of `depth` path components, and
each package carries its fan-in (Ca), fan-out (Ce), instability I = Ce/(Ca+Ce), abstractness A
and distance from the main sequence D = |A + I - 1|.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from mightymodels_plugin.review_metrics.shapes import (
    FileMetric,
    Graph,
    PackageMetric,
    PackageReport,
)
from mightymodels_plugin.review_metrics.sources import JS_SUFFIXES, TS_SUFFIXES, module_name_for

LAYOUT_DIRS = ('src', 'lib', 'app')
SRC_PREFIX = 'src.'

type Frame = tuple[str, Iterator[str]]


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
class CycleSearch:
    graph: Graph
    stack: list[str] = field(default_factory=list)
    lowlinks: dict[str, int] = field(default_factory=dict)
    index: dict[str, int] = field(default_factory=dict)
    on_stack: set[str] = field(default_factory=set)
    sccs: list[list[str]] = field(default_factory=list)

    def enter(self, node: str) -> Frame:
        self.index[node] = self.lowlinks[node] = len(self.index)
        self.stack.append(node)
        self.on_stack.add(node)
        return node, iter(sorted(self.graph.get(node, ())))

    def advance(self, current: str, children: Iterator[str], worklist: list[Frame]) -> bool:
        descended = False
        for child in children:
            if child not in self.index:
                worklist.append(self.enter(child))
                descended = True
                break
            if child in self.on_stack:
                self.lowlinks[current] = min(self.lowlinks[current], self.index[child])
        return descended

    def complete(self, worklist: list[Frame]) -> None:
        current = worklist.pop()[0]
        if worklist:
            parent = worklist[-1][0]
            self.lowlinks[parent] = min(self.lowlinks[parent], self.lowlinks[current])
        if self.lowlinks[current] != self.index[current]:
            return
        component: list[str] = []
        while not component or component[-1] != current:
            member = self.stack.pop()
            self.on_stack.discard(member)
            component.append(member)
        self.sccs.append(sorted(component))

    def visit(self, node: str) -> None:
        worklist = [self.enter(node)]
        while worklist:
            current, children = worklist[-1]
            if not self.advance(current, children, worklist):
                self.complete(worklist)


def tarjan_sccs(graph: Graph) -> list[list[str]]:
    search = CycleSearch(graph=graph)
    for node in sorted(graph):
        if node not in search.index:
            search.visit(node)
    return [scc for scc in search.sccs if len(scc) > 1]


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

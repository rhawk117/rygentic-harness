"""Project modules and the import relationships between them."""

from collections.abc import Mapping
from dataclasses import dataclass

from python_harness.core.sources import LoadedSources


@dataclass(frozen=True, slots=True)
class ModuleRef:
    name: str
    path: str
    is_test: bool

    @property
    def is_package(self) -> bool:
        return self.path.endswith('__init__.py')


@dataclass(frozen=True, slots=True)
class ImportBinding:
    importer: str
    local_name: str
    bound_name: str
    requested_name: str
    line: int

    @property
    def is_star(self) -> bool:
        return self.local_name == '*'


@dataclass(frozen=True, slots=True)
class ImportEdge:
    importer: str
    imported: str
    line: int


@dataclass(frozen=True, slots=True)
class ImportGraph:
    modules: Mapping[str, ModuleRef]
    bindings: tuple[ImportBinding, ...]
    edges: tuple[ImportEdge, ...]

    @property
    def internal_packages(self) -> frozenset[str]:
        return frozenset(name.partition('.')[0] for name in self.modules)

    @property
    def external_packages(self) -> frozenset[str]:
        requested = (item.requested_name.partition('.')[0] for item in self.bindings)
        internal = self.internal_packages
        return frozenset(name for name in requested if name and name not in internal)

    def dependencies_of(self, module: str) -> tuple[str, ...]:
        targets = {edge.imported for edge in self.edges if edge.importer == module}
        return tuple(sorted(targets))

    def dependents_of(self, module: str) -> tuple[str, ...]:
        importers = {edge.importer for edge in self.edges if edge.imported == module}
        return tuple(sorted(importers))

    def bindings_in(self, module: str) -> tuple[ImportBinding, ...]:
        return tuple(item for item in self.bindings if item.importer == module)


def longest_module_prefix(dotted_name: str, modules: Mapping[str, ModuleRef]) -> str | None:
    parts = dotted_name.split('.')
    prefixes = ('.'.join(parts[:size]) for size in range(len(parts), 0, -1))
    return next((name for name in prefixes if name in modules), None)


@dataclass(frozen=True, slots=True)
class ProjectIndex:
    sources: LoadedSources
    graph: ImportGraph


@dataclass(frozen=True, slots=True)
class UnindexedPackage:
    name: str
    directory: str

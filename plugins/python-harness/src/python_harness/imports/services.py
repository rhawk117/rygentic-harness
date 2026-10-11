"""Loading the project's modules and building the import graph between them."""

import ast
from collections.abc import Iterable, Iterator, Mapping
from itertools import chain
from pathlib import Path
from types import MappingProxyType

from python_harness.core.sources import ParsedModule, load_sources
from python_harness.core.workspace import Workspace
from python_harness.imports.domain import (
    ExternalPackage,
    ImportBinding,
    ImportEdge,
    ImportGraph,
    ModuleRef,
    ProjectIndex,
    longest_module_prefix,
)


def module_name_for(workspace: Workspace, path: str) -> str:
    absolute = workspace.resolve(path)
    bases = (*workspace.source_roots, workspace.root)
    base = max((root for root in bases if absolute.is_relative_to(root)), key=path_depth)
    parts = absolute.relative_to(base).with_suffix('').parts
    return '.'.join(part for part in parts if part != '__init__')


def path_depth(path: Path) -> int:
    return len(path.parts)


def module_ref_for(workspace: Workspace, path: str) -> ModuleRef:
    name = module_name_for(workspace, path)
    return ModuleRef(name, path, is_test=workspace.is_test_path(path))


def package_parts(module: ModuleRef) -> tuple[str, ...]:
    parts = tuple(module.name.split('.'))
    if module.is_package:
        return parts
    return parts[:-1]


def absolute_from_module(importer: ModuleRef, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ''
    package = package_parts(importer)
    anchor = package[: len(package) - node.level + 1]
    tail = (node.module,) if node.module else ()
    return '.'.join((*anchor, *tail))


def bindings_from_import(importer: ModuleRef, node: ast.Import) -> Iterator[ImportBinding]:
    for alias in node.names:
        local_name = alias.asname or alias.name.partition('.')[0]
        bound_name = alias.name if alias.asname else local_name
        yield ImportBinding(importer.name, local_name, bound_name, alias.name, node.lineno)


def bindings_from_import_from(importer: ModuleRef, node: ast.ImportFrom) -> Iterator[ImportBinding]:
    origin = absolute_from_module(importer, node)
    for alias in node.names:
        qualified = origin if alias.name == '*' else f'{origin}.{alias.name}'
        local_name = alias.asname or alias.name
        yield ImportBinding(importer.name, local_name, qualified, qualified, node.lineno)


def collect_bindings(importer: ModuleRef, tree: ast.Module) -> Iterator[ImportBinding]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from bindings_from_import(importer, node)
        if isinstance(node, ast.ImportFrom):
            yield from bindings_from_import_from(importer, node)


def edge_for(binding: ImportBinding, modules: Mapping[str, ModuleRef]) -> ImportEdge | None:
    target = longest_module_prefix(binding.requested_name, modules)
    if target is None or target == binding.importer:
        return None
    return ImportEdge(binding.importer, target, binding.line)


def edges_from_bindings(
    bindings: Iterable[ImportBinding], modules: Mapping[str, ModuleRef]
) -> tuple[ImportEdge, ...]:
    candidates = (edge_for(binding, modules) for binding in bindings)
    first_by_pair: dict[tuple[str, str], ImportEdge] = {}
    for edge in (item for item in candidates if item is not None):
        first_by_pair.setdefault((edge.importer, edge.imported), edge)
    return tuple(first_by_pair.values())


def build_import_graph(workspace: Workspace, modules: Iterable[ParsedModule]) -> ImportGraph:
    parsed = tuple(modules)
    refs = tuple(module_ref_for(workspace, module.source.path) for module in parsed)
    by_name = MappingProxyType({ref.name: ref for ref in refs})
    nested = (collect_bindings(ref, module.tree) for ref, module in zip(refs, parsed, strict=True))
    bindings = tuple(chain.from_iterable(nested))
    return ImportGraph(by_name, bindings, edges_from_bindings(bindings, by_name))


def load_project_index(workspace: Workspace) -> ProjectIndex:
    sources = load_sources(workspace, workspace.python_files('.'))
    return ProjectIndex(sources, build_import_graph(workspace, sources.modules))


def external_packages_for(workspace: Workspace, graph: ImportGraph) -> tuple[ExternalPackage, ...]:
    roots = (*workspace.source_roots, workspace.root)
    found = (
        (name, package_directory(workspace, name, roots))
        for name in sorted(graph.external_packages)
    )
    return tuple(
        ExternalPackage(name, workspace.relative(directory))
        for name, directory in found
        if directory is not None
    )


def package_directory(workspace: Workspace, name: str, roots: Iterable[Path]) -> Path | None:
    candidates = (root.joinpath(name) for root in roots)
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.is_dir() and candidate.resolve().is_relative_to(workspace.root)
        ),
        None,
    )

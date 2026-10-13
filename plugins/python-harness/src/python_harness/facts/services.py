"""Collecting facts in one walk per parsed module, for the files of a workspace."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import chain
from operator import attrgetter
from pathlib import Path

from python_harness.core.sources import (
    LoadedSources,
    ParsedModule,
    ParseOutcome,
    UnparsableSource,
    load_source,
    load_sources,
)
from python_harness.core.workspace import Workspace
from python_harness.facts.domain import FactCollector, FactsReport, ModuleFacts, NodeDetector
from python_harness.facts.util.annotations import ANNOTATION_DETECTORS
from python_harness.facts.util.async_calls import ASYNC_CALL_DETECTORS
from python_harness.facts.util.class_shape import CLASS_SHAPE_DETECTORS
from python_harness.facts.util.comments import (
    DOCSTRING_DETECTORS,
    collect_comment_facts,
)
from python_harness.facts.util.control_flow import CONTROL_FLOW_DETECTORS
from python_harness.facts.util.exceptions import EXCEPTION_DETECTORS
from python_harness.facts.util.function_shape import FUNCTION_SHAPE_DETECTORS
from python_harness.facts.util.module_state import MODULE_STATE_DETECTORS
from python_harness.facts.util.traversal import run_detectors


def default_node_detectors() -> tuple[NodeDetector, ...]:
    return (
        *CONTROL_FLOW_DETECTORS,
        *EXCEPTION_DETECTORS,
        *CLASS_SHAPE_DETECTORS,
        *FUNCTION_SHAPE_DETECTORS,
        *MODULE_STATE_DETECTORS,
        *ANNOTATION_DETECTORS,
        *DOCSTRING_DETECTORS,
        *ASYNC_CALL_DETECTORS,
    )


def default_module_collectors() -> tuple[FactCollector, ...]:
    return (collect_comment_facts,)


@dataclass(frozen=True, slots=True)
class FactCatalog:
    node_detectors: tuple[NodeDetector, ...] = field(default_factory=default_node_detectors)
    module_collectors: tuple[FactCollector, ...] = field(default_factory=default_module_collectors)


def build_review_catalog() -> FactCatalog:
    detectors = default_node_detectors()
    kept = tuple(item for item in detectors if item not in FUNCTION_SHAPE_DETECTORS)
    return FactCatalog(node_detectors=kept)


def build_full_catalog() -> FactCatalog:
    return FactCatalog()


def collect_module_facts(module: ParsedModule, catalog: FactCatalog) -> ModuleFacts:
    detected = run_detectors(module.tree, catalog.node_detectors)
    collected = (collector(module) for collector in catalog.module_collectors)
    observed = chain(detected, *collected)
    ordered = tuple(sorted(observed, key=attrgetter('line', 'detail.kind')))
    return ModuleFacts(module.source.path, module.source.line_count, ordered)


def collect_facts_or_unparsable(
    module: ParsedModule, catalog: FactCatalog
) -> ModuleFacts | UnparsableSource:
    try:
        return collect_module_facts(module, catalog)
    except RecursionError:
        return UnparsableSource(module.source.path, None, 'nested too deeply to walk')


def source_path_of(outcome: ParseOutcome) -> str:
    if isinstance(outcome, ParsedModule):
        return outcome.source.path
    return outcome.path


def load_sources_reusing(
    workspace: Workspace, files: Iterable[Path], loaded: LoadedSources
) -> LoadedSources:
    held = {source_path_of(item): item for item in (*loaded.modules, *loaded.unparsable)}
    outcomes = tuple(
        held.get(workspace.relative(file)) or load_source(workspace, file) for file in files
    )
    modules = tuple(item for item in outcomes if isinstance(item, ParsedModule))
    unparsable = tuple(item for item in outcomes if isinstance(item, UnparsableSource))
    return LoadedSources(modules, unparsable)


def collect_facts_from(loaded: LoadedSources, catalog: FactCatalog) -> FactsReport:
    outcomes = tuple(collect_facts_or_unparsable(module, catalog) for module in loaded.modules)
    modules = tuple(item for item in outcomes if isinstance(item, ModuleFacts))
    too_deep = tuple(item for item in outcomes if isinstance(item, UnparsableSource))
    return FactsReport(modules, (*loaded.unparsable, *too_deep))


def collect_facts(
    workspace: Workspace, paths: Iterable[str], catalog: FactCatalog | None = None
) -> FactsReport:
    chosen = FactCatalog() if catalog is None else catalog
    loaded = load_sources(workspace, workspace.python_files_in(paths))
    return collect_facts_from(loaded, chosen)

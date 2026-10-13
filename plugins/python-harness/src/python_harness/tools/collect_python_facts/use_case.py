"""Collect the facts of every Python module under the requested paths."""

from dataclasses import dataclass
from pathlib import Path

from python_harness.core.workspace import Workspace
from python_harness.facts.domain import FactsReport
from python_harness.facts.services import (
    FactCatalog,
    build_full_catalog,
    build_review_catalog,
    collect_facts_from,
    load_sources_reusing,
)
from python_harness.imports.domain import ProjectIndex
from python_harness.tools.collect_python_facts.schema import FactsRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class FactsTarget:
    files: tuple[Path, ...]
    catalog: FactCatalog


def catalog_for(request: FactsRequest) -> FactCatalog:
    if request.with_function_shapes:
        return build_full_catalog()
    return build_review_catalog()


def target_for(workspace: Workspace, request: FactsRequest) -> FactsTarget:
    files = workspace.python_files_in(request.paths)
    return FactsTarget(files=files, catalog=catalog_for(request))


def run(workspace: Workspace, index: ProjectIndex, target: FactsTarget) -> FactsReport:
    sources = load_sources_reusing(workspace, target.files, index.sources)
    return collect_facts_from(sources, target.catalog)

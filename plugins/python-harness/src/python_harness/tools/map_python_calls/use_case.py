"""Summarize each target module's references, or list one symbol's references."""

from python_harness.calls.domain import CallsReport, SymbolReferencesReport
from python_harness.calls.services import find_symbol_references_for, map_call_sites_for
from python_harness.core.workspace import Workspace
from python_harness.imports.domain import ProjectIndex
from python_harness.tools.map_python_calls.schema import CallsRequest


def run(
    workspace: Workspace, index: ProjectIndex, request: CallsRequest
) -> CallsReport | SymbolReferencesReport:
    if request.symbol is None:
        return map_call_sites_for(workspace, index, request.paths)
    return find_symbol_references_for(workspace, index, request.paths, name=request.symbol)

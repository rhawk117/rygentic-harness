"""A project tool call loads the project index at most once."""

from collections.abc import Iterable
from pathlib import Path

import pytest
from mcp import Client
from python_harness import server
from python_harness.core.sources import LoadedSources, load_sources
from python_harness.core.workspace import Workspace
from python_harness.gate.domain import GateReport, NotTracked, RuffConfigSource
from python_harness.imports import services as imports_services

PROJECT_TOOL_CALLS = (
    pytest.param('survey', {}, id='survey'),
    pytest.param('gate', {}, id='gate'),
    pytest.param('plan_review_surface', {'paths': ['src']}, id='plan-review-surface'),
    pytest.param(
        'collect_python_facts', {'paths': ['src/shop/pricing.py']}, id='collect-python-facts'
    ),
    pytest.param('map_python_calls', {'paths': ['src/shop/pricing.py']}, id='map-python-calls'),
    pytest.param('check_citations', {'path': 'REVIEW.md'}, id='check-citations'),
)


@pytest.fixture
def index_loads(monkeypatch: pytest.MonkeyPatch) -> list[LoadedSources]:
    loads: list[LoadedSources] = []

    def load_and_record(workspace: Workspace, paths: Iterable[Path]) -> LoadedSources:
        loaded = load_sources(workspace, paths)
        loads.append(loaded)
        return loaded

    monkeypatch.setattr(imports_services, 'load_sources', load_and_record)
    return loads


@pytest.fixture
def gate_without_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    report = GateReport(RuffConfigSource.FALLBACK, (), NotTracked())
    monkeypatch.setattr(server, 'run_gate', lambda *_, **__: report)


@pytest.mark.anyio
@pytest.mark.usefixtures('shop', 'gate_without_checks')
class TestProjectIndexLoads:
    @pytest.mark.parametrize(('tool', 'arguments'), PROJECT_TOOL_CALLS)
    async def test_a_project_tool_call_loads_the_index_at_most_once(
        self,
        project_client: Client,
        index_loads: list[LoadedSources],
        tool: str,
        arguments: dict[str, object],
    ) -> None:
        result = await project_client.call_tool(tool, arguments)

        assert (result.is_error, len(index_loads) <= 1) == (False, True)

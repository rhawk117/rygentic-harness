"""map_python_calls over MCP: per-module reference summaries and one symbol's references."""

from collections.abc import Callable

import pytest
from mcp import Client
from mcp.types import CallToolResult
from python_harness.calls.services import find_symbol_references_for, map_call_sites_for
from python_harness.core.output import to_json_value
from python_harness.core.tests.support import JsonDocument
from python_harness.core.workspace import Workspace
from python_harness.tools.tests.support import document_of

TOOL = 'map_python_calls'


@pytest.mark.anyio
class TestMapPythonCalls:
    PATHS = ('src/shop/pricing.py',)
    SYMBOL = 'price'

    async def test_result_is_the_calls_report_as_json(
        self,
        project_client: Client,
        shop: Workspace,
        project_report_of: Callable[[CallToolResult], JsonDocument],
    ) -> None:
        result = await project_client.call_tool(TOOL, {'paths': list(self.PATHS)})

        expected = map_call_sites_for(shop, self.PATHS)
        assert (result.is_error, project_report_of(result)) == (False, to_json_value(expected))

    async def test_symbol_result_is_the_references_report_as_json(
        self,
        project_client: Client,
        shop: Workspace,
        project_report_of: Callable[[CallToolResult], JsonDocument],
    ) -> None:
        arguments = {'paths': list(self.PATHS), 'symbol': self.SYMBOL}

        result = await project_client.call_tool(TOOL, arguments)

        expected = find_symbol_references_for(shop, self.PATHS, self.SYMBOL)
        assert (result.is_error, project_report_of(result)) == (False, to_json_value(expected))

    @pytest.mark.usefixtures('shop')
    async def test_calls_cover_the_given_paths(self, project_client: Client) -> None:
        calls = document_of(await project_client.call_tool(TOOL, {'paths': list(self.PATHS)}))

        assert [module['metrics']['path'] for module in calls['modules']] == list(self.PATHS)

    @pytest.mark.usefixtures('shop')
    async def test_symbol_lists_its_references(self, project_client: Client) -> None:
        arguments = {'paths': list(self.PATHS), 'symbol': self.SYMBOL}

        found = document_of(await project_client.call_tool(TOOL, arguments))

        contexts = [item['context'] for item in found['symbols'][0]['references']]
        assert contexts == ['import', 'call']


@pytest.mark.anyio
@pytest.mark.usefixtures('shop')
class TestWorkspaceDiagnostics:
    async def test_map_python_calls_reports_the_workspace_in_its_diagnostics(
        self, project_client: Client
    ) -> None:
        result = await project_client.call_tool(TOOL, {'paths': list(TestMapPythonCalls.PATHS)})

        diagnostics = document_of(result)['diagnostics']
        assert (result.is_error, sorted(diagnostics)) == (
            False,
            ['external_packages', 'fallback_diagnostics', 'source_roots'],
        )

"""map_python_calls over MCP: per-module reference summaries and one symbol's references."""

from collections.abc import Callable
from typing import ClassVar

import pytest
from mcp import Client
from mcp.types import CallToolResult
from python_harness import server
from python_harness.calls.services import find_symbol_references_for, map_call_sites_for
from python_harness.core.output import MINIMUM_BUDGET, to_json_value
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.tests.support import JsonDocument
from python_harness.core.workspace import Workspace
from python_harness.tools.tests.support import document_of, text_of

TOOL = 'map_python_calls'


@pytest.mark.anyio
class TestMapPythonCalls:
    PATHS = ('src/shop/pricing.py',)
    SYMBOL = 'price'

    async def test_full_result_is_the_calls_report_as_json(
        self,
        project_client: Client,
        shop: Workspace,
        project_report_of: Callable[[CallToolResult], JsonDocument],
    ) -> None:
        result = await project_client.call_tool(TOOL, {'paths': list(self.PATHS), 'detail': 'full'})

        expected = map_call_sites_for(shop, self.PATHS)
        assert (result.is_error, project_report_of(result)) == (False, to_json_value(expected))

    async def test_full_symbol_result_is_the_references_report_as_json(
        self,
        project_client: Client,
        shop: Workspace,
        project_report_of: Callable[[CallToolResult], JsonDocument],
    ) -> None:
        arguments = {'paths': list(self.PATHS), 'symbol': self.SYMBOL, 'detail': 'full'}

        result = await project_client.call_tool(TOOL, arguments)

        expected = find_symbol_references_for(shop, self.PATHS, self.SYMBOL)
        assert (result.is_error, project_report_of(result)) == (False, to_json_value(expected))

    @pytest.mark.usefixtures('shop')
    async def test_full_calls_cover_the_given_paths(self, project_client: Client) -> None:
        arguments = {'paths': list(self.PATHS), 'detail': 'full'}

        calls = document_of(await project_client.call_tool(TOOL, arguments))['result']

        assert [module['metrics']['path'] for module in calls['modules']] == list(self.PATHS)

    @pytest.mark.usefixtures('shop')
    async def test_full_symbol_lists_its_references(self, project_client: Client) -> None:
        arguments = {'paths': list(self.PATHS), 'symbol': self.SYMBOL, 'detail': 'full'}

        found = document_of(await project_client.call_tool(TOOL, arguments))['result']

        contexts = [item['context'] for item in found['symbols'][0]['references']]
        assert contexts == ['import', 'call']


@pytest.mark.anyio
class TestBudgetedCallsOutput:
    CALLS_PROJECT: ClassVar[dict[str, str]] = {
        'pyproject.toml': """
            [project]
            name = "calls-project"
            version = "0.1.0"
            requires-python = ">=3.14"
        """,
        'src/pkg/alpha.py': """
            from .beta import beta
            from .gamma import gamma

            def alpha() -> None:
                beta()
                gamma()
        """,
        'src/pkg/beta.py': """
            def beta() -> None:
                return None
        """,
        'src/pkg/gamma.py': """
            def gamma() -> None:
                return None
        """,
    }
    SYMBOL_CATEGORIES: ClassVar[dict[str, int]] = {
        'external': 0,
        'internal_only': 0,
        'unreferenced': 0,
    }

    @pytest.fixture
    def calls_project(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.CALLS_PROJECT)

    @pytest.fixture
    def many_modules_project(self, project_builder: ProjectBuilder) -> Workspace:
        files = {
            'pyproject.toml': """
                [project]
                name = "many-calls"
                version = "0.1.0"
                requires-python = ">=3.14"
            """
        }
        files.update({f'src/pkg/module_{index:02}.py': '' for index in range(21)})
        return project_builder.write(files)

    @pytest.mark.usefixtures('calls_project')
    async def test_default_summary_has_exact_ranking_narrowing_and_counts(
        self, project_client: Client
    ) -> None:
        document = document_of(await project_client.call_tool(TOOL, {'paths': ['src/pkg']}))

        assert (
            document['detail'],
            document['budget'],
            document['degraded'],
            document['truncated'],
            document['tokens'] <= 4000,
        ) == ('summary', 4000, False, False, True)
        assert document['result'] == {
            'counts': {
                'modules': 3,
                'symbol_categories': {'external': 2, 'internal_only': 0, 'unreferenced': 1},
                'unparsable': 0,
            },
            'modules': [
                {
                    'path': 'src/pkg/alpha.py',
                    'fan_in': 0,
                    'fan_out': 2,
                    'max_function_statements': 2,
                },
                {
                    'path': 'src/pkg/beta.py',
                    'fan_in': 1,
                    'fan_out': 0,
                    'max_function_statements': 1,
                },
                {
                    'path': 'src/pkg/gamma.py',
                    'fan_in': 1,
                    'fan_out': 0,
                    'max_function_statements': 1,
                },
            ],
            'top_referenced_symbols': [
                {'path': 'src/pkg/beta.py', 'name': 'beta', 'kind': 'function', 'references': 2},
                {'path': 'src/pkg/gamma.py', 'name': 'gamma', 'kind': 'function', 'references': 2},
            ],
            'narrowing': {'paths': ['src/pkg'], 'symbol': None, 'detail': 'full'},
        }

    @pytest.mark.usefixtures('calls_project')
    async def test_symbol_summary_has_exact_counts_and_narrowing(
        self, project_client: Client
    ) -> None:
        arguments = {'paths': ['src/pkg'], 'symbol': 'beta'}

        document = document_of(await project_client.call_tool(TOOL, arguments))

        assert document['result'] == {
            'counts': {'symbols': 1, 'references': 2, 'unparsable': 0},
            'top_referenced_symbols': [
                {'path': 'src/pkg/beta.py', 'name': 'beta', 'kind': 'function', 'references': 2}
            ],
            'narrowing': {'paths': ['src/pkg'], 'symbol': 'beta', 'detail': 'full'},
        }

    @pytest.mark.usefixtures('many_modules_project')
    async def test_many_modules_mark_the_summary_truncated_and_fit_the_budget(
        self, project_client: Client
    ) -> None:
        document = document_of(await project_client.call_tool(TOOL, {'paths': ['src/pkg']}))

        assert (
            document['detail'],
            document['degraded'],
            document['truncated'],
            document['tokens'] <= 4000,
        ) == ('summary', False, True, True)
        assert document['result']['counts'] == {
            'modules': 21,
            'symbol_categories': self.SYMBOL_CATEGORIES,
            'unparsable': 0,
        }
        assert [module['path'] for module in document['result']['modules']] == [
            f'src/pkg/module_{index:02}.py' for index in range(20)
        ]

    @pytest.mark.usefixtures('many_modules_project')
    async def test_counts_detail_fits_the_minimum_budget(self, project_client: Client) -> None:
        arguments = {'paths': ['src/pkg'], 'detail': 'counts', 'budget': MINIMUM_BUDGET}

        document = document_of(await project_client.call_tool(TOOL, arguments))

        assert (
            document['detail'],
            document['budget'],
            document['degraded'],
            document['truncated'],
            document['tokens'] <= MINIMUM_BUDGET,
        ) == ('counts', MINIMUM_BUDGET, False, False, True)
        assert document['result'] == {
            'modules': 21,
            'symbol_categories': self.SYMBOL_CATEGORIES,
            'unparsable': 0,
        }

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize('detail', ['full', 'summary', 'counts'])
    async def test_every_detail_returns_the_envelope_with_the_workspace(
        self, project_client: Client, detail: str
    ) -> None:
        arguments = {'paths': list(TestMapPythonCalls.PATHS), 'detail': detail}

        result = await project_client.call_tool(TOOL, arguments)

        document = document_of(result)
        assert (result.is_error, sorted(document), sorted(document['workspace'])) == (
            False,
            ['budget', 'degraded', 'detail', 'result', 'tokens', 'truncated', 'workspace'],
            ['external_packages', 'fallback_diagnostics', 'source_roots'],
        )

    @pytest.mark.usefixtures('shop')
    async def test_a_budget_under_the_minimum_is_a_tool_error(self, project_client: Client) -> None:
        arguments = {'paths': list(TestMapPythonCalls.PATHS), 'budget': MINIMUM_BUDGET - 1}

        result = await project_client.call_tool(TOOL, arguments)

        assert (result.is_error, str(MINIMUM_BUDGET) in text_of(result)) == (True, True)

    @pytest.mark.usefixtures('shop')
    async def test_a_document_that_cannot_fit_as_counts_is_a_tool_error(
        self, project_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server, 'workspace_diagnostics', lambda _: {'text': 'word ' * 2000})

        arguments = {'paths': list(TestMapPythonCalls.PATHS), 'budget': MINIMUM_BUDGET}

        result = await project_client.call_tool(TOOL, arguments)

        assert (result.is_error, 'does not fit' in text_of(result)) == (True, True)

    async def test_summary_and_4000_tokens_are_the_defaults(self, project_client: Client) -> None:
        tools = {tool.name: tool for tool in (await project_client.list_tools()).tools}

        properties = tools[TOOL].input_schema['properties']
        assert (properties['detail']['default'], properties['budget']['default']) == (
            'summary',
            4000,
        )

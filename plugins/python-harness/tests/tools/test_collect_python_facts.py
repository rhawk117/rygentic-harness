"""collect_python_facts over MCP: the facts report as JSON for paths inside the project."""

from collections.abc import Callable
from types import MappingProxyType

import pytest
from mcp import Client
from mcp.types import CallToolResult
from python_harness import server
from python_harness.core.output import MINIMUM_BUDGET, to_json_value
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.tests.support import JsonDocument
from python_harness.core.workspace import Workspace
from python_harness.facts.services import build_review_catalog, collect_facts
from python_harness.tools.tests.support import document_of, text_of

TOOL = 'collect_python_facts'


@pytest.mark.anyio
class TestCollectPythonFacts:
    PATHS = ('src/shop',)

    async def test_full_result_is_the_facts_report_as_json(
        self,
        project_client: Client,
        shop: Workspace,
        project_report_of: Callable[[CallToolResult], JsonDocument],
    ) -> None:
        result = await project_client.call_tool(TOOL, {'paths': list(self.PATHS), 'detail': 'full'})

        expected = collect_facts(shop, self.PATHS, build_review_catalog())
        assert (result.is_error, project_report_of(result)) == (False, to_json_value(expected))

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        ('paths', 'expected'),
        [
            pytest.param(['src/shop/pricing.py'], ['src/shop/pricing.py'], id='one-file'),
            pytest.param(
                ['src/shop', 'src/shop/pricing.py'],
                ['src/shop/__init__.py', 'src/shop/cli.py', 'src/shop/pricing.py'],
                id='overlapping-paths-report-a-module-once',
            ),
        ],
    )
    async def test_full_facts_cover_the_given_paths(
        self,
        project_client: Client,
        project_report_of: Callable[[CallToolResult], JsonDocument],
        paths: list[str],
        expected: list[str],
    ) -> None:
        facts = project_report_of(
            await project_client.call_tool(TOOL, {'paths': paths, 'detail': 'full'})
        )

        assert [module['path'] for module in facts['modules']] == expected

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        ('option', 'reported'),
        [
            pytest.param({}, False, id='left-out-by-default'),
            pytest.param({'with_function_shapes': True}, True, id='reported-on-request'),
        ],
    )
    async def test_function_shapes_are_reported_only_on_request(
        self,
        project_client: Client,
        project_report_of: Callable[[CallToolResult], JsonDocument],
        option: dict[str, bool],
        reported: bool,
    ) -> None:
        arguments = {'paths': ['src/shop/pricing.py'], 'detail': 'full', **option}

        facts = project_report_of(await project_client.call_tool(TOOL, arguments))

        assert ('function_shape' in facts['modules'][0]['counts']) is reported


@pytest.mark.anyio
class TestBudgetedFactsOutput:
    PATHS = TestCollectPythonFacts.PATHS
    FACTS_PROJECT = MappingProxyType(
        {
            'pyproject.toml': """
                [project]
                name = "facts"
                version = "0.1.0"
                requires-python = ">=3.14"
            """,
            'src/pkg/empty.py': '',
            'src/pkg/loader.py': """
                # loader
                def load(items=[]):  # cache
                    '''Return the items.'''
                    return items


                del load
            """,
        }
    )

    @pytest.fixture
    def facts_project(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FACTS_PROJECT)

    @pytest.fixture
    def many_modules_project(self, project_builder: ProjectBuilder) -> Workspace:
        files = {
            'pyproject.toml': """
                [project]
                name = "many-modules"
                version = "0.1.0"
                requires-python = ">=3.14"
            """
        }
        files.update({f'src/pkg/module_{index:02}.py': '' for index in range(21)})
        return project_builder.write(files)

    @pytest.mark.usefixtures('facts_project')
    async def test_default_summary_has_exact_ordering_narrowing_and_counts(
        self, project_client: Client
    ) -> None:
        result = await project_client.call_tool(TOOL, {'paths': ['src/pkg']})
        document = document_of(result)

        assert (
            result.is_error,
            document['detail'],
            document['budget'],
            document['degraded'],
            document['truncated'],
        ) == (False, 'summary', 4000, False, False)
        assert document['tokens'] <= 4000
        assert document['result'] == {
            'counts': {
                'modules': 2,
                'lines': 7,
                'facts': 4,
                'fact_kinds': {'comment': 2, 'del_statement': 1, 'docstring': 1},
                'unparsable': 0,
            },
            'modules': [
                {'path': 'src/pkg/loader.py', 'lines': 7, 'facts': 4},
                {'path': 'src/pkg/empty.py', 'lines': 0, 'facts': 0},
            ],
            'narrowing': {
                'paths': ['src/pkg'],
                'detail': 'full',
                'with_function_shapes': False,
            },
        }

    @pytest.mark.usefixtures('facts_project')
    async def test_counts_detail_fits_the_minimum_budget(self, project_client: Client) -> None:
        arguments = {'paths': ['src/pkg'], 'detail': 'counts', 'budget': MINIMUM_BUDGET}

        result = await project_client.call_tool(TOOL, arguments)
        document = document_of(result)

        assert (
            result.is_error,
            document['detail'],
            document['budget'],
            document['degraded'],
            document['truncated'],
        ) == (False, 'counts', MINIMUM_BUDGET, False, False)
        assert document['tokens'] <= MINIMUM_BUDGET
        assert document['result'] == {
            'modules': 2,
            'lines': 7,
            'facts': 4,
            'fact_kinds': {'comment': 2, 'del_statement': 1, 'docstring': 1},
            'unparsable': 0,
        }

    @pytest.mark.usefixtures('many_modules_project')
    async def test_omitted_ranked_modules_mark_the_summary_truncated(
        self, project_client: Client
    ) -> None:
        document = document_of(await project_client.call_tool(TOOL, {'paths': ['src/pkg']}))

        assert document['truncated'] is True
        assert document['degraded'] is False
        assert document['result']['counts']['modules'] == 21
        assert [module['path'] for module in document['result']['modules']] == [
            f'src/pkg/module_{index:02}.py' for index in range(20)
        ]

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize('detail', ['full', 'summary', 'counts'])
    async def test_every_detail_returns_the_envelope_with_the_workspace(
        self, project_client: Client, detail: str
    ) -> None:
        arguments = {'paths': list(self.PATHS), 'detail': detail}

        result = await project_client.call_tool(TOOL, arguments)

        document = document_of(result)
        assert (result.is_error, sorted(document), sorted(document['workspace'])) == (
            False,
            ['budget', 'degraded', 'detail', 'result', 'tokens', 'truncated', 'workspace'],
            ['external_packages', 'fallback_diagnostics', 'source_roots'],
        )

    @pytest.mark.usefixtures('shop')
    async def test_a_budget_under_the_minimum_is_a_tool_error(self, project_client: Client) -> None:
        arguments = {'paths': list(self.PATHS), 'budget': MINIMUM_BUDGET - 1}

        result = await project_client.call_tool(TOOL, arguments)

        assert (result.is_error, str(MINIMUM_BUDGET) in text_of(result)) == (True, True)

    @pytest.mark.usefixtures('shop')
    async def test_a_document_that_cannot_fit_as_counts_is_a_tool_error(
        self, project_client: Client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server, 'workspace_diagnostics', lambda _: {'text': 'word ' * 2000})

        result = await project_client.call_tool(
            TOOL, {'paths': list(self.PATHS), 'budget': MINIMUM_BUDGET}
        )

        assert (result.is_error, 'does not fit' in text_of(result)) == (True, True)


@pytest.mark.anyio
class TestBudgetDefaults:
    async def test_summary_and_4000_tokens_are_the_defaults(self, project_client: Client) -> None:
        tools = {tool.name: tool for tool in (await project_client.list_tools()).tools}

        properties = tools[TOOL].input_schema['properties']
        assert (properties['detail']['default'], properties['budget']['default']) == (
            'summary',
            4000,
        )

"""End to end over MCP: schemas, search tiers, paginated reads, model-visible errors."""

from pathlib import Path

import pytest
from mcp import Client
from mcp.types import CallToolResult
from python_harness.core.tests.fixtures import STUBBED_UV_DIAGNOSTIC, ProjectBuilder
from python_harness.core.tests.support import JsonDocument
from python_harness.core.workspace import open_workspace
from python_harness.documentation.tests.support import DOCS_VERSION, DocsSite, standard_pages
from python_harness.imports.services import load_project_index
from python_harness.tools.project import workspace_diagnostics
from python_harness.tools.tests.support import document_of

OS_PATH_PAGE_PATH = f'/{DOCS_VERSION}/library/os.path.html'
INVENTORY_PATH = f'/{DOCS_VERSION}/objects.inv'
OFFICIAL_ORIGIN = ('https', 'docs.python.org')
FOREIGN_HOST = 'mirror.example'
VERSION_PATTERN = r'^3\.(0|[1-9][0-9]?)$'
VERSION_HELP = (
    'Python minor version such as 3.13.\n\n'
    'Read requires-python in pyproject.toml or .python-version first; do not guess.'
)
EIGHT_TOOLS = (
    'search_python_docs',
    'read_python_docs',
    'survey',
    'gate',
    'plan_review_surface',
    'collect_python_facts',
    'map_python_calls',
    'check_citations',
)
BUDGETED_TOOLS = ('collect_python_facts', 'map_python_calls')
PROJECT_DIAGNOSTIC_ARGUMENTS = (
    pytest.param('survey', {}, id='survey'),
    pytest.param(
        'collect_python_facts', {'paths': ['src/shop/pricing.py']}, id='collect-python-facts'
    ),
    pytest.param('map_python_calls', {'paths': ['src/shop/pricing.py']}, id='map-python-calls'),
    pytest.param('check_citations', {'text': 'text'}, id='check-citations'),
    pytest.param('plan_review_surface', {'paths': ['src']}, id='plan-review-surface'),
)


async def call(client: Client, tool: str, **arguments: str | int) -> CallToolResult:
    return await client.call_tool(tool, {'version': DOCS_VERSION, **arguments})


def text_of(result: CallToolResult) -> str:
    return ''.join(getattr(block, 'text', '') for block in result.content)


def dereferenced(schema: JsonDocument, node: JsonDocument) -> JsonDocument:
    reference = node.get('$ref')
    if reference is None:
        return node
    target = schema['$defs'][reference.removeprefix('#/$defs/')]
    own = {key: value for key, value in node.items() if key != '$ref'}
    return dereferenced(schema, target) | own


@pytest.mark.anyio
class TestToolSchemas:
    async def test_the_server_lists_exactly_its_eight_tools(self, docs_client: Client) -> None:
        tools = (await docs_client.list_tools()).tools
        assert sorted(tool.name for tool in tools) == [
            'check_citations',
            'collect_python_facts',
            'gate',
            'map_python_calls',
            'plan_review_surface',
            'read_python_docs',
            'search_python_docs',
            'survey',
        ]

    async def test_every_tool_takes_object_arguments(self, docs_client: Client) -> None:
        tools = (await docs_client.list_tools()).tools
        assert {tool.input_schema['type'] for tool in tools} == {'object'}

    async def test_only_search_declares_structured_output(self, docs_client: Client) -> None:
        tools = (await docs_client.list_tools()).tools
        structured = [tool.name for tool in tools if tool.output_schema is not None]
        assert structured == ['search_python_docs']

    async def test_each_tool_takes_its_fields_as_flat_arguments(self, docs_client: Client) -> None:
        tools = (await docs_client.list_tools()).tools
        assert {tool.name: set(tool.input_schema['properties']) for tool in tools} == {
            'search_python_docs': {'version', 'query', 'limit'},
            'read_python_docs': {'version', 'symbol', 'offset', 'max_chars'},
            'collect_python_facts': {'paths', 'with_function_shapes', 'detail', 'budget'},
            'map_python_calls': {'paths', 'symbol', 'detail', 'budget'},
            'check_citations': {'path', 'text'},
            'plan_review_surface': {'paths', 'diff_base', 'diff_head'},
            'survey': set(),
            'gate': set(),
        }

    async def test_only_the_budgeted_tools_take_detail_and_budget(
        self, docs_client: Client
    ) -> None:
        tools = (await docs_client.list_tools()).tools
        budgeted = [
            tool.name
            for tool in tools
            if {'detail', 'budget'} & set(tool.input_schema['properties'])
        ]
        assert sorted(budgeted) == sorted(BUDGETED_TOOLS)

    @pytest.mark.parametrize('name', BUDGETED_TOOLS)
    async def test_budget_and_detail_describe_themselves_in_the_schema(
        self, docs_client: Client, name: str
    ) -> None:
        tools = {tool.name: tool for tool in (await docs_client.list_tools()).tools}
        schema = tools[name].input_schema
        budget = dereferenced(schema, schema['properties']['budget'])
        detail = dereferenced(schema, schema['properties']['detail'])
        assert (budget['minimum'], budget['default'], bool(budget['description'])) == (
            256,
            4000,
            True,
        )
        assert (detail['enum'], bool(detail['description'])) == (
            ['full', 'summary', 'counts'],
            True,
        )

    async def test_no_tool_takes_a_project_root(self, docs_client: Client) -> None:
        tools = (await docs_client.list_tools()).tools
        rooted = [tool.name for tool in tools if 'project_root' in tool.input_schema['properties']]
        assert rooted == []

    async def test_gate_is_not_read_only_and_survey_is(self, docs_client: Client) -> None:
        tools = {tool.name: tool for tool in (await docs_client.list_tools()).tools}
        assert tools['gate'].annotations is not None
        assert tools['survey'].annotations is not None
        assert (
            tools['gate'].annotations.read_only_hint,
            tools['survey'].annotations.read_only_hint,
        ) == (False, True)

    async def test_the_instructions_name_all_eight_tools(self, docs_client: Client) -> None:
        instructions = docs_client.instructions or ''
        assert [name for name in EIGHT_TOOLS if name not in instructions] == []

    @pytest.mark.parametrize(
        'name',
        [
            pytest.param('search_python_docs', id='search'),
            pytest.param('read_python_docs', id='read'),
        ],
    )
    async def test_version_argument_keeps_its_pattern_and_help(
        self, docs_client: Client, name: str
    ) -> None:
        tools = {tool.name: tool for tool in (await docs_client.list_tools()).tools}
        schema = tools[name].input_schema
        version = dereferenced(schema, schema['properties']['version'])
        assert (version['type'], version['pattern'], version['description']) == (
            'string',
            VERSION_PATTERN,
            VERSION_HELP,
        )


@pytest.mark.anyio
@pytest.mark.usefixtures('shop')
class TestProjectDiagnostics:
    @pytest.mark.parametrize(('tool', 'arguments'), PROJECT_DIAGNOSTIC_ARGUMENTS)
    async def test_project_tools_add_workspace_diagnostics(
        self, project_client: Client, tool: str, arguments: dict[str, object]
    ) -> None:
        result = await project_client.call_tool(tool, arguments)

        assert result.is_error is False
        diagnostics = document_of(result)['workspace']
        assert diagnostics['source_roots'] == ['src']
        assert diagnostics['fallback_diagnostics'] == [STUBBED_UV_DIAGNOSTIC]


class TestWorkspaceDiagnostics:
    def test_unindexed_workspace_package_has_a_relative_directory(
        self, project_builder: ProjectBuilder
    ) -> None:
        project_builder.write(
            {
                'members/one/src/one/__init__.py': 'from shared import value\n',
                'members/two/src/shared/py.typed': '',
            }
        )
        root = project_builder.root
        members = (root.joinpath('members', 'one'), root.joinpath('members', 'two'))

        def list_members(_: Path) -> str:
            return '\n'.join(str(member) for member in members)

        workspace = open_workspace(root, uv_runner=list_members)
        graph = load_project_index(workspace).graph

        assert workspace_diagnostics(workspace, graph)['unindexed_packages'] == [
            {'name': 'shared', 'directory': 'members/two/src/shared'}
        ]


@pytest.mark.anyio
class TestSearchPythonDocs:
    async def test_returns_tier_labeled_matches(self, docs_client: Client) -> None:
        result = await call(docs_client, 'search_python_docs', query='path join')
        assert result.structured_content is not None
        first = result.structured_content['matches'][0]
        assert (first['name'], first['match']) == ('os.path.join', 'prefix')

    async def test_unpublished_version_is_remembered(
        self, docs_client: Client, docs_site: DocsSite
    ) -> None:
        arguments = {'version': '3.99', 'query': 'json'}
        results = [await docs_client.call_tool('search_python_docs', arguments) for _ in range(2)]
        assert [result.is_error for result in results] == [True, True]
        assert 'not published' in text_of(results[1])
        assert docs_site.request_count('/3.99/objects.inv') == 1


@pytest.mark.anyio
class TestReadPythonDocs:
    async def test_definition_page_has_header_body_and_end_marker(
        self, docs_client: Client
    ) -> None:
        lines = text_of(await call(docs_client, 'read_python_docs', symbol='os.path.join'))
        header, *_, footer = lines.splitlines()
        assert header == (
            'os.path.join (function) | Python 3.13 documentation |'
            ' https://docs.python.org/3.13/library/os.path.html#os.path.join'
        )
        assert footer.startswith('End of section')

    async def test_long_sections_paginate_by_offset(self, docs_client: Client) -> None:
        first = text_of(
            await call(docs_client, 'read_python_docs', symbol='os.path', max_chars=500)
        )
        assert first.endswith('characters shown).')
        assert 'offset=500 ' in first
        second = text_of(
            await call(
                docs_client,
                'read_python_docs',
                symbol='os.path',
                offset=500,
                max_chars=500,
            )
        )
        assert first.splitlines()[0] == second.splitlines()[0]

    async def test_symbols_on_one_page_share_one_download(
        self, docs_client: Client, docs_site: DocsSite
    ) -> None:
        for symbol in ('os.path.join', 'os.path.isfile', 'os.path.join'):
            await call(docs_client, 'read_python_docs', symbol=symbol)
        assert docs_site.request_count(OS_PATH_PAGE_PATH) == 1
        assert docs_site.request_count(INVENTORY_PATH) == 1

    @pytest.mark.parametrize(
        ('arguments', 'expected'),
        [
            pytest.param(
                {'symbol': 'os.path.joinpath'},
                'Closest names: os.path.join',
                id='unknown-symbol-suggests',
            ),
            pytest.param(
                {'symbol': 'os.path.join', 'offset': 99_999},
                'exceeds the section length',
                id='offset-past-end',
            ),
            pytest.param(
                {'symbol': 'broken.anchor'},
                'missing from the official page',
                id='stale-anchor',
            ),
        ],
    )
    async def test_failures_reach_the_model_as_actionable_errors(
        self, docs_client: Client, arguments: dict[str, str | int], expected: str
    ) -> None:
        result = await call(docs_client, 'read_python_docs', **arguments)
        assert result.is_error
        assert expected in text_of(result)


@pytest.mark.anyio
class TestRequestOrigins:
    async def test_both_tools_fetch_only_from_the_official_host_over_https(
        self, docs_client: Client, docs_site: DocsSite
    ) -> None:
        await call(docs_client, 'search_python_docs', query='path join')
        await call(docs_client, 'read_python_docs', symbol='os.path.join')
        assert docs_site.requested_origins() == {OFFICIAL_ORIGIN}


@pytest.mark.anyio
class TestRedirectToAnotherHost:
    @pytest.fixture
    def docs_site(self, request: pytest.FixtureRequest) -> DocsSite:
        path = request.param
        return DocsSite(
            pages=standard_pages(),
            redirects={f'https://docs.python.org{path}': f'https://{FOREIGN_HOST}{path}'},
        )

    @pytest.mark.parametrize(
        ('docs_site', 'tool', 'arguments'),
        [
            pytest.param(
                INVENTORY_PATH, 'search_python_docs', {'query': 'path join'}, id='inventory'
            ),
            pytest.param(
                OS_PATH_PAGE_PATH, 'read_python_docs', {'symbol': 'os.path.join'}, id='page'
            ),
        ],
        indirect=['docs_site'],
    )
    async def test_the_redirect_is_reported_and_never_followed(
        self, docs_client: Client, docs_site: DocsSite, tool: str, arguments: dict[str, str]
    ) -> None:
        result = await call(docs_client, tool, **arguments)
        assert result.is_error
        assert 'HTTP 302' in text_of(result)
        assert docs_site.requested_origins() == {OFFICIAL_ORIGIN}

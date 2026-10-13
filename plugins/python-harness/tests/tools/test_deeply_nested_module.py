"""One module too deeply nested to walk is reported, and does not fail the project tools."""

import pytest
from mcp import Client
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.tools.tests.support import document_of

DEEP = 'src/deep/chain.py'
SIBLING = 'src/deep/plain.py'
ATTRIBUTE_CHAIN = 'x = a' + '.b' * 3000 + '\n'
DEEP_SOURCES = [
    pytest.param(ATTRIBUTE_CHAIN, id='attribute-chain'),
    pytest.param('x = ' + '1 + ' * 3000 + '1\n', id='binary-operator-chain'),
    pytest.param('x = f' + '()' * 3000 + '\n', id='call-chain'),
]


def write_project(project_builder: ProjectBuilder, deep_source: str) -> None:
    project_builder.write(
        {DEEP: deep_source, SIBLING: 'def plain() -> int:\n    return 1\n'},
    )


@pytest.fixture
def deep_project(project_builder: ProjectBuilder) -> None:
    write_project(project_builder, ATTRIBUTE_CHAIN)


@pytest.mark.anyio
class TestDeeplyNestedModule:
    @pytest.mark.usefixtures('deep_project')
    async def test_calls_still_answer_for_a_sibling(self, project_client: Client) -> None:
        result = await project_client.call_tool(
            'map_python_calls', {'paths': [SIBLING], 'detail': 'full'}
        )

        calls = document_of(result)['result']
        assert (result.is_error, [item['metrics']['path'] for item in calls['modules']]) == (
            False,
            [SIBLING],
        )

    @pytest.mark.usefixtures('deep_project')
    async def test_calls_list_the_requested_module_as_unparsable(
        self, project_client: Client
    ) -> None:
        result = await project_client.call_tool(
            'map_python_calls', {'paths': [DEEP], 'detail': 'full'}
        )

        calls = document_of(result)['result']
        reported = ([item['path'] for item in calls['unparsable']], calls['modules'])
        assert (result.is_error, reported) == (False, ([DEEP], []))

    @pytest.mark.usefixtures('deep_project')
    async def test_symbol_search_answers_with_the_module_in_the_project(
        self, project_client: Client
    ) -> None:
        arguments = {'paths': [SIBLING], 'symbol': 'plain', 'detail': 'full'}

        result = await project_client.call_tool('map_python_calls', arguments)

        assert result.is_error is False

    @pytest.mark.parametrize('deep_source', DEEP_SOURCES)
    async def test_each_deep_shape_is_reported_by_facts_and_answered_by_calls(
        self, project_client: Client, project_builder: ProjectBuilder, deep_source: str
    ) -> None:
        write_project(project_builder, deep_source)

        facts = await project_client.call_tool(
            'collect_python_facts', {'paths': ['src/deep'], 'detail': 'full'}
        )
        calls = await project_client.call_tool(
            'map_python_calls', {'paths': [DEEP], 'detail': 'full'}
        )

        unparsable = [item['path'] for item in document_of(facts)['result']['unparsable']]
        assert (facts.is_error, unparsable, calls.is_error) == (False, [DEEP], False)

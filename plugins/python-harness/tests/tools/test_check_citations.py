"""check_citations over MCP: a document inside the project or inline text, exactly one."""

from collections.abc import Callable

import pytest
from mcp import Client
from mcp.types import CallToolResult
from python_harness.citations.services import check_citations, check_citations_in_text
from python_harness.core.output import to_json_value
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.tests.support import JsonDocument
from python_harness.core.workspace import Workspace
from python_harness.tools.check_citations.schema import INLINE_DOCUMENT_NAME
from python_harness.tools.tests.support import SHOP_PROJECT, document_of, text_of

TOOL = 'check_citations'
REVIEW = 'REVIEW.md'
PYLENS_RETURN = '| src/shop/pricing.py:2 | `return total` | returns its argument |\n'
MALFORMED_RETURN = (
    '| src/shop/pricing.py:2 | `return total` | returns its argument |\n'
    '| src/shop/pricing.py#L2 | `return total` | returns its argument |\n'
)


@pytest.mark.anyio
class TestDocumentInTheProject:
    async def test_result_is_the_citation_report_as_json(
        self,
        project_client: Client,
        shop: Workspace,
        project_report_of: Callable[[CallToolResult], JsonDocument],
    ) -> None:
        result = await project_client.call_tool(TOOL, {'path': REVIEW})

        expected = check_citations(shop, shop.root.joinpath(REVIEW))
        assert (result.is_error, project_report_of(result)) == (False, to_json_value(expected))

    @pytest.mark.usefixtures('shop')
    async def test_a_failed_citation_is_a_report_not_an_error(self, project_client: Client) -> None:
        result = await project_client.call_tool(TOOL, {'path': REVIEW})

        report = document_of(result)
        assert (result.is_error, report['document'], report['passed']) == (False, REVIEW, False)


@pytest.mark.anyio
class TestInlineText:
    MALFORMED_ROWS = (1, [2], False)

    async def test_result_is_the_citation_report_as_json(
        self,
        project_client: Client,
        shop: Workspace,
        project_report_of: Callable[[CallToolResult], JsonDocument],
    ) -> None:
        result = await project_client.call_tool(TOOL, {'text': PYLENS_RETURN})

        expected = check_citations_in_text(shop, PYLENS_RETURN, INLINE_DOCUMENT_NAME)
        assert (result.is_error, project_report_of(result)) == (False, to_json_value(expected))

    @pytest.mark.usefixtures('shop')
    async def test_text_is_checked_under_the_inline_name(self, project_client: Client) -> None:
        report = document_of(await project_client.call_tool(TOOL, {'text': PYLENS_RETURN}))

        assert (report['document'], report['passed']) == ('<text>', True)

    @pytest.mark.usefixtures('shop')
    async def test_a_row_without_a_parseable_citation_fails_the_report(
        self, project_client: Client
    ) -> None:
        report = document_of(await project_client.call_tool(TOOL, {'text': MALFORMED_RETURN}))

        rows = (report['checked'], report['uncited_rows'], report['passed'])
        assert rows == self.MALFORMED_ROWS

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize('text', ['[]', '{"a": 1}', 'null'])
    async def test_text_that_is_a_whole_json_value_is_checked_as_text(
        self, project_client: Client, text: str
    ) -> None:
        result = await project_client.call_tool(TOOL, {'text': text})

        report = document_of(result)
        assert (result.is_error, report['document'], report['checked']) == (False, '<text>', 0)


@pytest.mark.anyio
class TestDocumentChoice:
    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        'arguments',
        [
            pytest.param({'path': REVIEW, 'text': PYLENS_RETURN}, id='both'),
            pytest.param({}, id='neither'),
        ],
    )
    async def test_both_or_neither_of_path_and_text_is_a_tool_error(
        self, project_client: Client, arguments: dict[str, str]
    ) -> None:
        result = await project_client.call_tool(TOOL, arguments)

        assert (result.is_error, 'exactly one of path and text' in text_of(result)) == (True, True)


@pytest.mark.anyio
class TestUndecodableDocument:
    DOCUMENT = 'LATIN.md'

    @pytest.fixture
    def shop(self, project_builder: ProjectBuilder) -> Workspace:
        workspace = project_builder.write(SHOP_PROJECT)
        document = workspace.root.joinpath(self.DOCUMENT)
        document.write_bytes(b'| src/shop/pricing.py:1 | `caf\xe9` | x |\n')
        return workspace

    @pytest.mark.usefixtures('shop')
    async def test_undecodable_document_is_a_tool_error_with_a_message(
        self, project_client: Client
    ) -> None:
        result = await project_client.call_tool(TOOL, {'path': self.DOCUMENT})

        expected = f'citation document {self.DOCUMENT} is not readable'
        assert (result.is_error, expected in text_of(result)) == (True, True)


@pytest.mark.anyio
@pytest.mark.usefixtures('shop')
class TestWorkspaceDiagnostics:
    async def test_check_citations_reports_the_workspace_in_its_diagnostics(
        self, project_client: Client
    ) -> None:
        result = await project_client.call_tool(TOOL, {'path': REVIEW})

        diagnostics = document_of(result)['diagnostics']
        assert (result.is_error, sorted(diagnostics)) == (
            False,
            ['external_packages', 'fallback_diagnostics', 'source_roots'],
        )

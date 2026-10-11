"""The python-harness MCP server over stdio: Python documentation, and facts about one project."""

import json
import os
from collections.abc import AsyncGenerator, Generator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass

import anyio
import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from python_harness.core.errors import PythonHarnessError
from python_harness.core.output import COMPACT_SEPARATORS, JsonValue, to_json_value
from python_harness.core.uv import run_uv_workspace
from python_harness.core.workspace import UvRunner, Workspace
from python_harness.documentation.repository import documentation_http_client
from python_harness.documentation.services import (
    DocumentationService,
    build_documentation_service,
    call_deadline,
)
from python_harness.documentation.settings import Settings
from python_harness.facts.domain import FactsReport
from python_harness.gate.domain import ConfigKind, GateOptions
from python_harness.gate.fallbacks import RUFF_CONFIG, TY_CONFIG
from python_harness.gate.services import run_gate_for
from python_harness.imports.domain import ProjectIndex
from python_harness.imports.services import load_project_index
from python_harness.survey.services import survey_document, survey_indexed_project
from python_harness.tools.check_citations import use_case as citations_use_case
from python_harness.tools.check_citations.schema import (
    CitationsRequest,
    DocumentPath,
    DocumentText,
)
from python_harness.tools.collect_python_facts import output as facts_output
from python_harness.tools.collect_python_facts import use_case as facts_use_case
from python_harness.tools.collect_python_facts.schema import FactsRequest, FunctionShapes
from python_harness.tools.envelope import (
    DEFAULT_BUDGET,
    Detail,
    ProjectOutput,
    output_options,
    render_budgeted_project_document,
)
from python_harness.tools.map_python_calls import output as calls_output
from python_harness.tools.map_python_calls import use_case as calls_use_case
from python_harness.tools.map_python_calls.schema import CallsRequest, SymbolReference
from python_harness.tools.plan_review_surface import use_case as surface_use_case
from python_harness.tools.plan_review_surface.schema import Revision, SurfaceRequest
from python_harness.tools.project import ProjectPaths, open_project, workspace_diagnostics
from python_harness.tools.read_python_docs import use_case as read_use_case
from python_harness.tools.read_python_docs.schema import (
    DEFAULT_PAGE_CHARACTERS,
    PageCharacters,
    PageOffset,
    ReadRequest,
    SymbolName,
)
from python_harness.tools.search_python_docs import use_case as search_use_case
from python_harness.tools.search_python_docs.schema import (
    DEFAULT_SEARCH_LIMIT,
    SearchLimit,
    SearchRequest,
    SearchResult,
    SymbolQuery,
    VersionText,
)

SERVER_NAME = 'python-harness'
SERVER_INSTRUCTIONS = (
    'Official Python standard-library documentation for a specific Python version.'
    ' Find exact names with search_python_docs, then read them with read_python_docs.'
    ' The other six tools read the Python project at CLAUDE_PROJECT_DIR and return one JSON'
    ' document each: survey, gate, plan_review_surface, collect_python_facts, map_python_calls'
    ' and check_citations. Their paths are relative to that root and cannot leave it.'
)
READ_ONLY_REMOTE = ToolAnnotations(read_only_hint=True, open_world_hint=True)
READ_ONLY_LOCAL = ToolAnnotations(read_only_hint=True, open_world_hint=False)
RUNS_PROJECT_CODE = ToolAnnotations(read_only_hint=False)


@contextmanager
def tool_errors() -> Generator[None]:
    try:
        yield
    except PythonHarnessError as error:
        raise ToolError(str(error)) from error


def render_document(report: object) -> str:
    return json.dumps(to_json_value(report), separators=COMPACT_SEPARATORS)


def render_project_document(report: object, diagnostics: dict[str, JsonValue]) -> str:
    document = to_json_value(report)
    if not isinstance(document, dict):
        msg = 'project reports must serialize to JSON objects'
        raise TypeError(msg)
    return render_document(document | {'workspace': diagnostics})


async def close_client(client: httpx.AsyncClient, timeout_seconds: float) -> None:
    with anyio.move_on_after(timeout_seconds, shield=True):
        await client.aclose()


@asynccontextmanager
async def documentation_service(
    settings: Settings, http_transport: httpx.AsyncBaseTransport | None = None
) -> AsyncGenerator[DocumentationService]:
    async with AsyncExitStack() as stack:
        client = documentation_http_client(settings, http_transport)
        stack.push_async_callback(close_client, client, settings.shutdown_timeout_seconds)
        fills = await stack.enter_async_context(anyio.create_task_group())
        stack.callback(fills.cancel_scope.cancel)
        yield build_documentation_service(settings, client, fills)


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentationTools:
    service: DocumentationService

    async def search_python_docs(
        self,
        *,
        version: VersionText,
        query: SymbolQuery,
        limit: SearchLimit = DEFAULT_SEARCH_LIMIT,
    ) -> SearchResult:
        """Find official Python standard-library symbols by name for one Python version.

        Each match is labeled exact, prefix, or approximate; treat approximate matches
        as guesses and confirm them before relying on them.
        """
        service = self.service
        request = SearchRequest(version=version, query=query, limit=limit)
        with tool_errors(), call_deadline(service.settings.call_timeout_seconds):
            return await search_use_case.run(service, request)

    async def read_python_docs(
        self,
        *,
        version: VersionText,
        symbol: SymbolName,
        offset: PageOffset = 0,
        max_chars: PageCharacters = DEFAULT_PAGE_CHARACTERS,
    ) -> str:
        """Read one symbol's official documentation as Markdown, one page at a time.

        The first line names the symbol, its kind, the documentation version, and the
        source URL; the last line gives the next offset or marks the end of the section.
        """
        service = self.service
        request = ReadRequest(version=version, symbol=symbol, offset=offset, max_chars=max_chars)
        with tool_errors(), call_deadline(service.settings.call_timeout_seconds):
            return await read_use_case.run(service, request)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectTools:
    environment: Mapping[str, str]
    uv_runner: UvRunner

    def open_indexed_project(self) -> tuple[Workspace, ProjectIndex]:
        workspace = open_project(self.environment, self.uv_runner)
        return workspace, load_project_index(workspace)

    def collect_python_facts(
        self,
        *,
        paths: ProjectPaths,
        with_function_shapes: FunctionShapes = False,
        detail: Detail = Detail.SUMMARY,
        budget: int = DEFAULT_BUDGET,
    ) -> str:
        """Collect mechanical AST facts for Python modules of the project, as JSON.

        Each module lists its facts by line and kind, with a count per kind; files that
        cannot be read or parsed are listed under unparsable. The default response is a
        budgeted summary; request detail=full for facts from the requested paths. Facts
        are observations, never verdicts.
        """
        request = FactsRequest(paths=paths, with_function_shapes=with_function_shapes)
        with tool_errors():
            options = output_options(detail=detail, budget=budget)

        def summary(report: FactsReport) -> object:
            return facts_output.facts_summary(
                report, paths=paths, with_function_shapes=with_function_shapes
            )

        output = ProjectOutput(
            options=options,
            summary=summary,
            counts=facts_output.facts_counts,
            summary_truncated=facts_output.facts_summary_is_truncated,
        )
        with tool_errors():
            workspace, index = self.open_indexed_project()
            report = facts_use_case.run(workspace, request)
            diagnostics = workspace_diagnostics(workspace, index.graph)
            return render_budgeted_project_document(report, diagnostics, output)

    def map_python_calls(
        self,
        *,
        paths: ProjectPaths,
        symbol: SymbolReference | None = None,
        detail: Detail = Detail.SUMMARY,
        budget: int = DEFAULT_BUDGET,
    ) -> str:
        """Map where the project references the symbols of the given modules, as JSON.

        Without symbol, each module gets coupling metrics and its symbols grouped by who
        references them. With symbol, every reference of that one symbol is listed by
        path and line. The default response is a budgeted summary; request detail=full
        for references and coupling facts from the requested paths. Resolution is static,
        so dynamic use is not seen.
        """
        request = CallsRequest(paths=paths, symbol=symbol)
        with tool_errors():
            options = output_options(detail=detail, budget=budget)
            workspace, index = self.open_indexed_project()
            report = calls_use_case.run(workspace, index, request)
            diagnostics = workspace_diagnostics(workspace, index.graph)
            return calls_output.render_calls_document(report, request, diagnostics, options=options)

    def check_citations(self, *, path: DocumentPath = '', text: DocumentText = '') -> str:
        """Check every path.py:line citation and its backticked quote in Markdown, as JSON.

        Give exactly one of path and text. The report lists each failing citation with
        its problem and each table row that holds no citation; passed is true when both
        lists are empty. A failed check is a report, not an error.
        """
        request = CitationsRequest(path=path or None, text=text or None)
        with tool_errors():
            workspace, index = self.open_indexed_project()
            report = citations_use_case.run(workspace, request)
            return render_project_document(report, workspace_diagnostics(workspace, index.graph))

    def survey(self) -> str:
        """Survey the project and return its mode, domains and layout as JSON."""
        with tool_errors():
            workspace, index = self.open_indexed_project()
            report = survey_document(survey_indexed_project(workspace, index.graph))
            return render_project_document(report, workspace_diagnostics(workspace, index.graph))

    def gate(self) -> str:
        """Run the project's ruff, ty and pytest checks and return the report as JSON."""
        with tool_errors():
            workspace, index = self.open_indexed_project()
            fallbacks = {ConfigKind.RUFF: RUFF_CONFIG, ConfigKind.TY: TY_CONFIG}
            options = GateOptions(fallbacks=fallbacks)
            survey = survey_indexed_project(workspace, index.graph)
            report = run_gate_for(workspace, survey, options, environment=self.environment)
            return render_project_document(report, workspace_diagnostics(workspace, index.graph))

    def plan_review_surface(
        self,
        *,
        paths: ProjectPaths | None = None,
        diff_base: Revision | None = None,
        diff_head: Revision | None = None,
    ) -> str:
        """Plan a review surface as import-graph clusters of Python modules, as JSON.

        Give paths for a codebase surface (the whole project when left out), or diff_base
        for the modules changed between diff_base and diff_head (HEAD when left out),
        never both. Each cluster lists its modules, the tests that import them and the
        other modules that depend on them.
        """
        request = SurfaceRequest(paths=paths, diff_base=diff_base, diff_head=diff_head)
        with tool_errors():
            workspace, index = self.open_indexed_project()
            report = surface_use_case.run(workspace, index, request)
            return render_project_document(report, workspace_diagnostics(workspace, index.graph))


def build_server(
    service: DocumentationService,
    environment: Mapping[str, str] | None = None,
    *,
    uv_runner: UvRunner,
) -> MCPServer:
    documentation = DocumentationTools(service=service)
    project = ProjectTools(
        environment={} if environment is None else environment, uv_runner=uv_runner
    )
    server = MCPServer(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    server.add_tool(documentation.search_python_docs, annotations=READ_ONLY_REMOTE)
    server.add_tool(
        documentation.read_python_docs, annotations=READ_ONLY_REMOTE, structured_output=False
    )
    for tool in (
        project.collect_python_facts,
        project.map_python_calls,
        project.check_citations,
        project.plan_review_surface,
    ):
        server.add_tool(tool, annotations=READ_ONLY_LOCAL, structured_output=False)
    server.add_tool(project.survey, annotations=READ_ONLY_LOCAL, structured_output=False)
    server.add_tool(project.gate, annotations=RUNS_PROJECT_CODE, structured_output=False)
    return server


async def serve(settings: Settings) -> None:
    async with documentation_service(settings) as service:
        await build_server(service, os.environ, uv_runner=run_uv_workspace).run_stdio_async()


def main() -> int:
    anyio.run(serve, Settings())
    return 0

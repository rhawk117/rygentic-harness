"""A documentation call made while a project tool call is held in flight."""

import threading
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import anyio
import pytest
from mcp import Client
from mcp.types import CallToolResult
from python_harness.core.tests.fixtures import stubbed_uv
from python_harness.documentation.settings import Settings
from python_harness.documentation.tests.support import DOCS_VERSION, DocsSite
from python_harness.server import ProjectTools, build_server, documentation_service
from python_harness.tools.collect_python_facts.schema import FunctionShapes
from python_harness.tools.project import ProjectPaths

PACKAGE = 'src/shop'
HOLD_SECONDS = 5


@dataclass(frozen=True, slots=True, kw_only=True)
class HeldProjectCall:
    client: Client
    started: threading.Event
    release: threading.Event


async def collect_facts_into(client: Client, finished: list[CallToolResult]) -> None:
    finished.append(await client.call_tool('collect_python_facts', {'paths': [PACKAGE]}))


@pytest.mark.anyio
class TestDocumentationCallDuringAHeldProjectCall:
    @pytest.fixture
    async def held_project_call(
        self,
        monkeypatch: pytest.MonkeyPatch,
        settings: Settings,
        docs_site: DocsSite,
        project_environment: dict[str, str],
    ) -> AsyncGenerator[HeldProjectCall]:
        original = ProjectTools.collect_python_facts
        started = threading.Event()
        release = threading.Event()

        def collect_python_facts(
            project: ProjectTools,
            *,
            paths: ProjectPaths,
            with_function_shapes: FunctionShapes = False,
        ) -> str:
            started.set()
            release.wait(HOLD_SECONDS)
            return original(project, paths=paths, with_function_shapes=with_function_shapes)

        monkeypatch.setattr(ProjectTools, 'collect_python_facts', collect_python_facts)
        async with (
            documentation_service(settings, docs_site.transport()) as service,
            Client(build_server(service, project_environment, uv_runner=stubbed_uv)) as client,
        ):
            try:
                yield HeldProjectCall(client=client, started=started, release=release)
            finally:
                release.set()

    @pytest.mark.usefixtures('shop')
    async def test_search_answers_while_collect_python_facts_is_in_flight(
        self, held_project_call: HeldProjectCall
    ) -> None:
        finished: list[CallToolResult] = []
        async with anyio.create_task_group() as calls:
            calls.start_soon(collect_facts_into, held_project_call.client, finished)
            with anyio.fail_after(HOLD_SECONDS):
                await anyio.to_thread.run_sync(held_project_call.started.wait)
            search = await held_project_call.client.call_tool(
                'search_python_docs', {'version': DOCS_VERSION, 'query': 'path join'}
            )
            assert (search.is_error, finished) == (False, [])
            held_project_call.release.set()

        assert [held.is_error for held in finished] == [False]

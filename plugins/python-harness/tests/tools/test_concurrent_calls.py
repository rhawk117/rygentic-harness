"""A documentation call made while a project tool call is held in flight on a pipe."""

import os
from pathlib import Path
from typing import BinaryIO

import anyio
import pytest
from mcp import Client
from mcp.types import CallToolResult
from python_harness.core.workspace import Workspace
from python_harness.documentation.tests.support import DOCS_VERSION

PACKAGE = 'src/shop'


def open_for_writing(pipe: Path) -> BinaryIO:
    return pipe.open('wb')


async def collect_facts_into(client: Client, finished: list[CallToolResult]) -> None:
    finished.append(await client.call_tool('collect_python_facts', {'paths': [PACKAGE]}))


@pytest.mark.anyio
class TestDocumentationCallDuringAHeldProjectCall:
    @pytest.fixture
    def pipe(self, shop: Workspace) -> Path:
        path = shop.root.joinpath(PACKAGE, 'held.py')
        assert hasattr(os, 'mkfifo')
        os.mkfifo(path)
        return path

    async def test_search_answers_while_collect_python_facts_waits_on_a_pipe(
        self, project_client: Client, pipe: Path
    ) -> None:
        finished: list[CallToolResult] = []
        async with anyio.create_task_group() as calls:
            calls.start_soon(collect_facts_into, project_client, finished)
            with await anyio.to_thread.run_sync(open_for_writing, pipe) as held_open:
                search = await project_client.call_tool(
                    'search_python_docs', {'version': DOCS_VERSION, 'query': 'path join'}
                )
                assert (search.is_error, finished) == (False, [])
                held_open.write(b'held = 1\n')
            with await anyio.to_thread.run_sync(open_for_writing, pipe) as workspace_scan_open:
                workspace_scan_open.write(b'held = 1\n')

        assert [held.is_error for held in finished] == [False]

"""Shared assertions for project-tool tests."""

from collections.abc import Callable

import pytest
from mcp.types import CallToolResult
from python_harness.core.tests.support import JsonDocument
from python_harness.tools.tests.support import document_of


@pytest.fixture
def project_report_of() -> Callable[[CallToolResult], JsonDocument]:
    def report_of(result: CallToolResult) -> JsonDocument:
        document = document_of(result)
        if 'result' in document:
            return document['result']
        return {key: value for key, value in document.items() if key != 'diagnostics'}

    return report_of

"""Shared project-tool fixtures, loaded as a pytest plugin by tests/conftest.py."""

from collections.abc import AsyncGenerator

import pytest
from mcp import Client

from python_harness.core.tests.fixtures import ProjectBuilder, stubbed_uv
from python_harness.core.workspace import Workspace
from python_harness.documentation.settings import Settings
from python_harness.documentation.tests.support import DocsSite
from python_harness.server import build_server, documentation_service
from python_harness.tools.project import PROJECT_ROOT_VARIABLE
from python_harness.tools.tests.support import SHOP_PROJECT


@pytest.fixture
def shop(project_builder: ProjectBuilder) -> Workspace:
    return project_builder.write(SHOP_PROJECT)


@pytest.fixture
def project_environment(project_builder: ProjectBuilder) -> dict[str, str]:
    return {PROJECT_ROOT_VARIABLE: str(project_builder.root)}


@pytest.fixture
async def project_client(
    settings: Settings, docs_site: DocsSite, project_environment: dict[str, str]
) -> AsyncGenerator[Client]:
    async with (
        documentation_service(settings, docs_site.transport()) as service,
        Client(build_server(service, project_environment, uv_runner=stubbed_uv)) as client,
    ):
        yield client

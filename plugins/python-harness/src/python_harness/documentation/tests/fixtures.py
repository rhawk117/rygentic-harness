"""Shared documentation fixtures, loaded as a pytest plugin by tests/conftest.py."""

from collections.abc import AsyncGenerator

import pytest
from mcp import Client

from python_harness.core.tests.fixtures import stubbed_uv
from python_harness.documentation.domain import PythonVersion
from python_harness.documentation.inventory import parse_inventory
from python_harness.documentation.matching import SymbolCatalog, catalog_symbols
from python_harness.documentation.settings import Settings
from python_harness.documentation.tests.support import (
    DOCS_VERSION,
    DocsSite,
    inventory_bytes,
    standard_pages,
)
from python_harness.server import build_server, documentation_service


@pytest.fixture
def anyio_backend() -> str:
    return 'asyncio'


@pytest.fixture(scope='session')
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope='session')
def docs_version() -> PythonVersion:
    return PythonVersion(text=DOCS_VERSION)


@pytest.fixture(scope='session')
def catalog(settings: Settings, docs_version: PythonVersion) -> SymbolCatalog:
    return catalog_symbols(parse_inventory(inventory_bytes(), docs_version, settings))


@pytest.fixture
def docs_site() -> DocsSite:
    return DocsSite(pages=standard_pages())


@pytest.fixture
async def docs_client(settings: Settings, docs_site: DocsSite) -> AsyncGenerator[Client]:
    async with (
        documentation_service(settings, docs_site.transport()) as service,
        Client(build_server(service, uv_runner=stubbed_uv)) as client,
    ):
        yield client

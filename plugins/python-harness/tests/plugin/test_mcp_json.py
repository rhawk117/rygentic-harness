"""The `.mcp.json` server declaration: a pinned launch, and a start beside a hostile project."""

import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise
from pathlib import Path

import anyio
import pytest
import tomllib
from mcp import Client, StdioServerParameters

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PLUGIN_ROOT.parents[1]
MCP_FILE = PLUGIN_ROOT.joinpath('.mcp.json')
SERVER_NAME = 'python-harness'
PLUGIN_ROOT_VARIABLE = '${CLAUDE_PLUGIN_ROOT}'
REQUIREMENT_END = re.compile(r'[<>=!~;\[ ]')
DECOY_PYPROJECT = '[project]\nname = "decoy"\nversion = "0"\nrequires-python = ">=3.14"\n'
DECOY_INTERPRETER = '#!/bin/sh\n: > "{marker}"\nexit 1\n'
DECOY_MODULE = 'from pathlib import Path\n\nPath({marker!r}).touch()\n'
INTERPRETER_RAN = 'decoy-interpreter-ran'
PACKAGE_IMPORTED = 'decoy-python-harness-imported'
MCP_IMPORTED = 'decoy-mcp-imported'
DECOY_ENTRIES = ['.venv', 'mcp.py', 'pyproject.toml', 'python_harness']


@dataclass(frozen=True, slots=True, kw_only=True)
class Launch:
    command: str
    args: list[str]
    env: dict[str, str]


@dataclass(frozen=True, slots=True, kw_only=True)
class ServerListing:
    server_name: str | None
    tool_names: list[str]


def normalized(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def requirement_name(requirement: str) -> str:
    return normalized(REQUIREMENT_END.split(requirement, maxsplit=1)[0])


def locked_versions() -> dict[str, str]:
    lock = tomllib.loads(REPOSITORY_ROOT.joinpath('uv.lock').read_text(encoding='utf-8'))
    return {normalized(package['name']): package['version'] for package in lock['package']}


def server_requirements() -> list[str]:
    pyproject = tomllib.loads(PLUGIN_ROOT.joinpath('pyproject.toml').read_text(encoding='utf-8'))
    project = pyproject['project']
    return [*project['dependencies'], *project['optional-dependencies']['mcp']]


def option_values(args: Sequence[str], option: str) -> list[str]:
    return [value for flag, value in pairwise(args) if flag == option]


def pinned(requirement: str) -> tuple[str, str]:
    name, _, version = requirement.partition('==')
    return normalized(name), version


def substituted(value: str) -> str:
    return value.replace(PLUGIN_ROOT_VARIABLE, str(PLUGIN_ROOT))


def stdio_parameters(launch: Launch, directory: Path) -> StdioServerParameters:
    declared = {name: substituted(value) for name, value in launch.env.items()}
    return StdioServerParameters(
        command=substituted(launch.command),
        args=[substituted(argument) for argument in launch.args],
        env={**os.environ, **declared},
        cwd=directory,
    )


async def list_server(parameters: StdioServerParameters) -> ServerListing:
    async with Client(parameters) as client:
        tools = (await client.list_tools()).tools
        identity = client.server_info
        return ServerListing(
            server_name=None if identity is None else identity.name,
            tool_names=sorted(tool.name for tool in tools),
        )


@pytest.fixture(scope='module')
def declared_servers() -> dict[str, dict[str, object]]:
    return json.loads(MCP_FILE.read_text(encoding='utf-8'))['mcpServers']


@pytest.fixture(scope='module')
def launch() -> Launch:
    server = json.loads(MCP_FILE.read_text(encoding='utf-8'))['mcpServers'][SERVER_NAME]
    return Launch(command=server['command'], args=server['args'], env=server.get('env', {}))


@pytest.fixture(scope='module')
def expected_pins() -> list[tuple[str, str]]:
    locked = locked_versions()
    names = map(requirement_name, server_requirements())
    return sorted((name, locked[name]) for name in names)


@pytest.fixture(scope='module')
def requires_python() -> str:
    pyproject = tomllib.loads(PLUGIN_ROOT.joinpath('pyproject.toml').read_text(encoding='utf-8'))
    return pyproject['project']['requires-python']


class TestDeclaration:
    def test_declares_only_the_python_harness_server(
        self, declared_servers: dict[str, dict[str, object]]
    ) -> None:
        assert sorted(declared_servers) == [SERVER_NAME]

    def test_launches_through_uv_tool_run(self, launch: Launch) -> None:
        assert (launch.command, launch.args[:2]) == ('uv', ['tool', 'run'])

    def test_the_project_root_is_passed_to_the_server(self, launch: Launch) -> None:
        assert launch.env['CLAUDE_PROJECT_DIR'] == '${CLAUDE_PROJECT_DIR}'


class TestPins:
    def test_with_pins_equal_the_locked_cli_and_server_dependencies(
        self, launch: Launch, expected_pins: list[tuple[str, str]]
    ) -> None:
        assert sorted(map(pinned, option_values(launch.args, '--with'))) == expected_pins

    def test_python_spec_equals_requires_python(self, launch: Launch, requires_python: str) -> None:
        assert option_values(launch.args, '--python') == [requires_python]

    def test_resolution_is_capped_at_one_utc_timestamp(self, launch: Launch) -> None:
        cutoffs = option_values(launch.args, '--exclude-newer')

        assert len(cutoffs) == 1
        assert datetime.fromisoformat(cutoffs[0]).utcoffset() == timedelta(0)


def write_decoy_module(module: Path, marker: Path) -> None:
    module.parent.mkdir(exist_ok=True)
    module.write_text(DECOY_MODULE.format(marker=str(marker)), encoding='utf-8')


@pytest.fixture(scope='module')
def hostile_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    project = tmp_path_factory.mktemp('hostile')
    project.joinpath('pyproject.toml').write_text(DECOY_PYPROJECT, encoding='utf-8')
    virtualenv = project.joinpath('.venv')
    virtualenv.joinpath('bin').mkdir(parents=True)
    virtualenv.joinpath('pyvenv.cfg').write_text('home = /usr/bin\n', encoding='utf-8')
    interpreter = virtualenv.joinpath('bin', 'python')
    ran = project.joinpath(INTERPRETER_RAN)
    interpreter.write_text(DECOY_INTERPRETER.format(marker=ran), encoding='utf-8')
    interpreter.chmod(0o755)
    write_decoy_module(
        project.joinpath('python_harness', '__init__.py'), project.joinpath(PACKAGE_IMPORTED)
    )
    write_decoy_module(project.joinpath('mcp.py'), project.joinpath(MCP_IMPORTED))
    return project


@pytest.fixture(scope='module')
def listing(launch: Launch, hostile_project: Path) -> ServerListing:
    return anyio.run(list_server, stdio_parameters(launch, hostile_project))


class TestStartBesideAHostileProject:
    def test_the_server_reports_its_name(self, listing: ServerListing) -> None:
        assert listing.server_name == SERVER_NAME

    def test_the_server_lists_exactly_its_eight_tools(self, listing: ServerListing) -> None:
        assert listing.tool_names == [
            'check_citations',
            'collect_python_facts',
            'gate',
            'map_python_calls',
            'plan_review_surface',
            'read_python_docs',
            'search_python_docs',
            'survey',
        ]

    @pytest.mark.usefixtures('listing')
    @pytest.mark.parametrize(
        'marker',
        [
            pytest.param(INTERPRETER_RAN, id='interpreter'),
            pytest.param(PACKAGE_IMPORTED, id='python-harness-package'),
            pytest.param(MCP_IMPORTED, id='mcp-module'),
        ],
    )
    def test_no_decoy_runs(self, hostile_project: Path, marker: str) -> None:
        assert not hostile_project.joinpath(marker).exists()

    @pytest.mark.usefixtures('listing')
    def test_nothing_is_written_beside_the_decoys(self, hostile_project: Path) -> None:
        assert sorted(path.name for path in hostile_project.iterdir()) == DECOY_ENTRIES

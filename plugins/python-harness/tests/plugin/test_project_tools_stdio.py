"""The survey and gate tools over stdio, as Claude Code reaches them through `.mcp.json`."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

import anyio
import pytest
from mcp import Client, StdioServerParameters
from python_harness.core.tests.support import JsonDocument
from python_harness.gate.domain import DEFAULT_RUFF_VERSION
from python_harness.gate.fallbacks import RUFF_CONFIG, TY_CONFIG
from python_harness.tools.tests.support import document_of

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT_VARIABLE = '${CLAUDE_PLUGIN_ROOT}'
SERVER_NAME = 'python-harness'
FIXTURE_PROJECT = {
    'pyproject.toml': '[project]\nname = "shop"\nversion = "0"\nrequires-python = ">=3.14"\n',
    'src/shop/__init__.py': 'def price(total: int) -> int:\n    return total\n',
    'tests/test_price.py': 'def test_price() -> None:\n    pass\n',
}
GATE_TOOLS = ['ruff_check', 'ruff_format', 'ty', 'pytest']


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectDocuments:
    survey: JsonDocument
    gate: JsonDocument


def server_parameters(project: Path) -> StdioServerParameters:
    declared = json.loads(PLUGIN_ROOT.joinpath('.mcp.json').read_text(encoding='utf-8'))
    server = declared['mcpServers'][SERVER_NAME]
    return StdioServerParameters(
        command=server['command'],
        args=[
            argument.replace(PLUGIN_ROOT_VARIABLE, str(PLUGIN_ROOT)) for argument in server['args']
        ],
        env={**os.environ, 'CLAUDE_PROJECT_DIR': str(project)},
        cwd=project,
    )


async def call_project_tools(parameters: StdioServerParameters) -> ProjectDocuments:
    async with Client(parameters) as client:
        survey = await client.call_tool('survey')
        gate = await client.call_tool('gate')
        return ProjectDocuments(survey=document_of(survey), gate=document_of(gate))


@pytest.fixture(scope='module')
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp('shop')
    for name, text in FIXTURE_PROJECT.items():
        root.joinpath(name).parent.mkdir(parents=True, exist_ok=True)
        root.joinpath(name).write_text(text, encoding='utf-8')
    return root


@pytest.fixture(scope='module')
def documents(project: Path) -> ProjectDocuments:
    return anyio.run(call_project_tools, server_parameters(project))


class TestSurveyOverStdio:
    def test_the_survey_names_the_project_and_its_manifest(
        self, documents: ProjectDocuments, project: Path
    ) -> None:
        survey = documents.survey

        assert (survey['root'], survey['manifest']['name']) == (str(project), 'shop')

    def test_the_survey_reports_no_ruff_or_ty_config_and_the_pytest_domain(
        self, documents: ProjectDocuments
    ) -> None:
        survey = documents.survey

        assert (survey['ruff_config'], survey['ty_config'], survey['domains']) == (
            None,
            None,
            ['pytest'],
        )

    def test_the_survey_carries_the_workspace_diagnostics(
        self, documents: ProjectDocuments
    ) -> None:
        assert documents.survey['workspace'] == {
            'source_roots': ['src'],
            'fallback_diagnostics': [],
            'unindexed_packages': [],
        }


class TestGateOverStdio:
    def test_the_gate_runs_one_result_per_check_and_none_time_out(
        self, documents: ProjectDocuments
    ) -> None:
        results = documents.gate['results']

        assert [item['command']['tool'] for item in results] == GATE_TOOLS
        assert [item['timed_out'] for item in results] == [False] * len(GATE_TOOLS)
        assert [item['outcome']['kind'] for item in results] == ['exited'] * len(GATE_TOOLS)

    def test_the_gate_reports_the_fallback_ruff_config(self, documents: ProjectDocuments) -> None:
        assert documents.gate['ruff_config_source'] == 'fallback'

    def test_the_gate_reports_the_fallback_ty_config(self, documents: ProjectDocuments) -> None:
        assert documents.gate['ty_config_source'] == 'fallback'

    def test_ruff_and_ty_commands_carry_the_packaged_fallback_config_paths(
        self, documents: ProjectDocuments
    ) -> None:
        arguments = {
            item['command']['tool']: item['command']['arguments']
            for item in documents.gate['results']
        }

        assert RUFF_CONFIG.as_posix() in arguments['ruff_check']
        assert RUFF_CONFIG.as_posix() in arguments['ruff_format']
        assert TY_CONFIG.as_posix() in arguments['ty']

    def test_both_ruff_commands_run_the_default_version_through_uvx(
        self, documents: ProjectDocuments
    ) -> None:
        commands = {item['command']['tool']: item['command'] for item in documents.gate['results']}
        pinned = f'ruff@{DEFAULT_RUFF_VERSION.text}'

        assert [
            (commands[tool]['program'], commands[tool]['arguments'][0])
            for tool in ('ruff_check', 'ruff_format')
        ] == [('uvx', pinned), ('uvx', pinned)]

    def test_ty_accepts_the_packaged_fallback_config_and_exits_zero(
        self, documents: ProjectDocuments
    ) -> None:
        outcomes = {item['command']['tool']: item['outcome'] for item in documents.gate['results']}

        assert outcomes['ty'] == {'kind': 'exited', 'exit_code': 0}

    def test_both_ruff_checks_accept_the_packaged_fallback_config_and_exit_zero(
        self, documents: ProjectDocuments
    ) -> None:
        outcomes = {item['command']['tool']: item['outcome'] for item in documents.gate['results']}

        assert (outcomes['ruff_check'], outcomes['ruff_format']) == (
            {'kind': 'exited', 'exit_code': 0},
            {'kind': 'exited', 'exit_code': 0},
        )

    def test_the_gate_carries_the_workspace_diagnostics(self, documents: ProjectDocuments) -> None:
        assert documents.gate['workspace'] == {
            'source_roots': ['src'],
            'fallback_diagnostics': [],
            'unindexed_packages': [],
        }

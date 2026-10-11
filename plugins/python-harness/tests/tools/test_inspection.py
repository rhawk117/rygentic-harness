"""The survey and gate project tools return their inspection documents over MCP."""

from collections.abc import Mapping

import pytest
from mcp import Client
from python_harness import server
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.workspace import Workspace
from python_harness.gate.domain import (
    Exited,
    GateCommand,
    GateOptions,
    GateReport,
    GateResult,
    GateTool,
    NotTracked,
    RuffConfigSource,
)
from python_harness.gate.fallbacks import RUFF_CONFIG, TY_CONFIG
from python_harness.tools.tests.support import document_of


@pytest.mark.anyio
class TestSurvey:
    @pytest.fixture
    def without_pyproject(self, project_builder: ProjectBuilder) -> None:
        project_builder.write({'shop/__init__.py': ''})

    @pytest.mark.usefixtures('without_pyproject')
    async def test_a_project_without_a_pyproject_has_a_null_manifest(
        self, project_client: Client
    ) -> None:
        result = await project_client.call_tool('survey')

        assert (result.is_error, document_of(result)['manifest']) == (False, None)


@pytest.mark.anyio
class TestGate:
    @pytest.fixture
    def gate_options(self, monkeypatch: pytest.MonkeyPatch) -> list[GateOptions]:
        given: list[GateOptions] = []

        def run_gate(
            workspace: Workspace, options: GateOptions, *, environment: Mapping[str, str]
        ) -> GateReport:
            assert workspace.root.is_dir()
            assert environment
            given.append(options)
            command = GateCommand(GateTool.RUFF_CHECK, 'ruff', ('check',))
            result = GateResult(command, Exited(1), 'error: line too long')
            return GateReport(RuffConfigSource.FALLBACK, (result,), NotTracked())

        monkeypatch.setattr(server, 'run_gate_for', run_gate)
        return given

    @pytest.mark.usefixtures('shop')
    async def test_failed_checks_are_returned_as_a_json_report(
        self, project_client: Client, gate_options: list[GateOptions]
    ) -> None:
        result = await project_client.call_tool('gate')
        document = document_of(result)

        assert (result.is_error, document['ruff_config_source'], document['passed']) == (
            False,
            'fallback',
            False,
        )
        assert document['results'][0]['output_tail'] == 'error: line too long'
        assert len(gate_options) == 1

    @pytest.mark.usefixtures('shop')
    async def test_the_gate_gets_the_packaged_fallback_configs(
        self, project_client: Client, gate_options: list[GateOptions]
    ) -> None:
        await project_client.call_tool('gate')

        (options,) = gate_options
        assert (options.fallback_ruff_config, options.fallback_ty_config) == (
            RUFF_CONFIG,
            TY_CONFIG,
        )

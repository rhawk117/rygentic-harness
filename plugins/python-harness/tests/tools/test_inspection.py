"""The survey and gate project tools return their inspection documents over MCP."""

import argparse
import json
from collections.abc import Mapping

import pytest
from mcp import Client
from python_harness.cli.inspection import add_gate_arguments
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.workspace import Workspace
from python_harness.gate import services as gate_services
from python_harness.gate.domain import (
    DEFAULT_RUFF_VERSION,
    RUFF_VERSION_OPTION,
    RUFF_VERSION_VARIABLE,
    ConfigKind,
    Exited,
    GateCommand,
    GateOptions,
    GatePlan,
    GateReport,
    GateResult,
    GateTool,
    NotTracked,
    RuffVersion,
)
from python_harness.gate.fallbacks import RUFF_CONFIG, TY_CONFIG
from python_harness.tools.envelope import (
    Detail,
    OutputOptions,
    ProjectOutput,
    output_view,
    render_budgeted_project_document,
)
from python_harness.tools.tests.support import SHOP_PROJECT, document_of, text_of


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
            workspace: Workspace,
            plan: GatePlan,
            options: GateOptions,
            *,
            environment: Mapping[str, str],
        ) -> GateReport:
            assert workspace.root.is_dir()
            assert plan.commands
            assert environment
            given.append(options)
            command = GateCommand(GateTool.RUFF_CHECK, 'ruff', ('check',))
            result = GateResult(command, Exited(1), 'error: line too long')
            sources = (plan.ruff_config_source, plan.ty_config_source)
            return GateReport(*sources, (result,), NotTracked())

        monkeypatch.setattr(gate_services, 'run_gate', run_gate)
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

    @pytest.mark.usefixtures('shop', 'gate_options')
    async def test_a_project_without_a_ty_config_gets_the_fallback_as_ty_source(
        self, project_client: Client
    ) -> None:
        result = await project_client.call_tool('gate')

        assert document_of(result)['ty_config_source'] == 'fallback'

    @pytest.mark.usefixtures('gate_options')
    async def test_a_project_with_its_own_ty_config_names_the_project_as_ty_source(
        self, project_builder: ProjectBuilder, project_client: Client
    ) -> None:
        project_builder.write({**SHOP_PROJECT, 'ty.toml': ''})

        result = await project_client.call_tool('gate')

        document = document_of(result)
        assert (document['ruff_config_source'], document['ty_config_source']) == (
            'fallback',
            'repository',
        )

    @pytest.mark.usefixtures('shop')
    async def test_the_gate_gets_the_packaged_fallback_configs(
        self, project_client: Client, gate_options: list[GateOptions]
    ) -> None:
        await project_client.call_tool('gate')

        (options,) = gate_options
        assert options.fallbacks == {ConfigKind.RUFF: RUFF_CONFIG, ConfigKind.TY: TY_CONFIG}

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        ('environment', 'expected'),
        [
            pytest.param({}, DEFAULT_RUFF_VERSION, id='unset'),
            pytest.param({RUFF_VERSION_VARIABLE: ''}, DEFAULT_RUFF_VERSION, id='empty'),
            pytest.param(
                {RUFF_VERSION_VARIABLE: '${user_config.ruff_version}'},
                DEFAULT_RUFF_VERSION,
                id='unexpanded-literal',
            ),
            pytest.param({RUFF_VERSION_VARIABLE: '0.15.2'}, RuffVersion('0.15.2'), id='override'),
        ],
    )
    async def test_both_ruff_checks_get_the_version_the_environment_names(
        self,
        project_client: Client,
        project_environment: dict[str, str],
        gate_options: list[GateOptions],
        environment: dict[str, str],
        expected: RuffVersion,
    ) -> None:
        project_environment.update(environment)

        await project_client.call_tool('gate')

        (options,) = gate_options
        tools = (options.tools[GateTool.RUFF_CHECK], options.tools[GateTool.RUFF_FORMAT])
        assert [tool.pinned_version for tool in tools] == [expected, expected]

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize('text', ['0.16 .9', '-0.16.9', 'ruff@0.16.9', '../0.16.9'])
    async def test_an_invalid_ruff_version_is_a_tool_error_that_runs_no_check(
        self,
        project_client: Client,
        project_environment: dict[str, str],
        gate_options: list[GateOptions],
        text: str,
    ) -> None:
        project_environment[RUFF_VERSION_VARIABLE] = text

        result = await project_client.call_tool('gate')

        assert (result.is_error, RUFF_VERSION_OPTION in text_of(result), gate_options) == (
            True,
            True,
            [],
        )

    @pytest.mark.usefixtures('shop')
    async def test_each_check_gets_a_600_second_timeout_like_the_cli_default(
        self, project_client: Client, gate_options: list[GateOptions]
    ) -> None:
        await project_client.call_tool('gate')
        parser = argparse.ArgumentParser()
        add_gate_arguments(parser)

        (options,) = gate_options
        assert (options.timeout_seconds, parser.parse_args([]).timeout) == (600.0, 600.0)


def keep(report: object) -> object:
    return report


class TestBudgetedProjectOutput:
    def test_shared_project_path_returns_the_response_envelope(self) -> None:
        rendered = render_budgeted_project_document(
            {'value': 'ok'},
            {'source_roots': ['src']},
            ProjectOutput(
                options=OutputOptions(detail=Detail.COUNTS, budget=256),
                summary=output_view,
                counts=keep,
            ),
        )

        document = json.loads(rendered)
        assert set(document) == {
            'detail',
            'budget',
            'tokens',
            'truncated',
            'degraded',
            'result',
            'workspace',
        }
        assert (document['detail'], document['budget'], document['result']) == (
            'counts',
            256,
            {'value': 'ok'},
        )
        assert document['tokens'] <= document['budget']

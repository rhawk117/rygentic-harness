"""The inspect commands end to end: arguments and streams in, JSON and exit code out."""

import io
import json
from types import MappingProxyType

import pytest
from python_harness.cli import main
from python_harness.cli.domain import InspectCommand, ProcessEdge
from python_harness.cli.exit_codes import ExitCode
from python_harness.cli.inspection import default_inspect_commands
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.tests.support import JsonDocument
from python_harness.core.workspace import Workspace

PROJECT = MappingProxyType(
    {
        'pyproject.toml': """
            [project]
            name = "shop"
            requires-python = ">=3.14"
            [project.scripts]
            shop = "shop.cli:main"
            [build-system]
            requires = ["uv_build"]
            build-backend = "uv_build"
        """,
        'src/shop/__init__.py': '',
        'src/shop/pricing.py': """
            def price(total: int) -> int:
                return total
        """,
        'src/shop/cli.py': """
            from shop.pricing import price


            def main() -> int:
                return price(0)
        """,
    }
)


def run_inspect(workspace: Workspace, *arguments: str) -> tuple[int, JsonDocument]:
    stdout = io.StringIO()
    edge = ProcessEdge(io.StringIO(), stdout, io.StringIO(), MappingProxyType({}))
    command = ('inspect', *arguments, '--root', str(workspace.root))
    exit_code = main(command, edge=edge)
    return exit_code, json.loads(stdout.getvalue())


def run_failing_inspect(workspace: Workspace, *arguments: str) -> tuple[int, str]:
    stderr = io.StringIO()
    edge = ProcessEdge(io.StringIO(), io.StringIO(), stderr, MappingProxyType({}))
    command = ('inspect', *arguments, '--root', str(workspace.root))
    exit_code = main(command, edge=edge)
    return exit_code, stderr.getvalue()


@pytest.fixture
def workspace(project_builder: ProjectBuilder) -> Workspace:
    return project_builder.write(PROJECT)


class TestCommandTable:
    def test_every_inspect_command_has_a_definition(self) -> None:
        assert frozenset(default_inspect_commands()) == frozenset(InspectCommand)

    def test_the_inspect_group_holds_exactly_survey_and_gate(self) -> None:
        assert sorted(default_inspect_commands()) == ['gate', 'survey']

    @pytest.mark.parametrize(
        'command',
        [
            pytest.param('surface', id='surface'),
            pytest.param('facts', id='facts'),
            pytest.param('calls', id='calls'),
            pytest.param('cite', id='cite'),
        ],
    )
    def test_a_command_moved_to_the_server_is_not_parsed(
        self, workspace: Workspace, command: str
    ) -> None:
        with pytest.raises(SystemExit) as refused:
            main(('inspect', command, '--root', str(workspace.root)))

        assert refused.value.code == ExitCode.ERROR


class TestSurvey:
    EMPTY_MANIFEST = MappingProxyType(
        {
            'name': None,
            'requires_python': None,
            'build_backend': None,
            'entry_points': [],
            'classifiers': [],
            'dependencies': [],
            'dev_dependencies': [],
            'optional_dependencies': [],
            'declared_distributions': [],
        }
    )

    @pytest.fixture
    def without_pyproject(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({'shop/__init__.py': ''})

    @pytest.fixture
    def with_empty_pyproject(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({'pyproject.toml': '', 'shop/__init__.py': ''})

    def test_survey_prints_the_projects_domains(self, workspace: Workspace) -> None:
        exit_code, document = run_inspect(workspace, 'survey')

        assert (exit_code, document['domains']) == (ExitCode.PASSED, ['cli'])

    def test_a_project_without_a_pyproject_prints_a_null_manifest(
        self, without_pyproject: Workspace
    ) -> None:
        _, document = run_inspect(without_pyproject, 'survey')

        assert (document['manifest'], document['mode']['reasons']) == (
            None,
            ['no pyproject.toml'],
        )

    def test_an_empty_pyproject_still_prints_a_manifest_object(
        self, with_empty_pyproject: Workspace
    ) -> None:
        _, document = run_inspect(with_empty_pyproject, 'survey')

        assert (document['manifest'], document['mode']['reasons']) == (
            self.EMPTY_MANIFEST,
            ['no build backend: uv application layout'],
        )


class TestGate:
    EVERY_TOOL_SKIPPED = (
        '--skip',
        'ruff_check',
        '--skip',
        'ruff_format',
        '--skip',
        'ty',
        '--skip',
        'pytest',
    )

    def test_gate_with_every_tool_skipped_reports_no_results(self, workspace: Workspace) -> None:
        exit_code, document = run_inspect(workspace, 'gate', *self.EVERY_TOOL_SKIPPED)

        assert (exit_code, document['results']) == (ExitCode.PASSED, [])

    @pytest.fixture
    def configured(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({**PROJECT, 'config/ruff.toml': 'line-length = 90\n'})

    def test_relative_fallback_ruff_config_is_found_under_the_root(
        self, configured: Workspace
    ) -> None:
        exit_code, document = run_inspect(
            configured,
            'gate',
            '--fallback-ruff-config',
            'config/ruff.toml',
            *self.EVERY_TOOL_SKIPPED,
        )

        assert (exit_code, document['ruff_config_source']) == (
            ExitCode.PASSED,
            'fallback',
        )

    def test_ty_runs_on_its_defaults_because_the_cli_passes_no_ty_fallback(
        self, workspace: Workspace
    ) -> None:
        exit_code, document = run_inspect(workspace, 'gate', *self.EVERY_TOOL_SKIPPED)

        assert (exit_code, document['ty_config_source']) == (ExitCode.PASSED, 'defaults')

    def test_a_ty_config_in_the_project_is_reported_as_the_projects(
        self, project_builder: ProjectBuilder
    ) -> None:
        workspace = project_builder.write({**PROJECT, 'ty.toml': ''})

        exit_code, document = run_inspect(workspace, 'gate', *self.EVERY_TOOL_SKIPPED)

        assert (exit_code, document['ty_config_source']) == (ExitCode.PASSED, 'repository')

    def test_missing_fallback_ruff_config_is_refused_before_any_tool_runs(
        self, workspace: Workspace
    ) -> None:
        missing = workspace.root.joinpath('absent-ruff.toml')

        exit_code, stderr = run_failing_inspect(
            workspace, 'gate', '--fallback-ruff-config', str(missing)
        )

        assert (exit_code, stderr) == (
            ExitCode.ERROR,
            f'python-harness: --fallback-ruff-config {missing} is not a file\n',
        )

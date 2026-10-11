"""Gate inputs from a survey, child environments, output tails and git status entries."""

import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest
import tomllib
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.workspace import Workspace
from python_harness.gate.domain import (
    DEFAULT_RUFF_VERSION,
    RUFF_VERSION_OPTION,
    RUFF_VERSION_VARIABLE,
    ConfigKind,
    GateInputs,
    GateOptions,
    GateTool,
    RuffVersion,
)
from python_harness.gate.errors import ECHOED_VALUE_LIMIT, InvalidRuffVersionError
from python_harness.gate.policy import plan_gate
from python_harness.gate.tests.support import argv_for
from python_harness.gate.util import (
    VIRTUALENV_SCRIPTS,
    build_child_environment,
    gate_inputs_from,
    ruff_version_from,
    take_output_tail,
    tool_invocations_from,
    untracked_paths_from_status,
)
from python_harness.survey.domain import (
    NO_MANIFEST,
    Domain,
    LayoutFacts,
    Mode,
    ModeInference,
    ProjectManifest,
    ProjectSurvey,
)
from python_harness.survey.services import survey_project


def join_search_path(*entries: str | Path) -> str:
    return os.pathsep.join(str(entry) for entry in entries)


class TestGateInputsFrom:
    MANIFEST = ProjectManifest(
        name='shop',
        requires_python='>=3.14',
        build_backend=None,
        entry_points=(),
        classifiers=(),
        dependencies=('fastapi',),
        dev_dependencies=('ruff',),
        optional_dependencies=('pytest',),
    )
    SURVEY = ProjectSurvey(
        root='/work/shop',
        manifest=MANIFEST,
        layout=LayoutFacts(
            has_py_typed=False,
            has_dunder_main=False,
            has_src_layout=True,
            has_tests_directory=True,
            has_uv_lock=True,
        ),
        mode=ModeInference(Mode.APPLICATION, ('no build backend: uv application layout',)),
        domains=(Domain.PYTEST, Domain.FASTAPI),
        ruff_config=None,
        external_packages=(),
        source_roots=('src',),
        ty_config=None,
    )
    EXTRA_ONLY_PYTEST_ARGV = (
        'uv',
        'run',
        '--isolated',
        '--frozen',
        '--with',
        'pytest',
        'pytest',
        '-q',
        '-p',
        'no:cacheprovider',
    )

    @pytest.fixture
    def inputs(self) -> GateInputs:
        return gate_inputs_from(self.SURVEY)

    def test_runtime_and_default_group_distributions_are_declared(self, inputs: GateInputs) -> None:
        assert inputs.declared_distributions == {'fastapi', 'ruff'}

    def test_layout_config_and_domains_carry_over(self, inputs: GateInputs) -> None:
        assert (inputs.has_uv_lock, inputs.project_configs, inputs.domains) == (
            True,
            frozenset(),
            {Domain.PYTEST, Domain.FASTAPI},
        )

    def test_ty_config_is_absent_when_the_survey_found_none(self, inputs: GateInputs) -> None:
        assert ConfigKind.TY not in inputs.project_configs

    def test_ty_config_carries_over_from_the_survey(self) -> None:
        inputs = gate_inputs_from(replace(self.SURVEY, ty_config='ty.toml'))

        assert ConfigKind.TY in inputs.project_configs

    def test_ruff_config_carries_over_from_the_survey(self) -> None:
        inputs = gate_inputs_from(replace(self.SURVEY, ruff_config='ruff.toml'))

        assert ConfigKind.RUFF in inputs.project_configs

    def test_source_roots_carry_over(self, inputs: GateInputs) -> None:
        assert inputs.source_roots == self.SURVEY.source_roots

    def test_without_a_manifest_nothing_is_declared(self) -> None:
        inputs = gate_inputs_from(replace(self.SURVEY, manifest=NO_MANIFEST))

        assert inputs.declared_distributions == frozenset()

    def test_pytest_declared_only_as_an_extra_joins_the_environment(
        self, inputs: GateInputs
    ) -> None:
        plan = plan_gate(inputs, Path(self.SURVEY.root))

        assert argv_for(plan, GateTool.PYTEST) == self.EXTRA_ONLY_PYTEST_ARGV


class TestSourceRootsFromTheWorkspace:
    FALLBACK_OPTIONS = GateOptions(fallbacks={ConfigKind.RUFF: Path('/plugin/assets/ruff.toml')})

    @pytest.fixture
    def workspace(
        self, project_builder: ProjectBuilder, request: pytest.FixtureRequest
    ) -> Workspace:
        return project_builder.write(request.param)

    @pytest.mark.parametrize(
        ('workspace', 'expected'),
        [
            pytest.param({'shop/__init__.py': ''}, ('.',), id='flat-layout'),
            pytest.param({'src/shop/__init__.py': ''}, ('src', '.'), id='src-layout'),
        ],
        indirect=['workspace'],
    )
    def test_fallback_ruff_config_names_the_roots_the_workspace_found(
        self, workspace: Workspace, expected: tuple[str, ...]
    ) -> None:
        inputs = gate_inputs_from(survey_project(workspace))

        plan = plan_gate(inputs, workspace.root, self.FALLBACK_OPTIONS)

        override = tomllib.loads(argv_for(plan, GateTool.RUFF_CHECK)[-1])
        assert override['src'] == [workspace.root.joinpath(name).as_posix() for name in expected]


class TestTakeOutputTail:
    @pytest.mark.parametrize(
        ('output', 'line_count', 'expected'),
        [
            pytest.param(b'a\nb\nc\n', 2, 'b\nc', id='keeps-last-lines'),
            pytest.param(b'a\n', 5, 'a', id='shorter-than-tail'),
            pytest.param(b'a\nb\n', 0, '', id='zero-lines'),
            pytest.param(b'ok \xff\n', 1, 'ok �', id='undecodable-bytes'),
        ],
    )
    def test_tail_lines(self, output: bytes, line_count: int, expected: str) -> None:
        assert take_output_tail(output, line_count) == expected


class TestBuildChildEnvironment:
    ACTIVE_VIRTUALENV = Path('/work/shop/.venv')
    ACTIVE_SCRIPTS = ACTIVE_VIRTUALENV.joinpath(VIRTUALENV_SCRIPTS)
    LAUNCHER_ENVIRONMENT = Path('/home/ryan/.cache/uv/archive-v0/pinned')
    LAUNCHER_SCRIPTS = LAUNCHER_ENVIRONMENT.joinpath(VIRTUALENV_SCRIPTS)
    SESSION_PARENT = MappingProxyType(
        {
            'PATH': join_search_path(ACTIVE_SCRIPTS, '/usr/local/bin', '/usr/bin'),
            'VIRTUAL_ENV': str(ACTIVE_VIRTUALENV),
            'UV': '/usr/local/bin/uv',
            'HOME': '/home/ryan',
        }
    )
    LAUNCHER_PARENT = MappingProxyType(
        {'PATH': join_search_path(LAUNCHER_SCRIPTS, ACTIVE_SCRIPTS, '/usr/bin')}
    )
    LAUNCHER_OPTIONS = GateOptions(launcher_environment=LAUNCHER_ENVIRONMENT)

    @pytest.mark.parametrize(
        ('parent', 'expected'),
        [
            pytest.param(
                SESSION_PARENT,
                {
                    'PATH': join_search_path('/usr/local/bin', '/usr/bin'),
                    'HOME': '/home/ryan',
                    'PYTHONDONTWRITEBYTECODE': '1',
                },
                id='active-virtualenv-scripts-leave-path-with-the-dropped-variables',
            ),
            pytest.param(
                {
                    'PATH': join_search_path('/usr/bin', f'{ACTIVE_SCRIPTS}/'),
                    'VIRTUAL_ENV': str(ACTIVE_VIRTUALENV),
                },
                {'PATH': '/usr/bin', 'PYTHONDONTWRITEBYTECODE': '1'},
                id='trailing-separator-still-matches',
            ),
            pytest.param(
                {'PATH': join_search_path(ACTIVE_SCRIPTS, '/usr/bin')},
                {
                    'PATH': join_search_path(ACTIVE_SCRIPTS, '/usr/bin'),
                    'PYTHONDONTWRITEBYTECODE': '1',
                },
                id='path-untouched-without-a-virtualenv',
            ),
            pytest.param(
                {'VIRTUAL_ENV': str(ACTIVE_VIRTUALENV)},
                {'PYTHONDONTWRITEBYTECODE': '1'},
                id='no-path-is-invented',
            ),
        ],
    )
    def test_child_environment(self, parent: Mapping[str, str], expected: dict[str, str]) -> None:
        assert build_child_environment(parent, GateOptions()) == expected

    def test_child_environment_overrides_the_parent(self) -> None:
        override = MappingProxyType({'HOME': '/home/isolated'})

        child = build_child_environment(
            self.SESSION_PARENT, GateOptions(child_environment=override)
        )

        assert child['HOME'] == override['HOME']

    def test_the_launchers_scripts_leave_path(self) -> None:
        child = build_child_environment(self.LAUNCHER_PARENT, self.LAUNCHER_OPTIONS)

        assert child['PATH'] == join_search_path(self.ACTIVE_SCRIPTS, '/usr/bin')


class TestLauncherEnvironment:
    PLUGIN_ROOT = Path(__file__).parents[2]
    LAUNCHER = PLUGIN_ROOT.joinpath('bin', 'python-harness')
    SET_BY_UV_RUN = frozenset({'UV', 'UV_RUN_RECURSION_DEPTH', 'VIRTUAL_ENV'})
    REPORT = (
        'import json, os, sys\n'
        'sys.path.insert(0, sys.argv[1])\n'
        'from python_harness.gate.domain import GateOptions\n'
        'from python_harness.gate.util import build_child_environment\n'
        'child = build_child_environment(os.environ, GateOptions())\n'
        'print(json.dumps([dict(os.environ), child]))\n'
    )

    @pytest.fixture
    def session(self) -> dict[str, str]:
        return {name: value for name, value in os.environ.items() if name not in self.SET_BY_UV_RUN}

    @pytest.fixture
    def launched(self, session: dict[str, str]) -> list[dict[str, str]]:
        shebang = self.LAUNCHER.read_text(encoding='utf-8').splitlines()[0]
        interpreter, arguments = shebang.removeprefix('#!').split(' ', 1)
        completed = subprocess.run(  # noqa: S603  the launcher's own shebang, with a fixed script.
            (interpreter, arguments, '-c', self.REPORT, str(self.PLUGIN_ROOT.joinpath('src'))),
            env=session,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def test_nothing_the_launcher_adds_reaches_the_tools(
        self, session: dict[str, str], launched: list[dict[str, str]]
    ) -> None:
        environment, child = launched

        assert environment != session
        assert child == session | dict(GateOptions().child_environment)


class TestUntrackedPathsFromStatus:
    @pytest.mark.parametrize(
        ('status', 'prefix', 'expected'),
        [
            pytest.param(
                '?? src/pkg.egg-info/PKG-INFO\0!! build/lib/pkg.py\0',
                '',
                {'src/pkg.egg-info/PKG-INFO', 'build/lib/pkg.py'},
                id='untracked-and-ignored',
            ),
            pytest.param(
                ' M src/pkg/core.py\0A  src/pkg/new.py\0?? notes.txt\0',
                '',
                {'notes.txt'},
                id='tracked-changes-are-not-created-files',
            ),
            pytest.param(
                '?? service/a b.txt\0!! service/cache/x\0',
                'service/',
                {'a b.txt', 'cache/x'},
                id='paths-relative-to-the-workspace-prefix',
            ),
            pytest.param('', '', frozenset(), id='clean-tree'),
        ],
    )
    def test_untracked_paths(self, status: str, prefix: str, expected: frozenset[str]) -> None:
        assert untracked_paths_from_status(status, prefix) == expected


class TestRuffVersionOption:
    @pytest.mark.parametrize(
        'environment',
        [
            pytest.param({}, id='unset'),
            pytest.param({RUFF_VERSION_VARIABLE: ''}, id='empty'),
            pytest.param(
                {RUFF_VERSION_VARIABLE: '${user_config.ruff_version}'}, id='unexpanded-literal'
            ),
        ],
    )
    def test_an_absent_value_is_the_default(self, environment: Mapping[str, str]) -> None:
        assert ruff_version_from(environment) == DEFAULT_RUFF_VERSION

    @pytest.mark.parametrize('text', ['0.15.2', '0.16.10', '1.0.0'])
    def test_a_version_overrides_the_default(self, text: str) -> None:
        assert ruff_version_from({RUFF_VERSION_VARIABLE: text}) == RuffVersion(text)

    @pytest.mark.parametrize(
        'text',
        [
            pytest.param('0.16 .9', id='space'),
            pytest.param(' 0.16.9', id='leading-space'),
            pytest.param('-0.16.9', id='leading-dash'),
            pytest.param('--version', id='flag'),
            pytest.param('ruff@0.16.9', id='at-sign'),
            pytest.param('0.16.9@latest', id='trailing-at-sign'),
            pytest.param('../0.16.9', id='slash'),
            pytest.param('0.16', id='two-components'),
            pytest.param('0.16.9rc1', id='pre-release'),
            pytest.param('0.16.9\n', id='trailing-newline'),
            pytest.param('latest', id='word'),
            pytest.param('$(id)', id='command-substitution'),
            pytest.param('${user_config.ruff_version', id='unterminated-literal'),
            pytest.param('١.٢.٣', id='non-ascii-digits'),
        ],
    )
    def test_any_other_value_is_refused_by_naming_the_option(self, text: str) -> None:
        with pytest.raises(InvalidRuffVersionError, match=RUFF_VERSION_OPTION):
            ruff_version_from({RUFF_VERSION_VARIABLE: text})

    def test_a_long_refused_value_is_cut_in_the_message(self) -> None:
        error = InvalidRuffVersionError(RUFF_VERSION_OPTION, RUFF_VERSION_VARIABLE, 'x' * 10_000)

        message = str(error)

        assert len(message) < 200
        assert RUFF_VERSION_OPTION in message
        assert RUFF_VERSION_VARIABLE in message
        assert 'x' * ECHOED_VALUE_LIMIT in message
        assert 'x' * (ECHOED_VALUE_LIMIT + 1) not in message
        assert f'cut to {ECHOED_VALUE_LIMIT} characters' in message
        assert error.value == 'x' * 10_000

    def test_the_environment_variable_sets_the_pin_of_both_ruff_commands(self) -> None:
        tools = tool_invocations_from({RUFF_VERSION_VARIABLE: '0.15.2'})

        assert [tools[tool].pinned_version for tool in GateTool] == [
            RuffVersion('0.15.2'),
            RuffVersion('0.15.2'),
            None,
            None,
        ]

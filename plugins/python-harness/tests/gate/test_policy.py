"""Gate planning: ruff config source, launchers, and which tools are planned."""

from dataclasses import replace
from pathlib import Path

import pytest
import tomllib
from python_harness.gate.domain import (
    GateInputs,
    GateOptions,
    GateTool,
    RuffConfigSource,
)
from python_harness.gate.policy import build_source_roots_override, plan_gate
from python_harness.gate.tests.support import argv_for, command_for
from python_harness.survey.domain import Domain

ROOT = Path('/work/shop')
INPUTS = GateInputs(
    declared_distributions=frozenset({'pytest', 'ruff'}),
    has_uv_lock=False,
    has_ruff_config=True,
    domains=frozenset({Domain.PYTEST}),
    source_roots=('src',),
)
RUFF_CHECK_ARGV = (
    'uv',
    'run',
    '--isolated',
    'ruff',
    'check',
    '--statistics',
    '--no-cache',
)


class TestRuffConfig:
    WITHOUT_RUFF_CONFIG = replace(INPUTS, has_ruff_config=False)
    FALLBACK_OPTIONS = GateOptions(fallback_ruff_config=Path('/plugin/assets/ruff.toml'))
    FALLBACK_ARGUMENTS = (
        '--config',
        '/plugin/assets/ruff.toml',
        '--config',
        'src = ["/work/shop/src", "/work/shop"]',
    )

    @pytest.mark.parametrize(
        ('inputs', 'options', 'expected'),
        [
            pytest.param(
                INPUTS,
                FALLBACK_OPTIONS,
                (RuffConfigSource.REPOSITORY, RUFF_CHECK_ARGV),
                id='repository-config-wins-over-fallback',
            ),
            pytest.param(
                WITHOUT_RUFF_CONFIG,
                FALLBACK_OPTIONS,
                (RuffConfigSource.FALLBACK, (*RUFF_CHECK_ARGV, *FALLBACK_ARGUMENTS)),
                id='fallback-with-absolute-source-roots',
            ),
            pytest.param(
                WITHOUT_RUFF_CONFIG,
                GateOptions(),
                (RuffConfigSource.DEFAULTS, RUFF_CHECK_ARGV),
                id='ruff-defaults',
            ),
        ],
    )
    def test_source_and_ruff_check_argv(
        self,
        inputs: GateInputs,
        options: GateOptions,
        expected: tuple[RuffConfigSource, tuple[str, ...]],
    ) -> None:
        plan = plan_gate(inputs, ROOT, options)

        check_argv = argv_for(plan, GateTool.RUFF_CHECK)
        assert (plan.ruff_config_source, check_argv) == expected

    @pytest.mark.parametrize(
        ('source_roots', 'expected'),
        [
            pytest.param(('src',), 'src = ["/work/shop/src", "/work/shop"]', id='src-layout'),
            pytest.param((), 'src = ["/work/shop"]', id='flat-layout'),
            pytest.param(
                ('lib', 'src'),
                'src = ["/work/shop/lib", "/work/shop/src", "/work/shop"]',
                id='every-root-the-survey-found',
            ),
        ],
    )
    def test_fallback_source_roots_are_the_surveyed_roots_and_the_root(
        self, source_roots: tuple[str, ...], expected: str
    ) -> None:
        inputs = replace(self.WITHOUT_RUFF_CONFIG, source_roots=source_roots)

        plan = plan_gate(inputs, ROOT, self.FALLBACK_OPTIONS)

        assert argv_for(plan, GateTool.RUFF_CHECK)[-1] == expected

    def test_config_flags_reach_both_ruff_commands_only(self) -> None:
        plan = plan_gate(self.WITHOUT_RUFF_CONFIG, ROOT, self.FALLBACK_OPTIONS)

        assert (argv_for(plan, GateTool.RUFF_FORMAT), argv_for(plan, GateTool.TY)) == (
            (
                'uv',
                'run',
                '--isolated',
                'ruff',
                'format',
                '--check',
                '--no-cache',
                *self.FALLBACK_ARGUMENTS,
            ),
            ('uv', 'run', '--isolated', '--with', 'ty', 'ty', 'check'),
        )


class TestTyConfig:
    WITH_TY_CONFIG = replace(INPUTS, has_ty_config=True)
    WITHOUT_TY_CONFIG = replace(INPUTS, has_ty_config=False)
    FALLBACK_OPTIONS = GateOptions(fallback_ty_config=Path('/plugin/assets/ty.toml'))
    FALLBACK_ARGUMENTS = ('--config-file', '/plugin/assets/ty.toml')
    TY_CHECK_ARGV = ('uv', 'run', '--isolated', '--with', 'ty', 'ty', 'check')

    @pytest.mark.parametrize(
        ('inputs', 'options', 'expected'),
        [
            pytest.param(
                WITH_TY_CONFIG,
                FALLBACK_OPTIONS,
                TY_CHECK_ARGV,
                id='repository-config-wins-over-fallback',
            ),
            pytest.param(
                WITHOUT_TY_CONFIG,
                FALLBACK_OPTIONS,
                (*TY_CHECK_ARGV, *FALLBACK_ARGUMENTS),
                id='fallback-config-is-explicit',
            ),
            pytest.param(
                WITHOUT_TY_CONFIG,
                GateOptions(),
                TY_CHECK_ARGV,
                id='no-fallback-config-keeps-ty-defaults',
            ),
        ],
    )
    def test_ty_config_arguments(
        self, inputs: GateInputs, options: GateOptions, expected: tuple[str, ...]
    ) -> None:
        plan = plan_gate(inputs, ROOT, options)

        assert argv_for(plan, GateTool.TY) == expected


class TestSourceRootsOverride:
    ROOTS = (Path("/home/o'brien/shop/src"), Path('/home/o\\x/shop'))

    def test_override_is_valid_toml_for_any_path(self) -> None:
        parsed = tomllib.loads(build_source_roots_override(self.ROOTS))

        assert parsed['src'] == [root.as_posix() for root in self.ROOTS]


class TestLaunchers:
    @pytest.mark.parametrize(
        ('inputs', 'tool', 'expected'),
        [
            pytest.param(
                INPUTS,
                GateTool.RUFF_CHECK,
                RUFF_CHECK_ARGV,
                id='declared-tool-runs-in-project',
            ),
            pytest.param(
                INPUTS,
                GateTool.TY,
                ('uv', 'run', '--isolated', '--with', 'ty', 'ty', 'check'),
                id='undeclared-ty-joins-the-project-environment',
            ),
            pytest.param(
                replace(INPUTS, has_uv_lock=True),
                GateTool.RUFF_CHECK,
                ('uv', 'run', '--isolated', '--frozen', *RUFF_CHECK_ARGV[3:]),
                id='lockfile-pins-the-project-environment',
            ),
            pytest.param(
                replace(INPUTS, declared_distributions=frozenset()),
                GateTool.RUFF_FORMAT,
                ('uvx', 'ruff', 'format', '--check', '--no-cache'),
                id='undeclared-ruff-runs-through-uvx',
            ),
            pytest.param(
                INPUTS,
                GateTool.PYTEST,
                ('uv', 'run', '--isolated', 'pytest', '-q', '-p', 'no:cacheprovider'),
                id='declared-pytest',
            ),
            pytest.param(
                replace(INPUTS, declared_distributions=frozenset({'ruff'})),
                GateTool.PYTEST,
                (
                    'uv',
                    'run',
                    '--isolated',
                    '--with',
                    'pytest',
                    'pytest',
                    '-q',
                    '-p',
                    'no:cacheprovider',
                ),
                id='undeclared-pytest-joins-the-project-environment',
            ),
        ],
    )
    def test_launcher_follows_declared_distributions(
        self, inputs: GateInputs, tool: GateTool, expected: tuple[str, ...]
    ) -> None:
        plan = plan_gate(inputs, ROOT)

        assert argv_for(plan, tool) == expected

    @pytest.mark.parametrize(
        ('inputs', 'expected'),
        [
            pytest.param(INPUTS, 'uv', id='project-launcher'),
            pytest.param(
                replace(INPUTS, declared_distributions=frozenset()),
                'uvx',
                id='tool-launcher',
            ),
        ],
    )
    def test_the_launcher_is_the_commands_program(self, inputs: GateInputs, expected: str) -> None:
        plan = plan_gate(inputs, ROOT)

        assert command_for(plan, GateTool.RUFF_CHECK).program == expected


class TestPlannedTools:
    @pytest.mark.parametrize(
        ('inputs', 'options', 'expected'),
        [
            pytest.param(
                INPUTS,
                GateOptions(),
                (
                    GateTool.RUFF_CHECK,
                    GateTool.RUFF_FORMAT,
                    GateTool.TY,
                    GateTool.PYTEST,
                ),
                id='every-tool',
            ),
            pytest.param(
                replace(INPUTS, domains=frozenset({Domain.FASTAPI})),
                GateOptions(),
                (GateTool.RUFF_CHECK, GateTool.RUFF_FORMAT, GateTool.TY),
                id='pytest-needs-the-pytest-domain',
            ),
            pytest.param(
                INPUTS,
                GateOptions(skipped=frozenset({GateTool.TY, GateTool.RUFF_FORMAT})),
                (GateTool.RUFF_CHECK, GateTool.PYTEST),
                id='skipped-tools-are-omitted',
            ),
        ],
    )
    def test_planned_tools(
        self, inputs: GateInputs, options: GateOptions, expected: tuple[GateTool, ...]
    ) -> None:
        plan = plan_gate(inputs, ROOT, options)

        assert tuple(command.tool for command in plan.commands) == expected

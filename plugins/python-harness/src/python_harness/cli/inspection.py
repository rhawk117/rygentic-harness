"""The `python-harness inspect` group: facts about a project as JSON, never verdicts."""

import argparse
from pathlib import Path
from types import MappingProxyType

from python_harness.cli.domain import (
    CommandDefinition,
    InspectCommand,
    InspectCommands,
    ProcessEdge,
)
from python_harness.cli.errors import FallbackRuffConfigMissingError
from python_harness.cli.exit_codes import ExitCode, exit_code_for
from python_harness.cli.util import add_command_parsers, build_root_parent
from python_harness.core.output import write_document
from python_harness.core.uv import run_uv_workspace
from python_harness.core.workspace import open_workspace
from python_harness.gate.domain import GateOptions, GateTool
from python_harness.gate.services import run_gate_for
from python_harness.survey.services import survey_document, survey_project


def run_survey(arguments: argparse.Namespace, edge: ProcessEdge) -> ExitCode:
    workspace = open_workspace(arguments.root, uv_runner=run_uv_workspace)
    write_document(survey_document(survey_project(workspace)), edge.stdout)
    return ExitCode.PASSED


def add_gate_arguments(parser: argparse.ArgumentParser) -> None:
    defaults = GateOptions()
    parser.add_argument('--fallback-ruff-config', type=Path, default=None)
    parser.add_argument('--timeout', type=float, default=defaults.timeout_seconds)
    parser.add_argument(
        '--skip', action='append', default=[], choices=tuple(GateTool), metavar='TOOL'
    )


def locate_fallback_ruff_config(given: Path | None, root: Path) -> Path | None:
    if given is None:
        return None
    located = root.joinpath(given)
    if not located.is_file():
        raise FallbackRuffConfigMissingError(located)
    return located


def gate_options_from(arguments: argparse.Namespace, root: Path) -> GateOptions:
    fallback = locate_fallback_ruff_config(arguments.fallback_ruff_config, root)
    return GateOptions(
        fallback_ruff_config=fallback,
        timeout_seconds=arguments.timeout,
        skipped=frozenset(GateTool(name) for name in arguments.skip),
    )


def run_gate_command(arguments: argparse.Namespace, edge: ProcessEdge) -> ExitCode:
    workspace = open_workspace(arguments.root, uv_runner=run_uv_workspace)
    options = gate_options_from(arguments, workspace.root)
    report = run_gate_for(workspace, options, environment=edge.environment)
    write_document(report, edge.stdout)
    return exit_code_for(passed=report.passed)


def default_inspect_commands() -> InspectCommands:
    return MappingProxyType(
        {
            InspectCommand.SURVEY: CommandDefinition('mode evidence, domains, configs', run_survey),
            InspectCommand.GATE: CommandDefinition(
                'run ruff, ty and pytest, report results',
                run_gate_command,
                add_gate_arguments,
            ),
        }
    )


def register_inspect_commands(group: argparse.ArgumentParser) -> None:
    commands = group.add_subparsers(dest='command', required=True)
    add_command_parsers(commands, default_inspect_commands(), (build_root_parent(),))

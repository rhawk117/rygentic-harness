"""Which verification commands run, how they launch and which ruff config applies."""

import json
from collections.abc import Iterable
from pathlib import Path

from python_harness.gate.domain import (
    ConfigArguments,
    ConfigKind,
    ConfigSelection,
    ConfigSource,
    GateCommand,
    GateInputs,
    GateOptions,
    GatePlan,
    GateTool,
    Launcher,
    ToolInvocation,
)


def list_ruff_source_roots(inputs: GateInputs, workspace_root: Path) -> tuple[Path, ...]:
    found = (workspace_root.joinpath(root) for root in inputs.source_roots)
    return (*found, workspace_root)


def build_source_roots_override(roots: Iterable[Path]) -> str:
    return f'src = {json.dumps([root.as_posix() for root in roots])}'


def build_fallback_arguments(
    kind: ConfigKind, fallback: Path, *, source_roots: Iterable[Path]
) -> tuple[str, ...]:
    if kind is ConfigKind.TY:
        return ('--config-file', fallback.as_posix())
    return (
        '--config',
        fallback.as_posix(),
        '--config',
        build_source_roots_override(source_roots),
    )


def select_config(
    kind: ConfigKind, inputs: GateInputs, workspace_root: Path, *, options: GateOptions
) -> ConfigSelection:
    fallback = options.fallbacks.get(kind)
    if kind in inputs.project_configs:
        return ConfigSelection(ConfigSource.REPOSITORY, ())
    if fallback is None:
        return ConfigSelection(ConfigSource.DEFAULTS, ())
    source_roots = list_ruff_source_roots(inputs, workspace_root)
    arguments = build_fallback_arguments(kind, fallback, source_roots=source_roots)
    return ConfigSelection(ConfigSource.FALLBACK, arguments)


def project_launcher(inputs: GateInputs) -> Launcher:
    if inputs.has_uv_lock:
        return Launcher('uv', ('run', '--isolated', '--frozen'))
    return Launcher('uv', ('run', '--isolated'))


def choose_launcher(invocation: ToolInvocation, inputs: GateInputs) -> Launcher:
    project = project_launcher(inputs)
    if invocation.distribution in inputs.declared_distributions:
        return project
    if invocation.runs_in_project_environment:
        joined = (*project.arguments, '--with', invocation.distribution)
        return Launcher(project.program, joined)
    return Launcher('uvx')


def build_command(
    tool: GateTool,
    inputs: GateInputs,
    configs: ConfigArguments,
    *,
    options: GateOptions,
) -> GateCommand:
    invocation = options.tools[tool]
    launcher = choose_launcher(invocation, inputs)
    config = () if invocation.config is None else configs[invocation.config]
    arguments = (*launcher.arguments, *invocation.arguments, *config)
    return GateCommand(tool, launcher.program, arguments)


def is_tool_planned(tool: GateTool, inputs: GateInputs, options: GateOptions) -> bool:
    if tool in options.skipped:
        return False
    required = options.tools[tool].required_domain
    return required is None or required in inputs.domains


def plan_gate(
    inputs: GateInputs, workspace_root: Path, options: GateOptions | None = None
) -> GatePlan:
    chosen = GateOptions() if options is None else options
    selections = {
        kind: select_config(kind, inputs, workspace_root, options=chosen) for kind in ConfigKind
    }
    configs = {kind: selection.arguments for kind, selection in selections.items()}
    planned = (tool for tool in chosen.tools if is_tool_planned(tool, inputs, chosen))
    commands = tuple(build_command(tool, inputs, configs, options=chosen) for tool in planned)
    return GatePlan(
        commands,
        selections[ConfigKind.RUFF].source,
        selections[ConfigKind.TY].source,
    )

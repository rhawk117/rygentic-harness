"""Running planned verification commands concurrently and noting the files they create."""

import asyncio
import os
import shutil
import signal
from asyncio.subprocess import Process
from collections.abc import AsyncGenerator, Iterable, Mapping
from contextlib import asynccontextmanager, suppress

from python_harness.core.errors import GitCommandError, GitUnavailableError
from python_harness.core.git import run_git
from python_harness.core.workspace import Workspace
from python_harness.gate.domain import (
    CreatedPaths,
    CreationTracking,
    Exited,
    GateCommand,
    GateOptions,
    GateOutcome,
    GatePlan,
    GateReport,
    GateResult,
    NotTracked,
    ProcessSettings,
    ResolvedCommand,
    TimedOut,
    UntrackedBaseline,
    UntrackedSnapshot,
)
from python_harness.gate.errors import LauncherUnavailableError
from python_harness.gate.policy import plan_gate
from python_harness.gate.util import (
    SEARCH_PATH,
    build_child_environment,
    gate_inputs_from,
    take_output_tail,
    untracked_paths_from_status,
)
from python_harness.survey.domain import ProjectSurvey

READ_CHUNK_BYTES = 65536
REPOSITORY_PREFIX_QUERY = ('rev-parse', '--show-prefix')
UNTRACKED_STATUS_QUERY = (
    '--no-optional-locks',
    'status',
    '--porcelain',
    '--ignored',
    '--untracked-files=all',
    '--no-renames',
    '-z',
    '--',
    '.',
)


def resolve_command(command: GateCommand, search_path: str) -> ResolvedCommand:
    executable = shutil.which(command.program, path=search_path)
    if executable is None:
        raise LauncherUnavailableError(command.program)
    return ResolvedCommand(command, executable)


def resolve_commands(
    commands: Iterable[GateCommand], environment: Mapping[str, str]
) -> tuple[ResolvedCommand, ...]:
    search_path = environment.get(SEARCH_PATH, os.defpath)
    return tuple(resolve_command(command, search_path) for command in commands)


def list_untracked_paths(workspace: Workspace, prefix: str) -> frozenset[str]:
    status = run_git(workspace, *UNTRACKED_STATUS_QUERY)
    return untracked_paths_from_status(status, prefix)


def take_untracked_snapshot(workspace: Workspace) -> UntrackedBaseline:
    try:
        output = run_git(workspace, *REPOSITORY_PREFIX_QUERY)
    except GitUnavailableError, GitCommandError:
        return NotTracked()
    prefix = output.rstrip('\n')
    return UntrackedSnapshot(prefix, list_untracked_paths(workspace, prefix))


def list_paths_created_since(workspace: Workspace, before: UntrackedBaseline) -> CreationTracking:
    if isinstance(before, NotTracked):
        return before
    after = list_untracked_paths(workspace, before.prefix)
    return CreatedPaths(tuple(sorted(after - before.paths)))


def kill_process_group(process: Process) -> None:
    with suppress(ProcessLookupError):
        if hasattr(os, 'killpg') and hasattr(signal, 'SIGKILL'):
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()


async def stop_process_group(process: Process) -> None:
    kill_process_group(process)
    await process.wait()


@asynccontextmanager
async def spawn_process_group(
    argv: tuple[str, ...], settings: ProcessSettings
) -> AsyncGenerator[Process]:
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=settings.root,
        env=settings.environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        yield process
    finally:
        await stop_process_group(process)


async def copy_stream(stream: asyncio.StreamReader, sink: bytearray) -> None:
    while chunk := await stream.read(READ_CHUNK_BYTES):
        sink.extend(chunk)


async def collect_output(process: Process, sink: bytearray) -> int:
    if process.stdout is not None:
        await copy_stream(process.stdout, sink)
    return await process.wait()


async def wait_for_outcome(
    process: Process, sink: bytearray, timeout_seconds: float
) -> GateOutcome:
    try:
        async with asyncio.timeout(timeout_seconds):
            exit_code = await collect_output(process, sink)
    except TimeoutError:
        return TimedOut()
    return Exited(exit_code)


async def run_resolved_command(resolved: ResolvedCommand, settings: ProcessSettings) -> GateResult:
    output = bytearray()
    async with spawn_process_group(resolved.argv, settings) as process:
        outcome = await wait_for_outcome(process, output, settings.timeout_seconds)
    tail = take_output_tail(output, settings.output_tail_lines)
    return GateResult(resolved.command, outcome, tail)


async def run_resolved_commands(
    resolved: tuple[ResolvedCommand, ...], settings: ProcessSettings
) -> tuple[GateResult, ...]:
    async with asyncio.TaskGroup() as group:
        tasks = tuple(group.create_task(run_resolved_command(item, settings)) for item in resolved)
    return tuple(task.result() for task in tasks)


def run_gate(
    workspace: Workspace,
    plan: GatePlan,
    options: GateOptions | None = None,
    *,
    environment: Mapping[str, str],
) -> GateReport:
    chosen = GateOptions() if options is None else options
    child_environment = build_child_environment(environment, chosen)
    resolved = resolve_commands(plan.commands, child_environment)
    settings = ProcessSettings(
        workspace.root,
        child_environment,
        chosen.timeout_seconds,
        chosen.output_tail_lines,
    )
    before = take_untracked_snapshot(workspace)
    results = asyncio.run(run_resolved_commands(resolved, settings))
    created = list_paths_created_since(workspace, before)
    return GateReport(plan.ruff_config_source, plan.ty_config_source, results, created)


def run_gate_for(
    workspace: Workspace,
    survey: ProjectSurvey,
    options: GateOptions | None = None,
    *,
    environment: Mapping[str, str],
) -> GateReport:
    inputs = gate_inputs_from(survey)
    plan = plan_gate(inputs, workspace.root, options)
    return run_gate(workspace, plan, options, environment=environment)

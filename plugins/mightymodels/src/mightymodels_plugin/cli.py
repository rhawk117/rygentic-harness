"""Command line entry point shared by the MCP server start mode, the hooks, `verify run`,
`review-signals` and `review-metrics`.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from mightymodels_plugin.commands.dispatch_hook import check_dispatch
from mightymodels_plugin.commands.hook_context import HookContext
from mightymodels_plugin.commands.session_start import export_data_directory

SERVE_COMMAND = 'serve'
SESSION_START_COMMAND = 'session-start'
DISPATCH_HOOK_COMMAND = 'dispatch-hook'
SUBAGENT_RECORD_COMMAND = 'subagent-record'
SUBAGENT_HANDBACK_COMMAND = 'subagent-handback'
COMPLETION_GATE_COMMAND = 'completion-gate'
PRE_COMPACT_COMMAND = 'pre-compact'
VERIFY_COMMAND = 'verify'
RUN_COMMAND = 'run'
REVIEW_SIGNALS_COMMAND = 'review-signals'
CODE_CHURN_REPORT = 'code-churn'
CHANGE_COUPLING_REPORT = 'change-coupling'
CODE_HOTSPOTS_REPORT = 'code-hotspots'
DEFAULT_MAX_COMMITS = 500
DEFAULT_LIMIT = 25
DEFAULT_MIN_SHARED = 3
DEFAULT_MAX_CHANGESET = 50
REVIEW_METRICS_COMMAND = 'review-metrics'
DEFAULT_MAX_LISTED = 50
DEFAULT_PACKAGE_DEPTH = 1
PHASES = ('planning', 'task', 'review', 'landing')
DEFAULT_PHASE = 'task'
HOOK_MODULES = MappingProxyType(
    {
        SUBAGENT_RECORD_COMMAND: 'mightymodels_plugin.commands.subagent_record',
        SUBAGENT_HANDBACK_COMMAND: 'mightymodels_plugin.commands.subagent_handback',
        COMPLETION_GATE_COMMAND: 'mightymodels_plugin.commands.completion_gate',
        PRE_COMPACT_COMMAND: 'mightymodels_plugin.commands.pre_compact',
    }
)


def add_verify_run(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    verify = commands.add_parser(VERIFY_COMMAND, help='run approved verification commands')
    actions = verify.add_subparsers(dest='action', required=True)
    run = actions.add_parser(RUN_COMMAND, help='run approved contract commands by id')
    run.add_argument('--slug', required=True, help='the ticket whose contract approved them')
    chosen = run.add_mutually_exclusive_group(required=True)
    chosen.add_argument('--id', action='append', help='an approved command id; repeatable')
    chosen.add_argument('--all', action='store_true', help='every approved command')
    run.add_argument('--phase', choices=PHASES, default=DEFAULT_PHASE)


def positive(text: str) -> int:
    value = int(text)
    if value < 1:
        message = 'must be at least 1'
        raise argparse.ArgumentTypeError(message)
    return value


def add_window(sub: argparse.ArgumentParser) -> None:
    sub.add_argument('--target', help='file or directory, relative to the repository')
    sub.add_argument('--since', help='git date, e.g. 2026-01-01 or "6 months ago"')
    sub.add_argument('--baseline-ref', help='only commits after this ref, up to HEAD')
    size = sub.add_mutually_exclusive_group()
    size.add_argument('--max-commits', type=positive, default=DEFAULT_MAX_COMMITS)
    size.add_argument('--all-history', action='store_true')
    sub.add_argument('--limit', type=positive, default=DEFAULT_LIMIT)


def add_review_signals(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    signals = commands.add_parser(
        REVIEW_SIGNALS_COMMAND,
        help='measure git history for a review: churn, change coupling, hotspots',
    )
    reports = signals.add_subparsers(dest='analysis', required=True)
    churn = reports.add_parser(CODE_CHURN_REPORT, help='commits and lines changed per file')
    coupling = reports.add_parser(
        CHANGE_COUPLING_REPORT, help='files that change in the same commits'
    )
    coupling.add_argument('--min-shared', type=positive, default=DEFAULT_MIN_SHARED)
    coupling.add_argument('--max-changeset', type=positive, default=DEFAULT_MAX_CHANGESET)
    hotspots = reports.add_parser(
        CODE_HOTSPOTS_REPORT, help='churn weighted by indentation complexity'
    )
    for sub in (churn, coupling, hotspots):
        add_window(sub)


def add_review_metrics(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    metrics = commands.add_parser(
        REVIEW_METRICS_COMMAND,
        help='measure code structure for a review: sizes, fan-in, fan-out, cycles',
    )
    metrics.add_argument('root', type=Path)
    metrics.add_argument('--out', type=Path, default=None)
    metrics.add_argument('--max-listed', type=int, default=DEFAULT_MAX_LISTED)
    metrics.add_argument(
        '--package-depth',
        type=int,
        default=DEFAULT_PACKAGE_DEPTH,
        help='path components per component rollup; use 2+ for single-package repos',
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='mightymodels', description='mightymodels state server and command line tools.'
    )
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser(SERVE_COMMAND, help='run the state MCP server on standard input and output')
    commands.add_parser(
        SESSION_START_COMMAND,
        help="export the plugin data directory to the session's commands; the SessionStart hook",
    )
    commands.add_parser(
        DISPATCH_HOOK_COMMAND,
        help="deny a worker's dispatch outside its allowed targets, the main thread's of an "
        "engineer or architect with no task in progress, and an intern's unless its task owns one "
        'file; the PreToolUse hook on Agent',
    )
    commands.add_parser(
        SUBAGENT_RECORD_COMMAND,
        help="leave a scout's report in the spool for the state server; the SubagentStop hook",
    )
    commands.add_parser(
        SUBAGENT_HANDBACK_COMMAND,
        help='leave the report a scout handed back in the spool; the PostToolUse hook on it',
    )
    commands.add_parser(
        COMPLETION_GATE_COMMAND,
        help="hold an implementer's stop once while its task has no DONE brief; SubagentStop",
    )
    commands.add_parser(
        PRE_COMPACT_COMMAND,
        help='write the snapshot of the ticket on the checked-out branch; the PreCompact hook',
    )
    add_verify_run(commands)
    add_review_signals(commands)
    add_review_metrics(commands)
    return parser


def session_hook_context() -> HookContext:
    return HookContext(stdin=sys.stdin, environ=os.environ, cwd=Path.cwd())


def run_hook_command(arguments: argparse.Namespace) -> int | None:
    if arguments.command == SESSION_START_COMMAND:
        return export_data_directory(os.environ)
    if arguments.command == DISPATCH_HOOK_COMMAND:
        return check_dispatch(sys.stdin, sys.stdout.buffer, session_hook_context())
    if arguments.command not in HOOK_MODULES:
        return None
    hook = import_module(HOOK_MODULES[arguments.command])
    return int(hook.run_hook(session_hook_context()))


def run_review_command(arguments: argparse.Namespace) -> int | None:
    if arguments.command == REVIEW_SIGNALS_COMMAND:
        from mightymodels_plugin.commands.review_signals import review_signals  # noqa: PLC0415 - importing commands.review_signals (core.workspace and Pydantic) took 0.13 s measured with -X importtime and every hook and `--help` must not pay it

        return review_signals(arguments)
    if arguments.command == REVIEW_METRICS_COMMAND:
        from mightymodels_plugin.commands.review_metrics import review_metrics  # noqa: PLC0415 - importing commands.review_metrics (the four review_metrics modules and logging) took 0.024 s on top of cli, the lowest of 15 runs measured with -X importtime, and every hook and `--help` must not pay it

        return review_metrics(arguments)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if (code := run_hook_command(arguments)) is not None:
        return code
    if (code := run_review_command(arguments)) is not None:
        return code
    if arguments.command == VERIFY_COMMAND:
        from mightymodels_plugin.commands.verify import verify_run  # noqa: PLC0415 - importing commands.verify (SQLAlchemy and Pydantic) took 0.37 s measured with -X importtime and `--help` must not pay it

        return verify_run(arguments)
    from mightymodels_plugin.server import serve  # noqa: PLC0415 - importing server (mcp) took 1.5 s measured with -X importtime and every hook and --help run would pay it

    serve()
    return 0

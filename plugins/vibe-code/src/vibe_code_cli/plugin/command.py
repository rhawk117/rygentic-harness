import argparse
import itertools
import sys
from pathlib import Path

import msgspec

from vibe_code_cli.builtin import Services
from vibe_code_cli.findings import (
    CannotCheckError,
    Finding,
    decode_problem,
    report,
    warning,
)
from vibe_code_cli.plugin.checks import check_plan
from vibe_code_cli.plugin.inventory import inventory
from vibe_code_cli.plugin.manifest import json_text
from vibe_code_cli.plugin.record import Plan, decode_plan, normalise, unknown_keys
from vibe_code_cli.plugin.render import RenderRefusedError, render


def register_validate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('plan', type=Path, metavar='PLAN', help='plan record JSON')
    parser.add_argument('--strict', action='store_true', help='exit 1 on warnings too')
    parser.set_defaults(handler=validate_command)


def register_render_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('plan', type=Path, metavar='PLAN', help='plan record JSON')
    parser.add_argument(
        'target',
        type=Path,
        metavar='TARGET',
        help='plugin directory',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='rewrite the plan files of an existing plugin',
    )
    parser.set_defaults(handler=render_command)


def register_inventory_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('plugin_dir', type=Path, metavar='PLUGIN_DIR')
    parser.add_argument(
        '--out',
        type=Path,
        help='write the record here, not to stdout',
    )
    parser.set_defaults(handler=inventory_command)


def build(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    validate = commands.add_parser('validate', help='check a plugin plan record')
    register_validate_args(validate)

    render_plan = commands.add_parser(
        'render',
        help='write a plugin shell from a plan record',
    )
    register_render_args(render_plan)

    inventory_plugin = commands.add_parser(
        'inventory',
        help='record an existing plugin as a plan of built components',
    )
    register_inventory_args(inventory_plugin)


def dispatch(arguments: argparse.Namespace, services: Services) -> int:
    return int(arguments.handler(arguments, services))


def validate_command(arguments: argparse.Namespace, _services: Services) -> int:
    try:
        document = read_document(arguments.plan)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2

    return report(
        str(arguments.plan),
        validate_findings(document),
        strict=arguments.strict,
    )


def render_command(arguments: argparse.Namespace, _services: Services) -> int:
    try:
        document = read_document(arguments.plan)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2

    if report(str(arguments.plan), validate_findings(document), strict=False) != 0:
        return 1

    return write_shell(normalise(decode_plan(document)), arguments)


def write_shell(plan: Plan, arguments: argparse.Namespace) -> int:
    try:
        written = render(plan, arguments.target, force=arguments.force)
    except RenderRefusedError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 1

    except OSError as problem:
        print(
            f'error: could not write under {arguments.target}: {problem}',
            file=sys.stderr,
        )
        return 2

    for relative in written:
        print(f'wrote {relative}')

    return 0


def inventory_command(arguments: argparse.Namespace, _services: Services) -> int:
    plugin_dir = arguments.plugin_dir
    if not plugin_dir.is_dir():
        print(f'error: {plugin_dir} is not a directory', file=sys.stderr)
        return 2

    try:
        text = json_text(msgspec.to_builtins(inventory(plugin_dir)))
        emit_record(text, arguments.out)
    except (msgspec.MsgspecError, OSError, UnicodeError) as problem:
        print(f'error: could not inventory {plugin_dir}: {problem}', file=sys.stderr)
        return 2

    return 0


def emit_record(text: str, out: Path | None) -> None:
    if out is None:
        sys.stdout.write(text)
        return

    out.write_text(text, encoding='utf-8')
    print(f'wrote {out}')


def read_document(path: Path) -> object:
    text = read_text(path)
    try:
        return msgspec.json.decode(text)
    except msgspec.DecodeError as problem:
        message = f'{path} is not valid JSON: {problem}'
        raise CannotCheckError(message) from problem


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as problem:
        message = f'could not read {path}: {problem}'
        raise CannotCheckError(message) from problem


def validate_findings(document: object) -> list[Finding]:
    findings = map(warning, unknown_keys(document))
    try:
        plan = decode_plan(document)
    except msgspec.ValidationError as problem:
        problems = itertools.chain(
            findings,
            decode_problem(problem, builtin_errored=False),
        )
        return list(problems)

    problems = itertools.chain(findings, check_plan(plan))
    return list(problems)

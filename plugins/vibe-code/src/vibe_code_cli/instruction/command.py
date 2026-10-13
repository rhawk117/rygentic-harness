import argparse
import sys
from pathlib import Path

from vibe_code_cli.builtin import Services
from vibe_code_cli.findings import CannotCheckError, Finding, report
from vibe_code_cli.frontmatter import parse_skill_text
from vibe_code_cli.instruction.audit import audit_files
from vibe_code_cli.instruction.files import discover, read_text
from vibe_code_cli.instruction.rule_body import check_body
from vibe_code_cli.instruction.rule_fields import check_frontmatter


def build(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    validate = commands.add_parser(
        'validate',
        help='check a .claude/rules rule file, or audit the instruction files of a project',
    )
    validate.add_argument(
        'path',
        type=Path,
        metavar='PATH',
        help='a rule .md file, or a project directory holding CLAUDE.md and .claude/rules',
    )
    validate.add_argument('--strict', action='store_true', help='exit 1 on warnings too')
    validate.set_defaults(handler=validate_command)


def dispatch(arguments: argparse.Namespace, services: Services) -> int:
    return int(arguments.handler(arguments, services))


def validate_command(arguments: argparse.Namespace, _services: Services) -> int:
    path = arguments.path
    try:
        findings = audit_project(path) if path.is_dir() else check_rule_file(path)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2
    return report(path.resolve().name, findings, strict=arguments.strict)


def check_rule_file(path: Path) -> list[Finding]:
    if not path.is_file():
        message = f'{path} is not a file or a directory'
        raise CannotCheckError(message)

    rule = parse_skill_text(read_text(path))
    return [*check_frontmatter(rule), *check_body(rule.body)]


def audit_project(root: Path) -> list[Finding]:
    files = discover(root)
    rule_findings = [
        Finding(level=finding.level, message=f'{entry.relative}: {finding.message}')
        for entry in files
        if not entry.always_on
        for finding in check_frontmatter(parse_skill_text(entry.text))
    ]
    return [*rule_findings, *audit_files(files, root)]

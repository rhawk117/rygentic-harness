import argparse
import sys
import tempfile
from pathlib import Path

from vibe_code_cli.builtin import BuiltinRunner, Services
from vibe_code_cli.findings import CannotCheckError, Finding, report
from vibe_code_cli.hook.checks import check_hooks
from vibe_code_cli.hook.file import HooksFile, load_hooks_file
from vibe_code_cli.hook.nodes import SchemaFinding, decode_hooks
from vibe_code_cli.hook.runner import (
    Expectations,
    HookTest,
    check_hook,
    parse_field_expectation,
)

DEFAULT_TEST_TIMEOUT_SECONDS = 15.0


def register_validate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "hooks_file",
        type=Path,
        metavar="HOOKS_FILE",
        help="plugin hooks/hooks.json, or a settings file with a top-level hooks key",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 on warnings too",
    )
    parser.set_defaults(handler=validate_command)


def register_test_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "script",
        type=Path,
        metavar="SCRIPT",
        help="hook script to run",
    )
    parser.add_argument(
        "payload",
        type=Path,
        metavar="PAYLOAD",
        help="JSON payload file for stdin",
    )
    parser.add_argument(
        "--expect-exit",
        type=int,
        default=0,
        help="expected exit code (default 0)",
    )
    parser.add_argument(
        "--expect-field",
        action="append",
        default=[],
        type=parse_field_expectation,
        metavar="KEY[=VALUE]",
        help="dotted key that must be in the JSON output, and optionally equal VALUE",
    )
    parser.add_argument(
        "--expect-silent",
        action="store_true",
        help="expect empty stdout",
    )
    parser.add_argument(
        "--malformed",
        action="store_true",
        help="send invalid JSON, not the payload",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TEST_TIMEOUT_SECONDS,
    )
    parser.set_defaults(handler=hook_test_command)


def build(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    validate = commands.add_parser(
        "validate",
        help="check the schema, run claude plugin validate, then the checks both miss",
    )
    register_validate_arguments(validate)

    test = commands.add_parser(
        "test",
        help="pipe a payload into a hook script and check the Claude Code output contract",
    )
    register_test_arguments(test)


def dispatch(arguments: argparse.Namespace, services: Services) -> int:
    return int(arguments.handler(arguments, services))


def validate_command(arguments: argparse.Namespace, services: Services) -> int:
    path = arguments.hooks_file
    if not path.is_file():
        print(f"error: {path} is not a file", file=sys.stderr)
        return 2

    try:
        findings = validate_findings(path, services.run_builtin)
    except CannotCheckError as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    return report(str(path), findings, strict=arguments.strict)


def validate_findings(path: Path, runner: BuiltinRunner) -> list[Finding]:
    hooks_file = load_hooks_file(path)
    decoded = decode_hooks(hooks_file.config)
    builtin_findings = run_hooks_builtin(hooks_file, runner)
    builtin_errored = any(finding.level == "error" for finding in builtin_findings)
    own_findings = check_hooks(hooks_file, decoded, builtin_errored=builtin_errored)
    return [
        *(schema_finding.finding for schema_finding in decoded.findings),
        *(
            finding
            for finding in builtin_findings
            if not reports_location(finding, decoded.findings)
        ),
        *own_findings,
    ]


def reports_location(
    finding: Finding, schema_findings: tuple[SchemaFinding, ...]
) -> bool:
    return any(f"{schema.where}: " in finding.message for schema in schema_findings)


def run_hooks_builtin(hooks_file: HooksFile, runner: BuiltinRunner) -> list[Finding]:
    hooks_text = hooks_file.hooks_text_for_builtin()
    with tempfile.TemporaryDirectory() as staging:
        root = Path(staging)
        files = {
            root.joinpath(".claude-plugin", "plugin.json"): '{"name": "staged"}',
            root.joinpath("hooks", "hooks.json"): hooks_text,
        }

        try:
            for path, text in files.items():
                path.parent.mkdir()
                path.write_text(text, encoding="utf-8")
        except OSError as problem:
            message = f"could not stage {hooks_file.path} for claude: {problem}"
            raise CannotCheckError(message) from problem

        return runner(root, include_manifest=False)


def hook_test_command(arguments: argparse.Namespace, _services: Services) -> int:
    expectations = Expectations(
        exit_code=arguments.expect_exit,
        fields=tuple(arguments.expect_field),
        silent=arguments.expect_silent,
    )

    hook_test = HookTest(
        script=arguments.script,
        payload=arguments.payload,
        expectations=expectations,
        timeout=arguments.timeout,
        malformed=arguments.malformed,
    )

    try:
        findings = check_hook(hook_test)
    except CannotCheckError as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    return report(
        f"{arguments.script.name} < {arguments.payload.name}",
        findings,
        strict=False,
    )

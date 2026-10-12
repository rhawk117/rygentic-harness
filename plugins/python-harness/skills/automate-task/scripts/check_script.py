# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Check a script produced by automate-task against the skill's structural contract.

Static checks run on the source; ruff and ty run afterwards when they are installed. Each
finding prints as one line, and the exit code says whether every required check passed.
"""

import argparse
import ast
import logging
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)

PEP723_BLOCK = re.compile(r'^# /// script$\n(?P<body>(?:^#.*$\n)*?)^# ///$', re.MULTILINE)
MAIN_GUARD = re.compile(
    r"""^if __name__ == ["']__main__["']:\s*\n\s+raise SystemExit\(main\(\)\)""", re.MULTILINE
)
CLI_MODULES = frozenset({'argparse', 'click', 'typer'})
CONCURRENCY_MODULES = frozenset({'asyncio', 'concurrent.futures', 'multiprocessing', 'threading'})
SUBPROCESS_CALLS = frozenset({'run', 'check_output', 'check_call', 'call'})


class ExitCode(IntEnum):
    OK = 0
    FAILED = 1
    UNREADABLE = 2


class Status(StrEnum):
    OK = 'PASS'
    FAIL = 'FAIL'
    WARN = 'WARN'
    SKIP = 'SKIP'


@dataclass(slots=True, kw_only=True, frozen=True)
class Finding:
    check: str
    status: Status
    detail: str

    @property
    def line(self) -> str:
        return f'{self.status} {self.check}: {self.detail}'


@dataclass(slots=True, kw_only=True, frozen=True)
class ScriptSource:
    path: Path
    text: str
    tree: ast.Module

    @property
    def imported_modules(self) -> frozenset[str]:
        return frozenset(iter_imported_modules(self.tree))

    @property
    def string_constants(self) -> frozenset[str]:
        return frozenset(
            node.value
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class CheckOptions:
    run_tools: bool = True
    tool_timeout_seconds: float = 120.0


type Check = Callable[[ScriptSource], Finding]


def iter_imported_modules(tree: ast.Module) -> Iterator[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def iter_calls(tree: ast.Module) -> Iterator[ast.Call]:
    return (node for node in ast.walk(tree) if isinstance(node, ast.Call))


def judge(check: str, *, passed: bool, detail: str) -> Finding:
    return Finding(check=check, status=Status.OK if passed else Status.FAIL, detail=detail)


def check_inline_metadata(source: ScriptSource) -> Finding:
    block = PEP723_BLOCK.search(source.text)
    has_python = bool(block) and 'requires-python' in block.group('body')
    return judge(
        'pep723',
        passed=has_python,
        detail='inline metadata with requires-python'
        if has_python
        else "add a '# /// script' block declaring requires-python and dependencies",
    )


def check_cli(source: ScriptSource) -> Finding:
    found = CLI_MODULES & source.imported_modules
    return judge(
        'cli',
        passed=bool(found),
        detail=f'uses {", ".join(sorted(found))}' if found else 'no argparse/click/typer import',
    )


def check_dry_run(source: ScriptSource) -> Finding:
    present = '--dry-run' in source.string_constants
    return judge(
        'dry-run',
        passed=present,
        detail='--dry-run flag declared' if present else 'declare a --dry-run flag',
    )


def check_logging(source: ScriptSource) -> Finding:
    calls_get_logger = any(
        isinstance(call.func, ast.Attribute) and call.func.attr == 'getLogger'
        for call in iter_calls(source.tree)
    )
    return judge(
        'logging',
        passed='logging' in source.imported_modules and calls_get_logger,
        detail='module logger via logging.getLogger'
        if calls_get_logger
        else 'create logger = logging.getLogger(__name__)',
    )


def check_main_exit_code(source: ScriptSource) -> Finding:
    main = next(
        (
            node
            for node in source.tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == 'main'
        ),
        None,
    )
    returns_int = main is not None and ast.unparse(main.returns or ast.Constant(None)) == 'int'
    guarded = bool(MAIN_GUARD.search(source.text))
    return judge(
        'main',
        passed=returns_int and guarded,
        detail='main() -> int behind raise SystemExit(main())'
        if returns_int and guarded
        else 'define main(argv) -> int and end with raise SystemExit(main())',
    )


def check_workers_flag(source: ScriptSource) -> Finding:
    concurrent = CONCURRENCY_MODULES & source.imported_modules
    if not concurrent:
        return Finding(check='workers', status=Status.SKIP, detail='script is sequential')
    present = '--workers' in source.string_constants
    return judge(
        'workers',
        passed=present,
        detail=f'--workers exposed for {", ".join(sorted(concurrent))}'
        if present
        else 'concurrent script must expose --workers with the mapped default',
    )


def is_subprocess_call(call: ast.Call) -> bool:
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in SUBPROCESS_CALLS
        and isinstance(func.value, ast.Name)
        and func.value.id == 'subprocess'
    )


def has_true_keyword(call: ast.Call, name: str) -> bool:
    return any(
        keyword.arg == name
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in call.keywords
    )


def check_no_shell(source: ScriptSource) -> Finding:
    offending = [call.lineno for call in iter_calls(source.tree) if has_true_keyword(call, 'shell')]
    return judge(
        'no-shell',
        passed=not offending,
        detail='no shell=True' if not offending else f'shell=True on lines {offending}',
    )


def check_subprocess_timeouts(source: ScriptSource) -> Finding:
    missing = [
        call.lineno
        for call in iter_calls(source.tree)
        if is_subprocess_call(call) and all(keyword.arg != 'timeout' for keyword in call.keywords)
    ]
    return judge(
        'subprocess-timeout',
        passed=not missing,
        detail='every subprocess call has a timeout'
        if not missing
        else f'add timeout= on lines {missing}',
    )


STRUCTURAL_CHECKS: tuple[Check, ...] = (
    check_inline_metadata,
    check_cli,
    check_dry_run,
    check_logging,
    check_main_exit_code,
    check_workers_flag,
    check_no_shell,
    check_subprocess_timeouts,
)


def resolve_tool(tool: str) -> list[str] | None:
    if shutil.which(tool):
        return [tool]
    if shutil.which('uvx'):
        return ['uvx', tool]
    return None


def run_tool(name: str, arguments: Sequence[str], options: CheckOptions) -> Finding:
    if (launcher := resolve_tool(name)) is None:
        return Finding(check=name, status=Status.SKIP, detail=f'{name} and uvx not installed')
    completed = subprocess.run(  # noqa: S603  fixed tool argv, no shell.
        [*launcher, *arguments],
        capture_output=True,
        text=True,
        timeout=options.tool_timeout_seconds,
        check=False,
    )
    output = (completed.stdout + completed.stderr).strip().splitlines()
    tail = ' | '.join(output[-5:]) or 'clean'
    if 'No Python files found' in tail:
        return Finding(check=name, status=Status.SKIP, detail='file excluded by project config')
    return judge(name, passed=completed.returncode == 0, detail=tail)


def run_type_check(path: Path, options: CheckOptions) -> Finding:
    finding = run_tool('ty', ['check', '--output-format', 'concise', str(path)], options)
    if finding.status is not Status.FAIL:
        return finding
    return Finding(
        check='ty',
        status=Status.WARN,
        detail=f'advisory, inline dependencies may be unresolved: {finding.detail}',
    )


def iter_tool_findings(path: Path, options: CheckOptions) -> Iterator[Finding]:
    if not options.run_tools:
        return
    yield run_tool('ruff', ['check', '--no-fix', '--output-format', 'concise', str(path)], options)
    yield run_type_check(path, options)


def load_source(path: Path) -> ScriptSource:
    text = path.read_text(encoding='utf-8')
    return ScriptSource(path=path, text=text, tree=ast.parse(text, filename=str(path)))


def try_load_source(path: Path) -> ScriptSource | OSError | SyntaxError:
    try:
        return load_source(path)
    except (OSError, SyntaxError) as error:
        return error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('script', type=Path, help='the generated script to check')
    parser.add_argument('--no-tools', action='store_true', help='skip ruff and ty')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    options = CheckOptions(run_tools=not arguments.no_tools)
    source = try_load_source(arguments.script)
    if isinstance(source, OSError | SyntaxError):
        logger.error('cannot check %s: %s', arguments.script, source)
        return ExitCode.UNREADABLE
    findings = [check(source) for check in STRUCTURAL_CHECKS]
    findings.extend(iter_tool_findings(source.path, options))
    sys.stdout.write('\n'.join(finding.line for finding in findings) + '\n')
    failed = [finding.check for finding in findings if finding.status is Status.FAIL]
    sys.stdout.write(
        f'{"FAILED: " + ", ".join(failed) if failed else "ALL REQUIRED CHECKS PASSED"}\n'
    )
    return ExitCode.FAILED if failed else ExitCode.OK


if __name__ == '__main__':
    raise SystemExit(main())

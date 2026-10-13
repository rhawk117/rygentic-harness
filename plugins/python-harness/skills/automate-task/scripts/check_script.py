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
from enum import IntEnum, StrEnum, auto
from pathlib import Path

logger = logging.getLogger(__name__)

PEP723_BLOCK = re.compile(r'^# /// script$\n(?P<body>(?:^#.*$\n)*?)^# ///$', re.MULTILINE)
MAIN_GUARD = re.compile(
    r"""^if __name__ == ["']__main__["']:\s*\n\s+raise SystemExit\(main\(\)\)""", re.MULTILINE
)
CLI_MODULES = frozenset({'argparse', 'click', 'typer'})
CONCURRENCY_MODULES = frozenset({'asyncio', 'concurrent.futures', 'multiprocessing', 'threading'})
SUBPROCESS_CALLS = frozenset(
    {'subprocess.run', 'subprocess.check_output', 'subprocess.check_call', 'subprocess.call'}
)
LOAD_ERRORS = (OSError, SyntaxError, UnicodeDecodeError)
PINNED_TOOL_VERSIONS = {'ruff': '0.16.9', 'ty': '0.0.84'}


class ExitCode(IntEnum):
    OK = 0
    FAILED = 1
    UNREADABLE = 2
    TOOL_ERROR = 3


class Status(StrEnum):
    PASS = auto()
    FAIL = auto()
    ERROR = auto()
    WARN = auto()
    SKIP = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class Finding:
    check: str
    status: Status
    detail: str

    @property
    def line(self) -> str:
        return f'{self.status.upper()} {self.check}: {self.detail}'


@dataclass(slots=True, kw_only=True, frozen=True)
class ScriptSource:
    path: Path
    text: str
    tree: ast.Module

    @property
    def imported_modules(self) -> frozenset[str]:
        return frozenset(iter_imported_modules(self.tree))

    @property
    def import_aliases(self) -> dict[str, str]:
        return dict(
            binding for node in ast.walk(self.tree) for binding in iter_import_bindings(node)
        )

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


def iter_import_targets(node: ast.AST) -> Iterator[str]:
    if isinstance(node, ast.Import):
        yield from (alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        yield node.module
        yield from (f'{node.module}.{alias.name}' for alias in node.names)


def iter_dotted_prefixes(name: str) -> Iterator[str]:
    parts = name.split('.')
    return ('.'.join(parts[:end]) for end in range(1, len(parts) + 1))


def iter_imported_modules(tree: ast.Module) -> Iterator[str]:
    for node in ast.walk(tree):
        for target in iter_import_targets(node):
            yield from iter_dotted_prefixes(target)


def iter_import_bindings(node: ast.AST) -> Iterator[tuple[str, str]]:
    if isinstance(node, ast.Import):
        for alias in node.names:
            top = alias.name.partition('.')[0]
            yield (alias.asname, alias.name) if alias.asname else (top, top)
    elif isinstance(node, ast.ImportFrom) and node.module:
        for alias in node.names:
            yield alias.asname or alias.name, f'{node.module}.{alias.name}'


def iter_calls(tree: ast.Module) -> Iterator[ast.Call]:
    return (node for node in ast.walk(tree) if isinstance(node, ast.Call))


def dotted_name(node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return '.'.join([node.id, *reversed(parts)])


def resolve_callee(call: ast.Call, aliases: dict[str, str]) -> str:
    name = dotted_name(call.func)
    if name is None:
        return ''
    head, _, rest = name.partition('.')
    resolved = aliases.get(head, head)
    return f'{resolved}.{rest}' if rest else resolved


def iter_resolved_calls(source: ScriptSource) -> Iterator[tuple[ast.Call, str]]:
    aliases = source.import_aliases
    return ((call, resolve_callee(call, aliases)) for call in iter_calls(source.tree))


def judge(check: str, *, ok: bool, ok_detail: str, fail_detail: str) -> Finding:
    return Finding(
        check=check,
        status=Status.PASS if ok else Status.FAIL,
        detail=ok_detail if ok else fail_detail,
    )


def check_inline_metadata(source: ScriptSource) -> Finding:
    block = PEP723_BLOCK.search(source.text)
    return judge(
        'pep723',
        ok=bool(block) and 'requires-python' in block.group('body'),
        ok_detail='inline metadata with requires-python',
        fail_detail="add a '# /// script' block declaring requires-python and dependencies",
    )


def check_cli(source: ScriptSource) -> Finding:
    found = CLI_MODULES & source.imported_modules
    return judge(
        'cli',
        ok=bool(found),
        ok_detail=f'uses {", ".join(sorted(found))}',
        fail_detail='no argparse/click/typer import',
    )


def check_dry_run(source: ScriptSource) -> Finding:
    return judge(
        'dry-run',
        ok='--dry-run' in source.string_constants,
        ok_detail='--dry-run flag declared',
        fail_detail='declare a --dry-run flag',
    )


def check_logging(source: ScriptSource) -> Finding:
    return judge(
        'logging',
        ok=any(callee == 'logging.getLogger' for _, callee in iter_resolved_calls(source)),
        ok_detail='module logger via logging.getLogger',
        fail_detail='create logger = logging.getLogger(__name__)',
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
    return judge(
        'main',
        ok=returns_int and bool(MAIN_GUARD.search(source.text)),
        ok_detail='main() -> int behind raise SystemExit(main())',
        fail_detail='define main(argv) -> int and end with raise SystemExit(main())',
    )


def check_workers_flag(source: ScriptSource) -> Finding:
    concurrent = CONCURRENCY_MODULES & source.imported_modules
    if not concurrent:
        return Finding(check='workers', status=Status.SKIP, detail='script is sequential')
    return judge(
        'workers',
        ok='--workers' in source.string_constants,
        ok_detail=f'--workers exposed for {", ".join(sorted(concurrent))}',
        fail_detail='concurrent script must expose --workers with the mapped default',
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
        ok=not offending,
        ok_detail='no shell=True',
        fail_detail=f'shell=True on lines {offending}',
    )


def check_subprocess_timeouts(source: ScriptSource) -> Finding:
    missing = [
        call.lineno
        for call, callee in iter_resolved_calls(source)
        if callee in SUBPROCESS_CALLS and all(keyword.arg != 'timeout' for keyword in call.keywords)
    ]
    return judge(
        'subprocess-timeout',
        ok=not missing,
        ok_detail='every subprocess call has a timeout',
        fail_detail=f'add timeout= on lines {missing}',
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
        return ['uvx', f'{tool}@{PINNED_TOOL_VERSIONS[tool]}']
    return None


def output_tail(completed: subprocess.CompletedProcess[str]) -> str:
    output = (completed.stdout + completed.stderr).strip().splitlines()
    return ' | '.join(output[-5:]) or 'clean'


def summarize_tool_run(name: str, completed: subprocess.CompletedProcess[str]) -> Finding:
    tail = output_tail(completed)
    if 'No Python files found' in tail:
        return Finding(check=name, status=Status.SKIP, detail='file excluded by project config')
    return judge(name, ok=completed.returncode == 0, ok_detail=tail, fail_detail=tail)


def run_process(command: Sequence[str], options: CheckOptions) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  tool and flags fixed, path resolved, no shell
        command,
        capture_output=True,
        text=True,
        timeout=options.tool_timeout_seconds,
        check=False,
    )


def fetch_failure(name: str, launcher: Sequence[str], options: CheckOptions) -> Finding | None:
    if launcher[0] != 'uvx':
        return None
    probe = run_process([*launcher, '--version'], options)
    if probe.returncode == 0:
        return None
    detail = f'uvx could not fetch {launcher[1]}: {output_tail(probe)}'
    return Finding(check=name, status=Status.ERROR, detail=detail)


def run_tool(name: str, arguments: Sequence[str], options: CheckOptions) -> Finding:
    if (launcher := resolve_tool(name)) is None:
        return Finding(check=name, status=Status.SKIP, detail=f'{name} and uvx not installed')
    try:
        if (unfetched := fetch_failure(name, launcher, options)) is not None:
            return unfetched
        completed = run_process([*launcher, *arguments], options)
    except subprocess.TimeoutExpired:
        detail = f'timed out after {options.tool_timeout_seconds:g}s'
        return Finding(check=name, status=Status.ERROR, detail=detail)
    return summarize_tool_run(name, completed)


def run_type_check(path: Path, options: CheckOptions) -> Finding:
    resolved = str(path.resolve())
    finding = run_tool('ty', ['check', '--output-format', 'concise', resolved], options)
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
    resolved = str(path.resolve())
    yield run_tool('ruff', ['check', '--no-fix', '--output-format', 'concise', resolved], options)
    yield run_type_check(path, options)


def load_source(path: Path) -> ScriptSource:
    text = path.read_text(encoding='utf-8')
    return ScriptSource(path=path, text=text, tree=ast.parse(text, filename=str(path)))


def try_load_source(path: Path) -> ScriptSource | OSError | SyntaxError | UnicodeDecodeError:
    try:
        return load_source(path)
    except LOAD_ERRORS as error:
        return error


def write_findings(findings: Sequence[Finding]) -> None:
    sys.stdout.write(''.join(f'{finding.line}\n' for finding in findings))
    sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('script', type=Path, help='the generated script to check')
    parser.add_argument('--no-tools', action='store_true', help='skip ruff and ty')
    return parser


def judge_run(findings: Sequence[Finding]) -> tuple[str, ExitCode]:
    failed = [finding.check for finding in findings if finding.status is Status.FAIL]
    if failed:
        return f'FAILED: {", ".join(failed)}', ExitCode.FAILED
    errored = [finding.check for finding in findings if finding.status is Status.ERROR]
    if errored:
        return f'TOOL ERROR: {", ".join(errored)}', ExitCode.TOOL_ERROR
    return 'ALL REQUIRED CHECKS PASSED', ExitCode.OK


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    options = CheckOptions(run_tools=not arguments.no_tools)
    source = try_load_source(arguments.script)
    if isinstance(source, LOAD_ERRORS):
        logger.error('cannot check %s: %s', arguments.script, source)
        return ExitCode.UNREADABLE
    structural = [check(source) for check in STRUCTURAL_CHECKS]
    write_findings(structural)
    tools = list(iter_tool_findings(source.path, options))
    write_findings(tools)
    verdict, exit_code = judge_run([*structural, *tools])
    sys.stdout.write(f'{verdict}\n')
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())

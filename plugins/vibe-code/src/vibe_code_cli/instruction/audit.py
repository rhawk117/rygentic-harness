import re
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from vibe_code_cli.findings import Finding, error, info, warning
from vibe_code_cli.frontmatter import parse_skill_text
from vibe_code_cli.instruction.files import InstructionFile, strip_code_fences

SKIP_BYTES = 4 * 1024 * 1024
TARGET_LINES = 200
MIN_CONFLICTING_COMMANDS = 2
GIT_TIMEOUT_SECONDS = 10


class LintTopic(StrEnum):
    INDENTATION = 'indentation'
    LINE_LENGTH = 'line length'
    NAMING_CASE = 'naming case'
    IMPORT_ORDERING = 'import ordering'
    QUOTE_STYLE = 'quote style'
    SEMICOLONS = 'semicolons'
    TRAILING_WHITESPACE = 'trailing whitespace'
    FORMATTER_SETTINGS = 'formatter settings'


def lint_leakage_patterns() -> dict[LintTopic, str]:
    return {
        LintTopic.INDENTATION: (
            r'\b(indent(ation)?|tabs?\s+(vs|versus|over)\s+spaces?|\d+[- ]space)\b'
        ),
        LintTopic.LINE_LENGTH: (
            r'\b(line[- ]length|max(imum)?\s+\d{2,3}\s+char|\d{2,3}\s+characters?\s+max)\b'
        ),
        LintTopic.NAMING_CASE: (
            r'\b(camelCase|snake_case|PascalCase|kebab-case|UPPER_CASE|UPPERCASE_SNAKE_CASE)\b'
        ),
        LintTopic.IMPORT_ORDERING: (
            r'\b(import\s+(order|ordering|sorted|sorting)|sort\s+imports|organize\s+imports)\b'
        ),
        LintTopic.QUOTE_STYLE: r'\b(single|double)\s+quotes?\b',
        LintTopic.SEMICOLONS: r'\bsemicolons?\b',
        LintTopic.TRAILING_WHITESPACE: r'\btrailing\s+(whitespace|commas?)\b',
        LintTopic.FORMATTER_SETTINGS: (
            r'\b(prettier|black|gofmt|rustfmt|biome)\s+(config|settings|rules)\b'
        ),
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class LintLeakagePatterns:
    by_topic: dict[LintTopic, str] = field(default_factory=lint_leakage_patterns)


REFERENCE_CUES = (
    'because',
    'contains',
    'describes',
    'explains',
    'covers',
    'lists',
    'defines',
    'when',
    'why',
    'read it',
    'use it',
    'details on',
    'documents',
    'spec for',
)
COMMAND_VERBS = ('test', 'build', 'lint', 'install', 'typecheck', 'format', 'dev', 'start')
CLAUDE_MD_NAMES = ('CLAUDE.md', '.claude/CLAUDE.md', 'CLAUDE.local.md')

PATH_TOKEN = re.compile(r'`([^`\s]*[/\\][^`\s]*\.[A-Za-z0-9]{1,6})`|\]\((\.{0,2}/?[^)\s]+\.md)\)')
BACKTICK_COMMAND = re.compile(r'`([a-z][a-z0-9_.-]*(?:\s+[^`]{0,60})?)`')
IMPORT_TOKEN = re.compile(r'(?<![\w`])@([\w./~-]+)')


def audit_files(files: list[InstructionFile], root: Path) -> list[Finding]:
    always_on = [entry for entry in files if entry.always_on]
    return [
        *check_size(always_on),
        *check_lint_leakage(files),
        *check_blind_references(files),
        *check_command_conflicts(always_on),
        *check_rules_without_paths(files),
        *check_imports(always_on),
        *check_agents_import(files),
        *check_single_commit(always_on, root),
    ]


def check_size(always_on: list[InstructionFile]) -> list[Finding]:
    findings: list[Finding] = []
    for entry in always_on:
        count = len(entry.lines)
        if entry.size > SKIP_BYTES:
            findings.append(
                error(f'{entry.relative}: over 4 MiB, so Claude Code skips the file entirely')
            )
            continue

        if count >= TARGET_LINES:
            findings.append(
                warning(
                    f'{entry.relative}: {count} lines, at or over the {TARGET_LINES}-line target; '
                    'move what matters for only part of the codebase into path-scoped rules'
                )
            )

    return findings


def check_lint_leakage(files: list[InstructionFile]) -> list[Finding]:
    findings: list[Finding] = []
    for entry in files:
        for number, line in strip_code_fences(entry.lines):
            label = leaked_lint_label(line)
            if label is not None:
                findings.append(
                    warning(
                        f'{entry.relative}:{number}: mentions {label}, '
                        'which a formatter or linter enforces deterministically'
                    )
                )
    return findings


def leaked_lint_label(line: str) -> str | None:
    return next(
        (
            label
            for label, pattern in LintLeakagePatterns().by_topic.items()
            if re.search(pattern, line, re.IGNORECASE)
        ),
        None,
    )


def check_blind_references(files: list[InstructionFile]) -> list[Finding]:
    findings: list[Finding] = []
    for entry in files:
        for number, line in strip_code_fences(entry.lines):
            match = PATH_TOKEN.search(line)
            if match is None or any(cue in line.lower() for cue in REFERENCE_CUES):
                continue
            findings.append(
                warning(
                    f'{entry.relative}:{number}: references `{match[1] or match[2]}` '
                    'without saying what it contains or when to read it'
                )
            )
    return findings


def check_command_conflicts(always_on: list[InstructionFile]) -> list[Finding]:
    seen: dict[str, dict[str, tuple[str, int]]] = {verb: {} for verb in COMMAND_VERBS}
    for entry in always_on:
        for verb, command, number in commands_in(entry):
            seen[verb][command] = (entry.relative, number)
    findings: list[Finding] = []
    for verb, variants in seen.items():
        if len(variants) < MIN_CONFLICTING_COMMANDS:
            continue
        rendered = ', '.join(f'`{command}`' for command in sorted(variants))
        relative, number = min(variants.values())
        findings.append(
            warning(
                f'{relative}:{number}: multiple {verb} commands across always-on files: '
                f'{rendered}; pick one or scope each'
            )
        )
    return findings


def commands_in(entry: InstructionFile) -> list[tuple[str, str, int]]:
    commands = [
        (' '.join(command.split()), number)
        for number, line in strip_code_fences(entry.lines)
        for command in BACKTICK_COMMAND.findall(line)
    ]
    return [
        (verb, command, number)
        for command, number in commands
        for verb in COMMAND_VERBS
        if re.search(rf'\b{verb}\b', command)
    ]


def check_rules_without_paths(files: list[InstructionFile]) -> list[Finding]:
    return [
        info(
            f'{entry.relative}: no paths frontmatter, so this rule loads at launch in every '
            'session, like .claude/CLAUDE.md'
        )
        for entry in files
        if not entry.always_on and not has_paths(entry.text)
    ]


def has_paths(text: str) -> bool:
    fields = parse_skill_text(text).fields
    return fields is not None and 'paths' in fields


def check_imports(always_on: list[InstructionFile]) -> list[Finding]:
    return [
        info(
            f'{entry.relative}:{number}: `@{target}` expands at launch and does not reduce '
            'context; split for organization, not for cost'
        )
        for entry in always_on
        for number, line in strip_code_fences(entry.lines)
        for target in IMPORT_TOKEN.findall(line)
    ]


def check_agents_import(files: list[InstructionFile]) -> list[Finding]:
    by_relative = {entry.relative: entry for entry in files}
    claude_files = [by_relative[name] for name in CLAUDE_MD_NAMES if name in by_relative]
    if 'AGENTS.md' not in by_relative or not claude_files:
        return []
    if any(imports_agents(entry) for entry in claude_files):
        return []
    return [
        warning(
            'AGENTS.md: a CLAUDE.md exists but does not import AGENTS.md, so Claude Code reads '
            'only the CLAUDE.md files; add @AGENTS.md to a CLAUDE.md or symlink them'
        )
    ]


def imports_agents(entry: InstructionFile) -> bool:
    targets = IMPORT_TOKEN.findall(entry.text)
    return entry.symlink or any(Path(target).name == 'AGENTS.md' for target in targets)


def check_single_commit(always_on: list[InstructionFile], root: Path) -> list[Finding]:
    counts = {entry.relative: commit_count(root, entry.relative) for entry in always_on}
    if None in counts.values():
        return []
    return [
        warning(
            f'{relative}: only one commit; generated files that are never '
            'revised measurably hurt agents'
        )
        for relative, commits in counts.items()
        if commits == 1
    ]


def commit_count(root: Path, relative: str) -> int | None:
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            ['git', 'log', '--follow', '--format=%H', '--', relative],  # noqa: S607 - git is resolved from PATH on purpose
            cwd=root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return len([line for line in completed.stdout.splitlines() if line.strip()])

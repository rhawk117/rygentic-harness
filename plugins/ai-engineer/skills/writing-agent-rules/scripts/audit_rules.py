"""Detect the agent-instruction layout of a repository and report configuration smells.

Exits non-zero when any error-severity finding is present, unless --no-fail is passed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ALWAYS_ON_WARN_LINES = 200
ALWAYS_ON_ERROR_LINES = 1000

CLAUDE_ALWAYS_ON = ('CLAUDE.md', '.claude/CLAUDE.md', 'CLAUDE.local.md')
COPILOT_ALWAYS_ON = ('.github/copilot-instructions.md',)
SHARED_ALWAYS_ON = ('AGENTS.md',)

LINT_LEAKAGE_PATTERNS = {
    'indentation': (
        r'\b(indent(ation)?|tabs?\s+(vs|versus|over)\s+spaces?|\d+[- ]space)\b'
    ),
    'line length': (
        r'\b(line[- ]length|max(imum)?\s+\d{2,3}\s+char|\d{2,3}\s+characters?\s+max)\b'
    ),
    'naming case': (
        r'\b(camelCase|snake_case|PascalCase|kebab-case|UPPER_CASE|'
        r'UPPERCASE_SNAKE_CASE)\b'
    ),
    'import ordering': (
        r'\b(import\s+(order|ordering|sorted|sorting)|sort\s+imports|'
        r'organize\s+imports)\b'
    ),
    'quote style': r'\b(single|double)\s+quotes?\b',
    'semicolons': r'\bsemicolons?\b',
    'trailing whitespace': r'\btrailing\s+(whitespace|commas?)\b',
    'formatter settings': (
        r'\b(prettier|black|gofmt|rustfmt|biome)\s+(config|settings|rules)\b'
    ),
}

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

COMMAND_VERBS = (
    'test',
    'build',
    'lint',
    'install',
    'typecheck',
    'format',
    'dev',
    'start',
)

PATH_TOKEN = re.compile(
    r'`([^`\s]*[/\\][^`\s]*\.[A-Za-z0-9]{1,6})`|\]\((\.{0,2}/?[^)\s]+\.md)\)'
)
BACKTICK_COMMAND = re.compile(r'`([a-z][a-z0-9_.-]*(?:\s+[^`]{0,60})?)`')
IMPORT_TOKEN = re.compile(r'(?<![\w`])@([\w./~-]+)')


@dataclass
class Finding:
    smell: str
    severity: str
    path: str
    line: int
    message: str


@dataclass
class InstructionFile:
    path: Path
    relative: str
    role: str
    tool: str
    text: str

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()


def strip_code_fences(lines: list[str]) -> list[tuple[int, str]]:
    result = []
    inside = False
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith('```'):
            inside = not inside
            continue
        if not inside:
            result.append((number, line))
    return result


def classify(relative: str) -> tuple[str, str] | None:
    normalized = relative.replace('\\', '/')
    if normalized in CLAUDE_ALWAYS_ON:
        return 'always_on', 'claude'
    if normalized in COPILOT_ALWAYS_ON:
        return 'always_on', 'copilot'
    if normalized in SHARED_ALWAYS_ON:
        return 'always_on', 'shared'
    if normalized.startswith('.claude/rules/') and normalized.endswith('.md'):
        return 'scoped', 'claude'
    if normalized.startswith('.github/instructions/') and normalized.endswith(
        '.instructions.md'
    ):
        return 'scoped', 'copilot'
    if normalized.endswith('/SKILL.md'):
        return 'skill', 'shared'
    return None


def discover(root: Path) -> list[InstructionFile]:
    candidates = set()
    for name in CLAUDE_ALWAYS_ON + COPILOT_ALWAYS_ON + SHARED_ALWAYS_ON:
        candidates.add(root / name)
    for pattern in (
        '.claude/rules/**/*.md',
        '.github/instructions/**/*.md',
        '.claude/skills/**/SKILL.md',
        '.github/skills/**/SKILL.md',
        '.agents/skills/**/SKILL.md',
    ):
        candidates.update(root.glob(pattern))

    files = []
    for path in sorted(candidates):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        kind = classify(relative)
        if kind is None:
            continue
        role, tool = kind
        files.append(
            InstructionFile(path, relative, role, tool, path.read_text(encoding='utf-8'))
        )
    return files


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith('---'):
        return {}
    end = text.find('\n---', 3)
    if end == -1:
        return {}
    block = text[3:end]
    fields = {}
    current = None
    for line in block.splitlines():
        if re.match(r'^\s*-\s', line) and current:
            fields[current] = fields.get(current, '') + line.strip()
            continue
        match = re.match(r'^([A-Za-z_][\w-]*):\s*(.*)$', line)
        if match:
            current = match.group(1)
            fields[current] = match.group(2).strip()
    return fields


def check_size(files: list[InstructionFile]) -> list[Finding]:
    findings = []
    for entry in files:
        if entry.role != 'always_on':
            continue
        count = len(entry.lines)
        if count >= ALWAYS_ON_ERROR_LINES:
            findings.append(
                Finding(
                    'Context Bloat',
                    'error',
                    entry.relative,
                    count,
                    f'{count} lines. Past the documented ceiling where response '
                    'quality degrades.',
                )
            )
        elif count >= ALWAYS_ON_WARN_LINES:
            findings.append(
                Finding(
                    'Context Bloat',
                    'warn',
                    entry.relative,
                    count,
                    f'{count} lines, over the {ALWAYS_ON_WARN_LINES}-line target. '
                    'Look for leaked skills and style rules before editing line by line.',
                )
            )
    return findings


def check_lint_leakage(files: list[InstructionFile]) -> list[Finding]:
    findings = []
    for entry in files:
        if entry.role == 'skill':
            continue
        for number, line in strip_code_fences(entry.lines):
            for label, pattern in LINT_LEAKAGE_PATTERNS.items():
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(
                        Finding(
                            'Lint Leakage',
                            'warn',
                            entry.relative,
                            number,
                            f'Mentions {label}, which a formatter or linter '
                            'enforces deterministically.',
                        )
                    )
                    break
    return findings


def check_blind_references(files: list[InstructionFile]) -> list[Finding]:
    findings = []
    for entry in files:
        if entry.role == 'skill':
            continue
        for number, line in strip_code_fences(entry.lines):
            match = PATH_TOKEN.search(line)
            if not match:
                continue
            referenced = match.group(1) or match.group(2)
            lowered = line.lower()
            if any(cue in lowered for cue in REFERENCE_CUES):
                continue
            findings.append(
                Finding(
                    'Blind Reference',
                    'warn',
                    entry.relative,
                    number,
                    f'References `{referenced}` without saying what it contains or '
                    'when to read it.',
                )
            )
    return findings


def check_command_conflicts(files: list[InstructionFile]) -> list[Finding]:
    seen: dict[str, dict[str, tuple[str, int]]] = {verb: {} for verb in COMMAND_VERBS}
    findings = []
    for entry in files:
        if entry.role != 'always_on':
            continue
        for number, line in strip_code_fences(entry.lines):
            for command in BACKTICK_COMMAND.findall(line):
                normalized = ' '.join(command.split())
                for verb in COMMAND_VERBS:
                    if not re.search(rf'\b{verb}\b', normalized):
                        continue
                    seen[verb][normalized] = (entry.relative, number)
    for verb, variants in seen.items():
        if len(variants) < 2:
            continue
        rendered = ', '.join(f'`{command}`' for command in sorted(variants))
        location = min(variants.values())
        findings.append(
            Finding(
                'Conflicting Instructions',
                'warn',
                location[0],
                location[1],
                f'Multiple {verb} commands across always-on files: {rendered}. '
                'Pick one or scope each.',
            )
        )
    return findings


def check_scope_frontmatter(files: list[InstructionFile]) -> list[Finding]:
    findings = []
    for entry in files:
        if entry.role != 'scoped':
            continue
        fields = parse_frontmatter(entry.text)
        if entry.tool == 'copilot':
            if not entry.relative.endswith('.instructions.md'):
                findings.append(
                    Finding(
                        'Scoping',
                        'error',
                        entry.relative,
                        1,
                        'Files under .github/instructions/ need a .instructions.md '
                        'suffix to be discovered.',
                    )
                )
            elif 'applyTo' not in fields:
                findings.append(
                    Finding(
                        'Scoping',
                        'error',
                        entry.relative,
                        1,
                        'No applyTo frontmatter, so this is not path-scoped and '
                        'may apply everywhere.',
                    )
                )
        elif 'paths' not in fields:
            findings.append(
                Finding(
                    'Scoping',
                    'info',
                    entry.relative,
                    1,
                    'No paths frontmatter, so this rule loads unconditionally in '
                    'every session.',
                )
            )
    return findings


def check_import_expectations(files: list[InstructionFile]) -> list[Finding]:
    findings = []
    for entry in files:
        if entry.role != 'always_on' or entry.tool == 'copilot':
            continue
        findings.extend(
            Finding(
                'Import Cost',
                'info',
                entry.relative,
                number,
                f'`@{target}` expands at launch and does not reduce context. '
                'Split for organization, not for cost.',
            )
            for number, line in strip_code_fences(entry.lines)
            for target in IMPORT_TOKEN.findall(line)
        )
    return findings


def check_agents_visibility(files: list[InstructionFile]) -> list[Finding]:
    by_relative = {entry.relative: entry for entry in files}
    if 'AGENTS.md' not in by_relative:
        return []
    claude_entries = [
        by_relative[name] for name in CLAUDE_ALWAYS_ON if name in by_relative
    ]
    if not claude_entries:
        return [
            Finding(
                'Invisible AGENTS.md',
                'warn',
                'AGENTS.md',
                1,
                'Claude Code does not read AGENTS.md. Add a CLAUDE.md containing '
                '@AGENTS.md, or symlink it.',
            )
        ]
    imports_agents = any(
        'AGENTS.md' in IMPORT_TOKEN.findall(entry.text) or entry.path.is_symlink()
        for entry in claude_entries
    )
    if imports_agents:
        return []
    return [
        Finding(
            'Invisible AGENTS.md',
            'warn',
            'AGENTS.md',
            1,
            'A CLAUDE.md exists but does not import AGENTS.md, so the two tools '
            'read different rules.',
        )
    ]


def check_duplication(files: list[InstructionFile]) -> list[Finding]:
    def body(entry: InstructionFile) -> set[str]:
        return {
            line.strip().lower()
            for _, line in strip_code_fences(entry.lines)
            if len(line.strip()) > 25 and not line.lstrip().startswith('#')
        }

    claude_side = [
        entry
        for entry in files
        if entry.role == 'always_on' and entry.tool in ('claude', 'shared')
    ]
    copilot_side = [
        entry for entry in files if entry.role == 'always_on' and entry.tool == 'copilot'
    ]
    findings = []
    for left in claude_side:
        for right in copilot_side:
            overlap = body(left) & body(right)
            if len(overlap) >= 3:
                findings.append(
                    Finding(
                        'Duplication',
                        'warn',
                        right.relative,
                        1,
                        f'{len(overlap)} content lines duplicated with {left.relative}. '
                        'Keep one source of truth and import or symlink the other.',
                    )
                )
    return findings


def check_fossilization(root: Path, files: list[InstructionFile]) -> list[Finding]:
    findings = []
    for entry in files:
        if entry.role != 'always_on':
            continue
        try:
            # argv is built by this function, never a shell string; git resolved via PATH.
            completed = subprocess.run(  # noqa: S603
                ['git', 'log', '--follow', '--format=%H', '--', entry.relative],  # noqa: S607
                cwd=root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            return findings
        if completed.returncode != 0:
            return findings
        commits = [line for line in completed.stdout.splitlines() if line.strip()]
        if len(commits) == 1:
            findings.append(
                Finding(
                    'Init Fossilization',
                    'warn',
                    entry.relative,
                    1,
                    'Only one commit. Generated files that are never revised '
                    'measurably hurt agents.',
                )
            )
    return findings


def describe_layout(files: list[InstructionFile]) -> dict:
    readers = {
        ('always_on', 'claude'): ['Claude Code'],
        ('always_on', 'copilot'): ['GitHub Copilot'],
        ('always_on', 'shared'): ['GitHub Copilot'],
        ('scoped', 'claude'): ['Claude Code'],
        ('scoped', 'copilot'): ['GitHub Copilot'],
        ('skill', 'shared'): ['Claude Code', 'GitHub Copilot'],
    }
    return {
        'files': [
            {
                'path': entry.relative,
                'role': entry.role,
                'lines': len(entry.lines),
                'read_by': readers.get((entry.role, entry.tool), []),
            }
            for entry in files
        ]
    }


def audit(root: Path) -> tuple[list[Finding], dict]:
    files = discover(root)
    findings = []
    findings.extend(check_size(files))
    findings.extend(check_lint_leakage(files))
    findings.extend(check_blind_references(files))
    findings.extend(check_command_conflicts(files))
    findings.extend(check_scope_frontmatter(files))
    findings.extend(check_import_expectations(files))
    findings.extend(check_agents_visibility(files))
    findings.extend(check_duplication(files))
    findings.extend(check_fossilization(root, files))
    findings.sort(key=lambda item: (item.path, item.line, item.smell))
    return findings, describe_layout(files)


def render(findings: list[Finding], layout: dict) -> str:
    lines = ['Layout', '------']
    if not layout['files']:
        lines.append('  no agent instruction files found')
    for entry in layout['files']:
        readers = ', '.join(entry['read_by']) or 'not read by either tool'
        lines.append(f'  {entry["path"]:<52} {entry["lines"]:>5} lines  [{readers}]')

    lines.extend(['', 'Findings', '--------'])
    if not findings:
        lines.append('  none')
    for item in findings:
        lines.append(
            f'  {item.severity.upper():<5} {item.path}:{item.line}  {item.smell}'
        )
        lines.append(f'        {item.message}')

    counts = {
        level: sum(1 for item in findings if item.severity == level)
        for level in ('error', 'warn', 'info')
    }
    lines.extend([
        '',
        f'{counts["error"]} errors, {counts["warn"]} warnings, {counts["info"]} info',
    ])
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('root', nargs='?', default='.', help='repository root to audit')
    parser.add_argument('--json', action='store_true', help='emit structured output')
    parser.add_argument('--no-fail', action='store_true', help='always exit zero')
    arguments = parser.parse_args(argv)

    root = Path(arguments.root).resolve()
    if not root.is_dir():
        print(f'not a directory: {root}', file=sys.stderr)
        return 2

    findings, layout = audit(root)

    if arguments.json:
        print(
            json.dumps(
                {'layout': layout, 'findings': [asdict(f) for f in findings]}, indent=2
            )
        )
    else:
        print(render(findings, layout))

    if arguments.no_fail:
        return 0
    return 1 if any(item.severity == 'error' for item in findings) else 0


if __name__ == '__main__':
    sys.exit(main())

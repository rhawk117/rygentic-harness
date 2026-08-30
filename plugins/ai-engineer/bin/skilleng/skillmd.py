"""One parser for SKILL.md, and one linter. There is no second parser.

Fixes, each pinned by a test:
  * empty `name`/`description` are errors (skill-creator prints "Skill is valid!")
  * `name` must equal the directory name (the commonest silent load failure; both
    the Agent Skills spec and GitHub's implementation require it, and skill-creator
    checks neither)
  * unknown frontmatter keys warn instead of blocking — rejecting `model:` or
    `disable-model-invocation:` makes valid skills unpackageable
  * references are resolved and checked; dangling ones are errors
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# Open spec (agentskills.io) — portable across Claude Code and Copilot.
SPEC_KEYS = {
    'name',
    'description',
    'license',
    'compatibility',
    'metadata',
    'allowed-tools',
}
# Host extensions. Present-but-unknown is a warning, never a hard failure.
HOST_KEYS = {
    'disable-model-invocation',
    'user-invocable',
    'when_to_use',
    'argument-hint',
    'arguments',
    'paths',
    'shell',
    'context',
    'agent',
    'background',
    'hooks',
    'effort',
    'model',
    'disallowed-tools',
    'target',
    'mcp-servers',
    'handoffs',
    'tools',
    'agents',
}
KNOWN_KEYS = SPEC_KEYS | HOST_KEYS

NAME_MAX, DESC_MAX, COMPAT_MAX = 64, 1024, 500
BODY_LINE_BUDGET, BODY_TOKEN_BUDGET = 500, 5000

_NAME_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
_BUNDLE_RE = re.compile(r'(?:references|scripts|assets|agents|evals)/[A-Za-z0-9_./-]+')
_FRONTMATTER_RE = re.compile(r'\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z', re.DOTALL)


@dataclass
class Finding:
    severity: str  # "error" | "warn" | "info"
    code: str
    message: str

    def __str__(self) -> str:
        return f'[{self.severity.upper():5}] {self.code}: {self.message}'


@dataclass
class Skill:
    path: Path
    frontmatter: dict
    body: str
    raw: str

    @property
    def name(self) -> str:
        return str(self.frontmatter.get('name', '') or '')

    @property
    def description(self) -> str:
        return str(self.frontmatter.get('description', '') or '')

    def est_tokens(self) -> int:
        return len(self.raw) // 4

    def body_lines(self) -> int:
        return len(self.body.splitlines())

    def referenced_files(self) -> set[str]:
        return set(_BUNDLE_RE.findall(self.body))

    def bundled_files(self) -> set[str]:
        out: set[str] = set()
        for sub in ('references', 'scripts', 'assets', 'agents'):
            d = self.path / sub
            if d.is_dir():
                out |= {
                    str(p.relative_to(self.path))
                    for p in d.rglob('*')
                    if p.is_file() and '__pycache__' not in p.parts
                }
        return out


def load(skill_dir: Path) -> Skill:
    skill_dir = Path(skill_dir).resolve()
    md = skill_dir / 'SKILL.md'
    if not md.exists():
        raise FileNotFoundError(f'no SKILL.md in {skill_dir}')
    raw = md.read_text(encoding='utf-8')
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        raise ValueError(
            f'{md}: missing or malformed YAML frontmatter (needs opening and closing ---)'
        )
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise ValueError(f'{md}: frontmatter is not valid YAML: {e}') from e
    if not isinstance(fm, dict):
        raise TypeError(f'{md}: frontmatter must be a mapping, got {type(fm).__name__}')
    return Skill(path=skill_dir, frontmatter=fm, body=m.group(2), raw=raw)


def lint(skill_dir: Path) -> list[Finding]:
    out: list[Finding] = []
    try:
        s = load(skill_dir)
    except (FileNotFoundError, ValueError) as e:
        return [Finding('error', 'parse', str(e))]

    # -- name ------------------------------------------------------------
    name = s.name.strip()
    if not name:
        out.append(
            Finding(
                'error',
                'name.empty',
                '`name` is missing or empty; a skill with no name can never be invoked',
            )
        )
    else:
        if len(name) > NAME_MAX:
            out.append(
                Finding(
                    'error', 'name.length', f'`name` is {len(name)} chars, max {NAME_MAX}'
                )
            )
        if not _NAME_RE.match(name):
            out.append(
                Finding(
                    'error',
                    'name.format',
                    '`name` must be lowercase letters/digits joined by single '
                    f'hyphens, got {name!r}',
                )
            )
        if name != s.path.name:
            out.append(
                Finding(
                    'error',
                    'name.dirmatch',
                    f'`name` is {name!r} but the directory is {s.path.name!r}. '
                    "The spec requires them to match; when they don't the skill usually "
                    'fails to load with no error at all.',
                )
            )

    # -- description ------------------------------------------------------
    desc = s.description.strip()
    if not desc:
        out.append(
            Finding(
                'error',
                'description.empty',
                '`description` is missing or empty; this is the only thing the '
                'model sees when deciding whether to invoke the skill',
            )
        )
    else:
        if len(desc) > DESC_MAX:
            out.append(
                Finding(
                    'error',
                    'description.length',
                    f'`description` is {len(desc)} chars, max {DESC_MAX} — the '
                    'tail is truncated silently',
                )
            )
        elif len(desc) > DESC_MAX * 0.9:
            out.append(
                Finding(
                    'warn',
                    'description.near_limit',
                    f'`description` is {len(desc)}/{DESC_MAX} chars; little headroom',
                )
            )
        if '<' in desc or '>' in desc:
            out.append(
                Finding(
                    'warn',
                    'description.angle_brackets',
                    'angle brackets in `description` are rejected by some validators',
                )
            )
        if not re.search(
            r'\buse (this|when|it)\b|\bwhen\b|\btrigger', desc, re.IGNORECASE
        ):
            out.append(
                Finding(
                    'info',
                    'description.no_when',
                    '`description` states what the skill does but not when to use it; '
                    "trigger accuracy usually comes from the 'when' half",
                )
            )

    # -- other frontmatter -------------------------------------------------
    compat = s.frontmatter.get('compatibility')
    if isinstance(compat, str) and len(compat) > COMPAT_MAX:
        out.append(
            Finding(
                'error',
                'compatibility.length',
                f'`compatibility` is {len(compat)} chars, max {COMPAT_MAX}',
            )
        )
    unknown = set(s.frontmatter) - KNOWN_KEYS
    if unknown:
        out.append(
            Finding(
                'warn',
                'frontmatter.unknown',
                f'unrecognised key(s): {", ".join(sorted(unknown))}. '
                'Host-specific keys are fine; this is a note, not a blocker.',
            )
        )

    # -- budgets -----------------------------------------------------------
    if s.body_lines() > BODY_LINE_BUDGET:
        out.append(
            Finding(
                'warn',
                'body.lines',
                f'SKILL.md body is {s.body_lines()} lines (budget {BODY_LINE_BUDGET}). '
                'Move phase-specific detail into references/ and load it on demand.',
            )
        )
    if s.est_tokens() > BODY_TOKEN_BUDGET:
        out.append(
            Finding(
                'warn',
                'body.tokens',
                f'~{s.est_tokens()} tokens (budget {BODY_TOKEN_BUDGET}); this is '
                'paid on every invocation',
            )
        )

    # -- reference integrity ----------------------------------------------
    referenced, bundled = s.referenced_files(), s.bundled_files()
    out.extend(
        Finding(
            'error',
            'reference.dangling',
            f'SKILL.md points at {ref!r}, which does not exist',
        )
        for ref in sorted(referenced)
        if not (s.path / ref).exists()
    )
    out.extend(
        Finding(
            'warn',
            'reference.orphan',
            f'{f!r} ships with the skill but nothing references it',
        )
        for f in sorted(bundled - referenced)
        if Path(f).name != '__init__.py'
    )

    return out


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == 'error']

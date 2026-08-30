"""Packaging, and the security report that should travel with the package.

A .skill file is a zip of instructions *and executable scripts* that someone else
installs and an agent then runs. GitHub's own documentation tells users to
pre-approve shell access only for skills whose scripts they have reviewed — so the
tool that mints the artifact should produce the thing that makes that review
possible. skill-creator checks frontmatter validity and nothing else, does not
exclude `.git`, and strips `evals/` so the recipient cannot re-verify the skill
after a model upgrade.
"""

from __future__ import annotations

import fnmatch
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from skilleng.skillmd import Finding, errors, lint, load

# Never packaged. Absence of a rule here is how a .env ends up inside a shared zip.
DENY_DIRS = {
    '.git',
    '.hg',
    '.svn',
    '__pycache__',
    'node_modules',
    '.venv',
    'venv',
    '.mypy_cache',
    '.pytest_cache',
    '.idea',
    '.vscode',
    '.tox',
}
DENY_GLOBS = [
    '*.pyc',
    '*.pyo',
    '.DS_Store',
    '*.log',
    '*.sqlite',
    '*.db',
    '.env',
    '.env.*',
    '*.pem',
    '*.key',
    '*.p12',
    '*.pfx',
    '*.keystore',
    'id_rsa*',
    'id_ed25519*',
    '.netrc',
    '.npmrc',
    '.pypirc',
    'credentials',
    'credentials.json',
    '*.tfstate',
    '*.tfstate.backup',
]

SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ('AWS access key id', re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b')),
    ('GitHub token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}\b')),
    ('Slack token', re.compile(r'\bxox[abprs]-[A-Za-z0-9-]{10,}\b')),
    ('Google API key', re.compile(r'\bAIza[0-9A-Za-z_\-]{35}\b')),
    ('Anthropic key', re.compile(r'\bsk-ant-[A-Za-z0-9_\-]{20,}\b')),
    ('OpenAI key', re.compile(r'\bsk-[A-Za-z0-9]{32,}\b')),
    (
        'private key block',
        re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----'),
    ),
    (
        'bearer token',
        re.compile(r"(?i)\bauthorization\s*[:=]\s*['\"]?bearer\s+[A-Za-z0-9._\-]{20,}"),
    ),
    (
        'assigned secret',
        re.compile(
            r'(?i)\b(?:api[_-]?key|secret|passwd|password|token)\b\s*[:=]\s*'
            r"['\"][A-Za-z0-9/_+\-]{16,}['\"]"
        ),
    ),
]

# Signals that a bundled script does something the installer should know about.
EXEC_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        'runs shell commands',
        re.compile(
            r'\b(?:subprocess\.|os\.system|os\.popen|child_process|execSync|`[^`]*`)'
        ),
    ),
    (
        'makes network requests',
        re.compile(r'\b(?:requests\.|urllib|httpx|aiohttp|fetch\(|curl\s|wget\s|nc\s)'),
    ),
    (
        'writes outside the workspace',
        re.compile(r"(?:open\(\s*['\"]/(?!tmp)|>\s*/(?!tmp)|shutil\.(?:copy|move)\()"),
    ),
    (
        'deletes files',
        re.compile(r'\b(?:shutil\.rmtree|os\.remove|os\.unlink|rm\s+-[rf])'),
    ),
    (
        'reads environment/credentials',
        re.compile(r'(?:os\.environ|getenv|process\.env|~/\.(?:aws|ssh|netrc))'),
    ),
    (
        'evaluates dynamic code',
        re.compile(r'\b(?:eval\(|exec\(|pickle\.loads|yaml\.load\s*\((?![^)]*Safe))'),
    ),
]

URL_RE = re.compile(r"https?://[A-Za-z0-9.\-]+(?:/[^\s'\"`)]*)?")

# Legitimate skills carry example credentials in docs and fixtures in tests, so a
# scanner with no suppression is a scanner people disable. The pragma must sit on the
# matching line or the one above it, and every use is listed in the report — a
# suppression nobody can see is just a way to hide a real secret.
ALLOW_RE = re.compile(r'skilleng:allow-secret')
TEXT_SUFFIXES = {
    '.md',
    '.py',
    '.sh',
    '.bash',
    '.js',
    '.ts',
    '.json',
    '.yaml',
    '.yml',
    '.toml',
    '.txt',
    '.cfg',
    '.ini',
    '.rb',
    '.go',
    '.rs',
    '.java',
    '.pl',
}


@dataclass
class SecurityReport:
    skill: str
    files_included: int
    files_excluded: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    suppressed: list[str] = field(default_factory=list)
    scripts: list[dict] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    proposed_allowed_tools: list[str] = field(default_factory=list)
    declared_allowed_tools: str | None = None

    @property
    def blocking(self) -> bool:
        return bool(self.secrets)

    def to_markdown(self) -> str:
        lines = [
            f'# Security report — {self.skill}',
            '',
            (
                'What an installer is agreeing to run. Generated at package time; '
                'review before granting this skill shell access.'
            ),
            '',
            f'- Files packaged: **{self.files_included}**',
            f'- Files excluded by policy: **{len(self.files_excluded)}**',
            f'- Executable scripts: **{len(self.scripts)}**',
            f'- Distinct network endpoints referenced: **{len(self.endpoints)}**',
            '',
        ]
        if self.secrets:
            lines += ['## Possible secrets — packaging blocked', '']
            lines += [f'- **{s}**' for s in self.secrets]
            lines += ['', 'Remove or redact these, then package again.', '']
        if self.suppressed:
            lines += [
                '## Suppressed secret matches',
                '',
                (
                    'Marked `skilleng:allow-secret` by the author. Listed here so a '
                    'suppression is never invisible — confirm each one is genuinely an '
                    'example or a fixture.'
                ),
                '',
            ]
            lines += [f'- {s}' for s in self.suppressed]
            lines.append('')
        if self.scripts:
            lines += [
                '## Bundled scripts',
                '',
                '| Script | Lines | Behaviour |',
                '|---|---|---|',
            ]
            for s in self.scripts:
                behaviours = ', '.join(s['behaviours']) or 'no flagged behaviour'
                lines.append(f'| `{s["path"]}` | {s["lines"]} | {behaviours} |')
            lines.append('')
        if self.endpoints:
            lines += [
                '## Network endpoints',
                '',
                (
                    "On Copilot's cloud agent these must be on the firewall allowlist "
                    'or the request is blocked and reported as a PR warning rather '
                    'than a hard failure.'
                ),
                '',
            ]
            lines += [f'- `{e}`' for e in sorted(self.endpoints)]
            lines.append('')
        lines += [
            '## Permissions',
            '',
            f'- Declared `allowed-tools`: `{self.declared_allowed_tools or "(none)"}`',
            (
                f'- Minimum implied by the bundled scripts: '
                f'`{" ".join(self.proposed_allowed_tools) or "(none)"}`'
            ),
            '',
        ]
        if self.files_excluded:
            lines += (
                ['## Excluded by policy', '']
                + [f'- `{f}`' for f in sorted(self.files_excluded)[:40]]
                + ['']
            )
        return '\n'.join(lines)


def _excluded(rel: Path) -> bool:
    if any(part in DENY_DIRS for part in rel.parts):
        return True
    return any(fnmatch.fnmatch(rel.name, g) for g in DENY_GLOBS)


def scan(skill_dir: Path) -> SecurityReport:
    skill_dir = Path(skill_dir).resolve()
    skill = load(skill_dir)
    rep = SecurityReport(
        skill=skill_dir.name,
        files_included=0,
        declared_allowed_tools=skill.frontmatter.get('allowed-tools'),
    )
    tools: set[str] = set()

    for p in sorted(skill_dir.rglob('*')):
        if not p.is_file():
            continue
        rel = p.relative_to(skill_dir)
        if _excluded(rel):
            rep.files_excluded.append(str(rel))
            continue
        rep.files_included += 1
        if p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = p.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue

        lines = text.splitlines()
        seen: set[tuple[str, int]] = set()
        for label, pat in SECRET_PATTERNS:
            for m in pat.finditer(text):
                n = text[: m.start()].count('\n')
                if (label, n) in seen:
                    continue
                seen.add((label, n))
                context = '\n'.join(lines[max(0, n - 1) : n + 1])
                where = f'{label} in `{rel}` line {n + 1}'
                (rep.suppressed if ALLOW_RE.search(context) else rep.secrets).append(
                    where
                )

        for u in URL_RE.findall(text):
            host = u.split('/')[2] if '://' in u else u
            rep.endpoints.append(host)

        if rel.parts and rel.parts[0] == 'scripts':
            behaviours = [label for label, pat in EXEC_PATTERNS if pat.search(text)]
            rep.scripts.append({
                'path': str(rel),
                'lines': text.count('\n') + 1,
                'behaviours': behaviours,
            })
            if p.suffix in ('.py', '.sh', '.bash'):
                tools.add('Bash')
            if 'makes network requests' in behaviours:
                tools.add('WebFetch')
            if any(
                b in behaviours for b in ('writes outside the workspace', 'deletes files')
            ):
                tools.add('Write')

    rep.endpoints = sorted(set(rep.endpoints))
    rep.proposed_allowed_tools = sorted(tools)
    return rep


def package(
    skill_dir: Path, out_dir: Path | None = None, include_evals: bool = True
) -> tuple[Path | None, SecurityReport, list[Finding]]:
    """Package a skill, or refuse. Returns (archive, security report, lint findings).

    `evals/` ships by default — a distributed skill that cannot re-verify itself
    after a model upgrade is a skill nobody can maintain.
    """
    skill_dir = Path(skill_dir).resolve()
    findings = lint(skill_dir)
    rep = scan(skill_dir)
    if errors(findings) or rep.blocking:
        return None, rep, findings

    out_dir = Path(out_dir or Path.cwd()).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f'{skill_dir.name}.skill'

    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(skill_dir.rglob('*')):
            if not p.is_file():
                continue
            rel = p.relative_to(skill_dir)
            if _excluded(rel):
                continue
            if not include_evals and rel.parts and rel.parts[0] == 'evals':
                continue
            z.write(p, Path(skill_dir.name) / rel)
        z.writestr(f'{skill_dir.name}/SECURITY.md', rep.to_markdown())
    (out_dir / f'{skill_dir.name}-SECURITY.md').write_text(rep.to_markdown())
    return archive, rep, findings

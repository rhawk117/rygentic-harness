import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from vibe_code_cli.findings import Finding, error, warning

LINE_BUDGET = 500
RESOURCE_DIRS = ('scripts', 'references', 'assets')
MARKDOWN_LINK = re.compile(r'!?\[[^\]\n]*\]\(([^\n)]+)\)')
RESOURCE_REFERENCE = re.compile(
    r'(?<![A-Za-z0-9_./-])'
    r'((?:\./)?(?:scripts|references|assets)/'
    r'[^\s`<>"\'()\]\[{}]+)'
)
URI_SCHEME = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:')


@dataclass(slots=True, kw_only=True, frozen=True)
class Referenced:
    files: frozenset[str]
    directories: frozenset[str]


def check_body(skill_dir: Path, text: str, body: str) -> list[Finding]:
    findings = (
        check_resources(skill_dir, body)
        if body.strip()
        else [error('SKILL.md has no Markdown body after the frontmatter')]
    )
    line_count = len(text.splitlines())
    if line_count > LINE_BUDGET:
        findings.append(
            warning(
                f'SKILL.md is {line_count} lines; keep it under {LINE_BUDGET} '
                'and move detail into referenced files'
            )
        )
    return findings


def check_resources(skill_dir: Path, body: str) -> list[Finding]:
    problems = {
        reference: reference_problem(skill_dir, reference)
        for reference in sorted(referenced_files(body))
    }
    referenced = Referenced(
        files=frozenset(problems),
        directories=frozenset(
            reference
            for reference, problem in problems.items()
            if problem is None and skill_dir.joinpath(reference).is_dir()
        ),
    )

    findings = list(filter(None, problems.values()))
    for subdirectory in RESOURCE_DIRS:
        findings.extend(scan_directory(skill_dir, subdirectory, referenced))

    return findings


def reference_problem(skill_dir: Path, reference: str) -> Finding | None:
    pure = PurePosixPath(reference)
    if pure.is_absolute() or ".." in pure.parts:
        return error(f"reference escapes the skill directory: {reference}")

    path = skill_dir.joinpath(*pure.parts)
    if not path.resolve(strict=False).is_relative_to(skill_dir.resolve()):
        return error(
            f"reference escapes the skill directory through a symlink: {reference}"
        )

    if not path.exists():
        return error(f"body references {reference} but it does not exist")

    return None


def scan_directory(
    skill_dir: Path, subdirectory: str, referenced: Referenced
) -> list[Finding]:
    directory = skill_dir.joinpath(subdirectory)
    if not directory.is_dir():
        return []

    if not any(directory.iterdir()):
        return [warning(f"{subdirectory}/ is empty")]

    entries = (scan_entry(skill_dir, path, referenced) for path in directory.rglob('*'))
    return [finding for finding in entries if finding is not None]


def scan_entry(skill_dir: Path, path: Path, referenced: Referenced) -> Finding | None:
    relative = path.relative_to(skill_dir).as_posix()

    if path.is_symlink() and not path.resolve(strict=False).is_relative_to(
        skill_dir.resolve()
    ):
        return error(f"{relative} is a symlink outside the skill directory")

    if not path.is_file() or path.suffix == '.pyc' or '__pycache__' in path.parts:
        return None

    if relative in referenced.files or any(
        relative.startswith(f"{directory}/") for directory in referenced.directories
    ):
        return None

    return warning(
        f'{relative} is never referenced in SKILL.md; '
        'progressive disclosure has no explicit instruction for when to use it'
    )


def referenced_files(body: str) -> set[str]:
    candidates = [
        normalized_reference(link_target(match.group(1)), resource_only=False)
        for match in MARKDOWN_LINK.finditer(body)
    ]
    candidates.extend(
        normalized_reference(match.group(1), resource_only=False)
        for match in RESOURCE_REFERENCE.finditer(body)
    )
    candidates = filter(None, candidates)
    return set(candidates)


def link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith('<'):
        closing = target.find('>')
        return target[1:closing] if closing > 0 else target

    words = target.split(maxsplit=1)
    return words[0] if words else ''


def normalized_reference(value: str, *, resource_only: bool) -> str | None:
    value = value.strip().rstrip('.,;:!?')
    if not is_local_reference(value):
        return None

    value = value.removeprefix('./').split('#', 1)[0].split('?', 1)[0]
    if not value:
        return None

    path = PurePosixPath(value)
    if resource_only and (not path.parts or path.parts[0] not in RESOURCE_DIRS):
        return None
    return path.as_posix()


def is_local_reference(value: str) -> bool:
    if not value or value.startswith(('/', '#')):
        return False

    if URI_SCHEME.match(value):
        return False

    return not any(marker in value for marker in '<>{}$')

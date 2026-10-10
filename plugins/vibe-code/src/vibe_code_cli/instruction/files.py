from dataclasses import dataclass
from pathlib import Path

from vibe_code_cli.findings import CannotCheckError

ALWAYS_ON_NAMES = ('CLAUDE.md', '.claude/CLAUDE.md', 'CLAUDE.local.md', 'AGENTS.md')
RULES_GLOB = '.claude/rules/**/*.md'


@dataclass(slots=True, kw_only=True, frozen=True)
class InstructionFile:
    relative: str
    text: str
    size: int
    always_on: bool
    symlink: bool

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as problem:
        message = f'could not read {path}: {problem}'
        raise CannotCheckError(message) from problem


def discover(root: Path) -> list[InstructionFile]:
    always_on = {root / name for name in ALWAYS_ON_NAMES}
    candidates = always_on | set(root.glob(RULES_GLOB))
    return [
        InstructionFile(
            relative=path.relative_to(root).as_posix(),
            text=read_text(path),
            size=path.stat().st_size,
            always_on=path in always_on,
            symlink=path.is_symlink(),
        )
        for path in sorted(candidates)
        if path.is_file()
    ]


def strip_code_fences(lines: list[str]) -> list[tuple[int, str]]:
    kept: list[tuple[int, str]] = []
    inside = False
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith('```'):
            inside = not inside
            continue

        if not inside:
            kept.append((number, line))

    return kept

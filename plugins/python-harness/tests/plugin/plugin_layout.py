"""Paths and frontmatter parsers shared by the plugin layout tests."""

from itertools import takewhile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SKILL_FILES = sorted(PLUGIN_ROOT.glob('skills/*/SKILL.md'))
AGENT_FILES = sorted(PLUGIN_ROOT.glob('agents/*.md'))
SKILL_MARKDOWN = sorted(PLUGIN_ROOT.joinpath('skills').rglob('*.md'))
WRITE_TOOLS = ('Edit', 'Write', 'NotebookEdit')
SKILL_DISALLOWED = {
    'build-web-service': WRITE_TOOLS,
    'enterprise-design': WRITE_TOOLS,
    'design-persistence': WRITE_TOOLS,
    'design-tests': WRITE_TOOLS,
    'tactical-slop-review': ('Edit', 'NotebookEdit'),
    'automate-task': (),
    'data-analysis': (),
    'data-engineering': (),
}


def document_parts(document: Path) -> tuple[str, str]:
    _, frontmatter, body = document.read_text(encoding='utf-8').split('---\n', maxsplit=2)
    return frontmatter, body


def block_list_entries(frontmatter: str, key: str) -> list[str]:
    lines = frontmatter.splitlines()
    if f'{key}:' not in lines:
        return []
    following = lines[lines.index(f'{key}:') + 1 :]
    return [
        line.removeprefix('  - ') for line in takewhile(lambda x: x.startswith('  - '), following)
    ]


def inline_list_entries(frontmatter: str, key: str) -> list[str]:
    prefix = f'{key}: '
    values = [
        line.removeprefix(prefix) for line in frontmatter.splitlines() if line.startswith(prefix)
    ]
    return values[0].split(', ') if values else []


def skill_name(document: Path) -> str:
    return document.parent.name

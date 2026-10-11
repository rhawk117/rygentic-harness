"""MCP tool names the review skill and the pylens agent carry, against the server's tools."""

import re
from pathlib import Path

import pytest
from mcp import Client

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
TOOL_PREFIX = 'mcp__plugin_python-harness_python-harness__'
TOOL_REFERENCE = re.compile(rf'{TOOL_PREFIX}(?P<tool>\w+)')
REFERENCING_DIRECTORIES = ('skills', 'agents')
PYLENS = PLUGIN_ROOT.joinpath('agents', 'pylens.md')
SKILL = PLUGIN_ROOT.joinpath('skills', 'tactical-slop-review', 'SKILL.md')
PYLENS_TOOLS = (
    'tools: Read, Grep, Glob,'
    f' {TOOL_PREFIX}collect_python_facts,'
    f' {TOOL_PREFIX}map_python_calls,'
    f' {TOOL_PREFIX}check_citations'
)
SKILL_TOOLS = [
    'check_citations',
    'collect_python_facts',
    'gate',
    'map_python_calls',
    'plan_review_surface',
    'survey',
]
SKILL_BASH = [
    'Bash(git rev-parse HEAD)',
    'Bash(git symbolic-ref --short refs/remotes/origin/HEAD)',
    'Bash(git fetch origin *)',
    'Bash(gh pr view *)',
]


def referenced_tools() -> set[str]:
    files = (
        path
        for directory in REFERENCING_DIRECTORIES
        for path in PLUGIN_ROOT.joinpath(directory).rglob('*.md')
    )
    texts = (path.read_text(encoding='utf-8') for path in files)
    return {found['tool'] for text in texts for found in TOOL_REFERENCE.finditer(text)}


def frontmatter_lines(document: Path) -> list[str]:
    _, frontmatter, _ = document.read_text(encoding='utf-8').split('---\n', maxsplit=2)
    return frontmatter.splitlines()


@pytest.mark.anyio
class TestReferencedTools:
    async def test_every_tool_named_by_the_skill_or_an_agent_is_one_the_server_lists(
        self, docs_client: Client
    ) -> None:
        listed = {tool.name for tool in (await docs_client.list_tools()).tools}

        referenced = referenced_tools()

        assert (bool(referenced), referenced - listed) == (True, set())


class TestFrontmatter:
    def test_pylens_has_its_read_tools_and_exactly_three_server_tools(self) -> None:
        tools = [line for line in frontmatter_lines(PYLENS) if line.startswith('tools:')]

        assert tools == [PYLENS_TOOLS]

    def test_the_skill_allows_the_six_project_tools_and_keeps_its_bash_entries(self) -> None:
        entries = [line.removeprefix('  - ') for line in frontmatter_lines(SKILL)]
        allowed = sorted(
            entry.removeprefix(TOOL_PREFIX) for entry in entries if entry.startswith(TOOL_PREFIX)
        )
        bash = [entry for entry in entries if entry.startswith('Bash(')]

        assert (allowed, bash) == (SKILL_TOOLS, SKILL_BASH)

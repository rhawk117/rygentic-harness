"""MCP tool names, tool grants and read-only boundaries of the plugin's skills and agents."""

import re
from dataclasses import dataclass
from itertools import takewhile
from pathlib import Path

import pytest
from mcp import Client

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
TOOL_PREFIX = 'mcp__plugin_python-harness_python-harness__'
TOOL_REFERENCE = re.compile(rf'{TOOL_PREFIX}(?P<tool>\w+)')
SERVER_TOOLS = frozenset(
    {
        'survey',
        'gate',
        'plan_review_surface',
        'collect_python_facts',
        'map_python_calls',
        'check_citations',
        'search_python_docs',
        'read_python_docs',
    }
)
SHORT_TOOL = re.compile(rf'`({"|".join(sorted(SERVER_TOOLS))})`')
DATA_COMMAND = re.compile(r'python-harness-data (?P<subcommand>[a-z][\w-]*)')
LAUNCHER_ENTRY = re.compile(r"^    '(?P<name>[\w-]+)': ", re.MULTILINE)
DATA_LAUNCHER = PLUGIN_ROOT.joinpath('bin', 'python-harness-data')
REFERENCING_DIRECTORIES = ('skills', 'agents')
SKILL_FILES = sorted(PLUGIN_ROOT.glob('skills/*/SKILL.md'))
AGENT_FILES = sorted(PLUGIN_ROOT.glob('agents/*.md'))
SKILL_MARKDOWN = sorted(PLUGIN_ROOT.joinpath('skills').rglob('*.md'))
SKILL = PLUGIN_ROOT.joinpath('skills', 'tactical-slop-review', 'SKILL.md')
SKILL_TOOLS = [
    'check_citations',
    'collect_python_facts',
    'gate',
    'map_python_calls',
    'plan_review_surface',
    'read_python_docs',
    'search_python_docs',
    'survey',
]
SKILL_BASH = [
    'Bash(git rev-parse HEAD)',
    'Bash(git symbolic-ref --short refs/remotes/origin/HEAD)',
    'Bash(git fetch origin *)',
    'Bash(gh pr view *)',
]
LAUNCHER_BASH = ('Bash(python-harness *)', 'Bash(python-harness-data *)')
DATA_BASH = 'Bash(python-harness-data *)'
WRITE_TOOLS = ('Edit', 'Write', 'NotebookEdit')
READ_ONLY_FORBIDDEN_GRANTS = ('Bash', 'Edit', 'Write', 'NotebookEdit', f'{TOOL_PREFIX}gate')
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


def server(*names: str) -> tuple[str, ...]:
    return tuple(f'{TOOL_PREFIX}{name}' for name in names)


@dataclass(frozen=True, kw_only=True)
class AgentGrant:
    tools: tuple[str, ...]
    disallowed: tuple[str, ...]
    skills: tuple[str, ...]


AGENT_GRANTS = {
    'pylens': AgentGrant(
        tools=(
            'Read',
            'Grep',
            'Glob',
            *server('collect_python_facts', 'map_python_calls', 'check_citations', 'survey'),
        ),
        disallowed=('Bash', *WRITE_TOOLS),
        skills=(),
    ),
    'pep-talk': AgentGrant(
        tools=(
            'Read',
            'Grep',
            'Glob',
            *server('search_python_docs', 'read_python_docs', 'survey', 'check_citations'),
        ),
        disallowed=('Bash', *WRITE_TOOLS),
        skills=(),
    ),
    'reviewer': AgentGrant(
        tools=(
            'Read',
            'Grep',
            'Glob',
            'Bash',
            *server('plan_review_surface', 'check_citations', 'survey', 'gate'),
        ),
        disallowed=WRITE_TOOLS,
        skills=('tactical-slop-review',),
    ),
    'test-engineer': AgentGrant(
        tools=(
            'Read',
            'Grep',
            'Glob',
            'Bash',
            'Edit',
            'Write',
            *server(
                'survey',
                'collect_python_facts',
                'map_python_calls',
                'gate',
                'search_python_docs',
                'read_python_docs',
            ),
        ),
        disallowed=(),
        skills=('design-tests',),
    ),
}


def referenced_tools() -> set[str]:
    files = (
        path
        for directory in REFERENCING_DIRECTORIES
        for path in PLUGIN_ROOT.joinpath(directory).rglob('*.md')
    )
    texts = (path.read_text(encoding='utf-8') for path in files)
    return {found['tool'] for text in texts for found in TOOL_REFERENCE.finditer(text)}


def document_parts(document: Path) -> tuple[str, str]:
    _, frontmatter, body = document.read_text(encoding='utf-8').split('---\n', maxsplit=2)
    return frontmatter, body


def frontmatter_lines(document: Path) -> list[str]:
    return document_parts(document)[0].splitlines()


def list_entries(frontmatter: str, key: str) -> list[str]:
    lines = frontmatter.splitlines()
    if f'{key}:' not in lines:
        return []
    following = lines[lines.index(f'{key}:') + 1 :]
    return [
        line.removeprefix('  - ') for line in takewhile(lambda x: x.startswith('  - '), following)
    ]


def line_entries(frontmatter: str, key: str) -> list[str]:
    prefix = f'{key}: '
    values = [
        line.removeprefix(prefix) for line in frontmatter.splitlines() if line.startswith(prefix)
    ]
    return values[0].split(', ') if values else []


def tool_mismatch(frontmatter: str, body: str) -> tuple[set[str], set[str]]:
    entries = list_entries(frontmatter, 'allowed-tools')
    granted = {
        entry.removeprefix(TOOL_PREFIX) for entry in entries if entry.startswith(TOOL_PREFIX)
    }
    named = {found['tool'] for found in TOOL_REFERENCE.finditer(body)}
    named |= set(SHORT_TOOL.findall(body))
    return granted - named, named - granted


def launcher_subcommands() -> set[str]:
    text = DATA_LAUNCHER.read_text(encoding='utf-8')
    return {found['name'] for found in LAUNCHER_ENTRY.finditer(text)}


def unknown_subcommands(text: str, known: set[str]) -> set[str]:
    return {found['subcommand'] for found in DATA_COMMAND.finditer(text)} - known


def skill_name(document: Path) -> str:
    return document.parent.name


@pytest.mark.anyio
class TestReferencedTools:
    async def test_every_tool_named_by_the_skill_or_an_agent_is_one_the_server_lists(
        self, docs_client: Client
    ) -> None:
        listed = {tool.name for tool in (await docs_client.list_tools()).tools}

        referenced = referenced_tools()

        assert (bool(referenced), referenced - listed) == (True, set())

    async def test_the_tool_names_the_tests_know_are_the_ones_the_server_lists(
        self, docs_client: Client
    ) -> None:
        listed = {tool.name for tool in (await docs_client.list_tools()).tools}

        assert listed == SERVER_TOOLS

    def test_the_plugin_ships_eight_skills_and_four_agents(self) -> None:
        assert (len(SKILL_FILES), len(AGENT_FILES)) == (8, 4)

    def test_the_skills_and_agents_found_are_the_ones_the_tests_pin(self) -> None:
        skills = {skill_name(path) for path in SKILL_FILES}
        agents = {path.stem for path in AGENT_FILES}

        assert (skills, agents) == (set(SKILL_DISALLOWED), set(AGENT_GRANTS))


class TestAgentGrants:
    @pytest.mark.parametrize('document', AGENT_FILES, ids=lambda path: path.stem)
    def test_each_agent_holds_exactly_the_tools_it_is_designed_to_hold(
        self, document: Path
    ) -> None:
        frontmatter = document_parts(document)[0]
        grant = AGENT_GRANTS[document.stem]

        held = (
            tuple(line_entries(frontmatter, 'tools')),
            tuple(line_entries(frontmatter, 'disallowedTools')),
            tuple(list_entries(frontmatter, 'skills')),
        )

        assert held == (grant.tools, grant.disallowed, grant.skills)

    @pytest.mark.parametrize('name', ['pylens', 'pep-talk'])
    def test_the_read_only_agents_grant_no_shell_write_or_gate_and_deny_the_write_tools(
        self, name: str
    ) -> None:
        frontmatter = document_parts(PLUGIN_ROOT.joinpath('agents', f'{name}.md'))[0]
        tools = line_entries(frontmatter, 'tools')

        granted = [tool for tool in READ_ONLY_FORBIDDEN_GRANTS if tool in tools]

        assert (granted, line_entries(frontmatter, 'disallowedTools')) == (
            [],
            ['Bash', *WRITE_TOOLS],
        )

    def test_the_reviewer_grants_neither_edit_nor_write_and_denies_all_three_write_tools(
        self,
    ) -> None:
        frontmatter = document_parts(PLUGIN_ROOT.joinpath('agents', 'reviewer.md'))[0]
        tools = line_entries(frontmatter, 'tools')

        granted = [tool for tool in ('Edit', 'Write') if tool in tools]

        assert (granted, line_entries(frontmatter, 'disallowedTools')) == ([], list(WRITE_TOOLS))


class TestSkillGrants:
    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_the_server_tools_a_skill_allows_are_the_ones_its_body_names(
        self, document: Path
    ) -> None:
        frontmatter, body = document_parts(document)

        assert tool_mismatch(frontmatter, body) == (set(), set())

    @pytest.mark.parametrize(
        ('frontmatter', 'body', 'expected'),
        [
            pytest.param(
                f'allowed-tools:\n  - Read\n  - {TOOL_PREFIX}survey\n  - {TOOL_PREFIX}gate\n',
                'Call `survey` first.',
                ({'gate'}, set()),
                id='granted-but-never-named',
            ),
            pytest.param(
                f'allowed-tools:\n  - Read\n  - {TOOL_PREFIX}survey\n',
                'Call `survey`, then `gate`.',
                (set(), {'gate'}),
                id='named-short-but-not-granted',
            ),
            pytest.param(
                f'allowed-tools:\n  - Read\n  - {TOOL_PREFIX}survey\n',
                f'Call `survey`, then `{TOOL_PREFIX}check_citations`.',
                (set(), {'check_citations'}),
                id='named-in-full-but-not-granted',
            ),
            pytest.param(
                f'allowed-tools:\n  - Read\n  - {TOOL_PREFIX}gate\n',
                'The gate is a noun here.',
                ({'gate'}, set()),
                id='a-bare-word-does-not-name-a-tool',
            ),
        ],
    )
    def test_a_grant_and_a_mention_that_disagree_are_reported_in_the_right_direction(
        self, frontmatter: str, body: str, expected: tuple[set[str], set[str]]
    ) -> None:
        assert tool_mismatch(frontmatter, body) == expected

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_a_skill_denies_exactly_the_tools_it_is_designed_to_deny(self, document: Path) -> None:
        frontmatter = document_parts(document)[0]

        denied = tuple(list_entries(frontmatter, 'disallowed-tools'))

        assert denied == SKILL_DISALLOWED[skill_name(document)]

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_a_skill_carries_the_data_launcher_pattern_exactly_when_its_body_names_a_command(
        self, document: Path
    ) -> None:
        frontmatter, body = document_parts(document)
        bash = [e for e in list_entries(frontmatter, 'allowed-tools') if e.startswith('Bash(')]

        carried = [entry for entry in bash if entry in LAUNCHER_BASH]
        other = [entry for entry in bash if entry not in LAUNCHER_BASH]

        assert (DATA_BASH in carried, other) == (
            bool(DATA_COMMAND.search(body)),
            SKILL_BASH if document == SKILL else [],
        )


class TestDataCommands:
    def test_the_launcher_defines_the_four_data_commands(self) -> None:
        assert launcher_subcommands() == {
            'alert-budget',
            'paired-compare',
            'profile-data',
            'size-check',
        }

    @pytest.mark.parametrize(
        'document', SKILL_MARKDOWN, ids=lambda path: str(path.relative_to(PLUGIN_ROOT))
    )
    def test_every_data_command_a_skill_file_names_is_one_the_launcher_defines(
        self, document: Path
    ) -> None:
        text = document.read_text(encoding='utf-8')

        assert unknown_subcommands(text, launcher_subcommands()) == set()

    def test_a_command_the_launcher_does_not_define_is_reported(self) -> None:
        text = 'Run `python-harness-data size-check dense` then `python-harness-data frobnicate x`.'

        assert unknown_subcommands(text, launcher_subcommands()) == {'frobnicate'}


class TestFrontmatter:
    def test_the_skill_allows_the_eight_server_tools_and_keeps_its_bash_entries(self) -> None:
        entries = [line.removeprefix('  - ') for line in frontmatter_lines(SKILL)]
        allowed = sorted(
            entry.removeprefix(TOOL_PREFIX) for entry in entries if entry.startswith(TOOL_PREFIX)
        )
        bash = [entry for entry in entries if entry.startswith('Bash(')]

        assert (allowed, bash) == (SKILL_TOOLS, SKILL_BASH)

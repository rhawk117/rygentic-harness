"""MCP tool names, tool grants and read-only boundaries of the plugin's skills and agents."""

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from mcp import Client
from plugin_layout import (
    AGENT_FILES,
    PLUGIN_ROOT,
    SKILL_DISALLOWED,
    SKILL_FILES,
    SKILL_MARKDOWN,
    WRITE_TOOLS,
    block_list_entries,
    document_parts,
    inline_list_entries,
    skill_name,
)

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
REVIEW_SKILL = PLUGIN_ROOT.joinpath('skills', 'tactical-slop-review', 'SKILL.md')
AUTOMATE_TASK = PLUGIN_ROOT.joinpath('skills', 'automate-task', 'SKILL.md')
REVIEW_SKILL_TOOLS = [
    'check_citations',
    'collect_python_facts',
    'gate',
    'map_python_calls',
    'plan_review_surface',
    'read_python_docs',
    'search_python_docs',
    'survey',
]
REVIEW_SKILL_BASH = [
    'Bash(git rev-parse HEAD)',
    'Bash(git symbolic-ref --short refs/remotes/origin/HEAD)',
    'Bash(git fetch origin *)',
    'Bash(gh pr view *)',
]
LAUNCHER_BASH = ('Bash(python-harness *)', 'Bash(python-harness-data *)')
DATA_BASH = 'Bash(python-harness-data *)'
BUNDLED_SCRIPT_BASH = [
    'Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/check_script.py *)',
    'Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/parallelism.py *)',
]
OTHER_BASH = {'tactical-slop-review': REVIEW_SKILL_BASH, 'automate-task': BUNDLED_SCRIPT_BASH}
READ_ONLY_FORBIDDEN_GRANTS = ('Bash', 'Edit', 'Write', 'NotebookEdit', f'{TOOL_PREFIX}gate')


def server_tool_names(*names: str) -> tuple[str, ...]:
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
            *server_tool_names(
                'collect_python_facts', 'map_python_calls', 'check_citations', 'survey'
            ),
        ),
        disallowed=('Bash', *WRITE_TOOLS),
        skills=(),
    ),
    'pep-talk': AgentGrant(
        tools=(
            'Read',
            'Grep',
            'Glob',
            *server_tool_names(
                'search_python_docs', 'read_python_docs', 'survey', 'check_citations'
            ),
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
            *server_tool_names('plan_review_surface', 'check_citations', 'survey', 'gate'),
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
            *server_tool_names(
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


def tool_mismatch(frontmatter: str, body: str) -> tuple[set[str], set[str]]:
    entries = block_list_entries(frontmatter, 'allowed-tools')
    granted = {
        entry.removeprefix(TOOL_PREFIX) for entry in entries if entry.startswith(TOOL_PREFIX)
    }
    named = {found['tool'] for found in TOOL_REFERENCE.finditer(body)}
    named |= set(SHORT_TOOL.findall(body))
    return granted - named, named - granted


def bash_mismatch(frontmatter: str, name: str) -> tuple[list[str], list[str]]:
    bash = [e for e in block_list_entries(frontmatter, 'allowed-tools') if e.startswith('Bash(')]
    carried = [entry for entry in bash if entry not in LAUNCHER_BASH]
    listed = OTHER_BASH.get(name, [])
    return (
        [entry for entry in carried if entry not in listed],
        [entry for entry in listed if entry not in carried],
    )


def launcher_subcommands() -> set[str]:
    text = DATA_LAUNCHER.read_text(encoding='utf-8')
    return {found['name'] for found in LAUNCHER_ENTRY.finditer(text)}


def unknown_subcommands(text: str, known: set[str]) -> set[str]:
    return {found['subcommand'] for found in DATA_COMMAND.finditer(text)} - known


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
            tuple(inline_list_entries(frontmatter, 'tools')),
            tuple(inline_list_entries(frontmatter, 'disallowedTools')),
            tuple(block_list_entries(frontmatter, 'skills')),
        )

        assert held == (grant.tools, grant.disallowed, grant.skills)

    @pytest.mark.parametrize('name', ['pylens', 'pep-talk'])
    def test_the_read_only_agents_grant_no_shell_write_or_gate_and_deny_the_write_tools(
        self, name: str
    ) -> None:
        frontmatter = document_parts(PLUGIN_ROOT.joinpath('agents', f'{name}.md'))[0]
        tools = inline_list_entries(frontmatter, 'tools')

        granted = [tool for tool in READ_ONLY_FORBIDDEN_GRANTS if tool in tools]

        assert (granted, inline_list_entries(frontmatter, 'disallowedTools')) == (
            [],
            ['Bash', *WRITE_TOOLS],
        )

    def test_the_reviewer_grants_neither_edit_nor_write_and_denies_all_three_write_tools(
        self,
    ) -> None:
        frontmatter = document_parts(PLUGIN_ROOT.joinpath('agents', 'reviewer.md'))[0]
        tools = inline_list_entries(frontmatter, 'tools')

        granted = [tool for tool in ('Edit', 'Write') if tool in tools]

        assert (granted, inline_list_entries(frontmatter, 'disallowedTools')) == (
            [],
            list(WRITE_TOOLS),
        )


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

        denied = tuple(block_list_entries(frontmatter, 'disallowed-tools'))

        assert denied == SKILL_DISALLOWED[skill_name(document)]

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_a_skill_carries_the_data_launcher_pattern_exactly_when_its_body_names_a_command(
        self, document: Path
    ) -> None:
        frontmatter, body = document_parts(document)
        entries = block_list_entries(frontmatter, 'allowed-tools')

        mismatch = bash_mismatch(frontmatter, skill_name(document))

        assert (DATA_BASH in entries, mismatch) == (bool(DATA_COMMAND.search(body)), ([], []))

    @pytest.mark.parametrize(
        ('name', 'bash', 'expected'),
        [
            pytest.param('automate-task', BUNDLED_SCRIPT_BASH, ([], []), id='the-bundled-rules'),
            pytest.param('automate-task', [], ([], BUNDLED_SCRIPT_BASH), id='the-rules-missing'),
            pytest.param(
                'automate-task',
                [*BUNDLED_SCRIPT_BASH, 'Bash(uv run *)'],
                (['Bash(uv run *)'], []),
                id='a-rule-that-also-covers-the-generated-script',
            ),
            pytest.param(
                'design-tests',
                BUNDLED_SCRIPT_BASH,
                (BUNDLED_SCRIPT_BASH, []),
                id='the-rules-on-another-skill',
            ),
            pytest.param('data-analysis', [DATA_BASH], ([], []), id='a-launcher-alone'),
        ],
    )
    def test_a_bash_pattern_a_skill_is_not_listed_for_is_reported(
        self, name: str, bash: list[str], expected: tuple[list[str], list[str]]
    ) -> None:
        frontmatter = ''.join(['allowed-tools:\n  - Read\n', *(f'  - {e}\n' for e in bash)])

        assert bash_mismatch(frontmatter, name) == expected

    def test_automate_task_pre_approves_its_bundled_scripts_in_its_last_entries(self) -> None:
        frontmatter, body = document_parts(AUTOMATE_TASK)
        commands = [entry.removeprefix('Bash(').removesuffix('*)') for entry in BUNDLED_SCRIPT_BASH]

        last = block_list_entries(frontmatter, 'allowed-tools')[-len(BUNDLED_SCRIPT_BASH) :]

        assert (last, all(command in body for command in commands)) == (BUNDLED_SCRIPT_BASH, True)


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
        entries = block_list_entries(document_parts(REVIEW_SKILL)[0], 'allowed-tools')
        allowed = sorted(
            entry.removeprefix(TOOL_PREFIX) for entry in entries if entry.startswith(TOOL_PREFIX)
        )
        bash = [entry for entry in entries if entry.startswith('Bash(')]

        assert (allowed, bash) == (REVIEW_SKILL_TOOLS, REVIEW_SKILL_BASH)

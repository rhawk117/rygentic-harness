"""Each skill's frontmatter says when to use it, who may start it and which tools it pre-approves.

A skill started with a slug or a target hints at the argument and reads it in its body, and no
skill holds a key but the ones pinned here.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import pytest
from mightymodels_plugin.server import SERVER_NAME, TOOLS

SKILLS = Path(__file__).parent.parent.joinpath('skills')
FRONTMATTER = re.compile(r'\A---\n(?P<head>.*?)\n---\n(?P<body>.*)\Z', re.DOTALL)
FIELD = re.compile(r'^(?P<key>[\w-]+):(?P<value>.*(?:\n[ \t]+.*)*)$', re.MULTILINE)
LISTED_TOOL = re.compile(r'^[ \t]+- (?P<name>\S+)$', re.MULTILINE)
STATE_TOOL = re.compile(r'\bmcp__\w+')
QUESTION_TOOL = 'AskUserQuestion'
ARGUMENTS = '$ARGUMENTS'


@dataclass(slots=True, kw_only=True, frozen=True)
class SkillFile:
    name: str
    keys: frozenset[str]
    description: str
    when_to_use: str
    human_only: bool
    hidden_from_the_user: bool
    allowed_tools: tuple[str, ...]
    body: str


def folded(value: str) -> str:
    return ' '.join(value.removeprefix(' >-').split())


def skill_file(path: Path) -> SkillFile:
    parts = FRONTMATTER.match(path.read_text(encoding='utf-8'))
    assert parts is not None, path.parent.name
    fields = {found['key']: found['value'] for found in FIELD.finditer(parts['head'])}
    return SkillFile(
        name=path.parent.name,
        keys=frozenset(fields),
        description=folded(fields.get('description', '')),
        when_to_use=folded(fields.get('when_to_use', '')),
        human_only=fields.get('disable-model-invocation', '').strip() == 'true',
        hidden_from_the_user=fields.get('user-invocable', '').strip() == 'false',
        allowed_tools=tuple(LISTED_TOOL.findall(fields.get('allowed-tools', ''))),
        body=parts['body'],
    )


SKILL_FILES = tuple(map(skill_file, sorted(SKILLS.glob('*/SKILL.md'))))
EVERY_SKILL = pytest.mark.parametrize(
    'skill', [pytest.param(skill, id=skill.name) for skill in SKILL_FILES]
)


class TestListingOfTheSkills:
    LISTING_CAP = 1536

    @EVERY_SKILL
    def test_the_description_and_when_to_use_fit_the_listing_together(
        self, skill: SkillFile
    ) -> None:
        assert len(skill.description) + len(skill.when_to_use) <= self.LISTING_CAP


class TestInvocationOfTheSkills:
    HUMAN_ONLY = frozenset({'crashout', 'prune-ticket', 'stick-the-landing'})
    NEVER_TYPED = frozenset({'agent-debugging', 'prompting-subagents'})

    def test_exactly_the_skills_that_vent_push_or_close_refuse_model_invocation(self) -> None:
        assert {skill.name for skill in SKILL_FILES if skill.human_only} == self.HUMAN_ONLY

    def test_exactly_the_skills_nobody_types_are_hidden_from_the_user(self) -> None:
        hidden = {skill.name for skill in SKILL_FILES if skill.hidden_from_the_user}

        assert hidden == self.NEVER_TYPED


class TestAllowedToolsOfTheSkills:
    REGISTERED = frozenset(
        f'mcp__plugin_mightymodels_{SERVER_NAME}__{tool.__name__}' for tool in TOOLS
    )

    @EVERY_SKILL
    def test_every_state_tool_pre_approved_is_one_the_server_registers(
        self, skill: SkillFile
    ) -> None:
        state_tools = [tool for tool in skill.allowed_tools if tool != QUESTION_TOOL]

        assert [tool for tool in state_tools if tool not in self.REGISTERED] == []

    @EVERY_SKILL
    def test_every_state_tool_the_body_names_is_pre_approved(self, skill: SkillFile) -> None:
        named = STATE_TOOL.findall(skill.body)

        assert [tool for tool in named if tool not in skill.allowed_tools] == []

    @EVERY_SKILL
    def test_the_question_tool_is_pre_approved_exactly_when_the_body_names_it(
        self, skill: SkillFile
    ) -> None:
        assert (QUESTION_TOOL in skill.allowed_tools) == (QUESTION_TOOL in skill.body)


class TestArgumentsOfTheSkills:
    @EVERY_SKILL
    def test_the_body_reads_the_arguments_exactly_when_the_frontmatter_hints_at_them(
        self, skill: SkillFile
    ) -> None:
        assert (ARGUMENTS in skill.body) == ('argument-hint' in skill.keys)


class TestKeysOfTheSkills:
    SHARED = frozenset({'name', 'description', 'when_to_use'})
    PRE_APPROVING = SHARED.union({'allowed-tools'})
    TAKING_AN_ARGUMENT = PRE_APPROVING.union({'argument-hint'})
    HUMAN_ONLY = TAKING_AN_ARGUMENT.union({'disable-model-invocation'})
    KEYS = MappingProxyType(
        {
            'agent-debugging': PRE_APPROVING.union({'user-invocable'}),
            'agents-assemble': TAKING_AN_ARGUMENT,
            'ask-an-adult': PRE_APPROVING,
            'baton-pass': TAKING_AN_ARGUMENT,
            'crashout': HUMAN_ONLY,
            'cross-examine': PRE_APPROVING,
            'game-plan': TAKING_AN_ARGUMENT,
            'lets-investigate': TAKING_AN_ARGUMENT,
            'one-shot': TAKING_AN_ARGUMENT,
            'open-ticket': TAKING_AN_ARGUMENT,
            'prompting-subagents': SHARED.union({'user-invocable'}),
            'prune-ticket': HUMAN_ONLY,
            'review-circus': TAKING_AN_ARGUMENT,
            'stick-the-landing': HUMAN_ONLY,
            'what-we-know': TAKING_AN_ARGUMENT,
            'whats-broken': TAKING_AN_ARGUMENT,
        }
    )

    def test_every_skill_directory_has_its_keys_pinned(self) -> None:
        assert {skill.name for skill in SKILL_FILES} == set(self.KEYS)

    @EVERY_SKILL
    def test_the_frontmatter_holds_exactly_the_keys_pinned_for_the_skill(
        self, skill: SkillFile
    ) -> None:
        assert skill.keys == self.KEYS[skill.name]

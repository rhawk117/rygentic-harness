"""Each skill's frontmatter says when to use it, who may start it and which tools it pre-approves.

A skill that takes an argument reads it in its body as the text the user wrote after the skill
name, and no skill holds a key but the ones pinned here.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import pytest
from mightymodels.server import SERVER_NAME, TOOLS

SKILLS = Path(__file__).parent.parent.joinpath('skills')
FRONTMATTER = re.compile(r'\A---\n(?P<head>.*?)\n---\n(?P<body>.*)\Z', re.DOTALL)
FIELD = re.compile(r'^(?P<key>[\w-]+):(?P<value>.*(?:\n[ \t]+.*)*)$', re.MULTILINE)
LISTED_TOOL = re.compile(r'^[ \t]+- (?P<name>\S+)$', re.MULTILINE)
STATE_TOOL = re.compile(rf'\b{SERVER_NAME}/\w+')
QUESTION_TOOL = 'ask_user'
ARGUMENT = re.compile(r'^\*\*Argument:\*\*(?P<paragraph>.*?)\n\n', re.DOTALL | re.MULTILINE)


@dataclass(slots=True, kw_only=True, frozen=True)
class SkillFile:
    name: str
    keys: frozenset[str]
    description: str
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
    def test_the_description_fits_the_listing(self, skill: SkillFile) -> None:
        assert len(skill.description) <= self.LISTING_CAP


class TestInvocationOfTheSkills:
    HUMAN_ONLY = frozenset({'crashout', 'prune-ticket', 'stick-the-landing'})
    NEVER_TYPED = frozenset(
        {'agent-debugging', 'becoming-merge-vader', 'becoming-uncle-bob', 'prompting-subagents'}
    )

    def test_exactly_the_skills_that_vent_push_or_close_refuse_model_invocation(self) -> None:
        assert {skill.name for skill in SKILL_FILES if skill.human_only} == self.HUMAN_ONLY

    def test_exactly_the_skills_nobody_types_are_hidden_from_the_user(self) -> None:
        hidden = {skill.name for skill in SKILL_FILES if skill.hidden_from_the_user}

        assert hidden == self.NEVER_TYPED


class TestAllowedToolsOfTheSkills:
    REGISTERED = frozenset(f'{SERVER_NAME}/{tool.__name__}' for tool in TOOLS)

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
    TAKING_AN_ARGUMENT = frozenset(
        {
            'agents-assemble',
            'baton-pass',
            'break-it-down',
            'crashout',
            'game-plan',
            'lets-investigate',
            'one-shot',
            'open-ticket',
            'prune-ticket',
            'review-circus',
            'stick-the-landing',
            'what-we-know',
            'whats-broken',
        }
    )

    def test_exactly_the_skills_that_take_an_argument_read_one_in_the_body(self) -> None:
        reading = {skill.name for skill in SKILL_FILES if ARGUMENT.search(skill.body)}

        assert reading == self.TAKING_AN_ARGUMENT

    @EVERY_SKILL
    def test_the_argument_is_the_text_the_user_wrote_after_the_skill_name(
        self, skill: SkillFile
    ) -> None:
        found = ARGUMENT.search(skill.body)
        paragraph = '' if found is None else folded(found['paragraph'])

        assert (found is None) or ('the text the user wrote after' in paragraph)


class TestKeysOfTheSkills:
    SHARED = frozenset({'name', 'description'})
    PRE_APPROVING = SHARED.union({'allowed-tools'})
    HUMAN_ONLY = PRE_APPROVING.union({'disable-model-invocation'})
    KEYS = MappingProxyType(
        {
            'agent-debugging': PRE_APPROVING.union({'user-invocable'}),
            'agents-assemble': PRE_APPROVING,
            'ask-an-adult': PRE_APPROVING,
            'baton-pass': PRE_APPROVING,
            'break-it-down': PRE_APPROVING,
            'becoming-merge-vader': SHARED.union({'user-invocable'}),
            'becoming-uncle-bob': SHARED.union({'user-invocable'}),
            'crashout': HUMAN_ONLY,
            'cross-examine': PRE_APPROVING,
            'game-plan': PRE_APPROVING,
            'lets-investigate': PRE_APPROVING,
            'one-shot': PRE_APPROVING,
            'open-ticket': PRE_APPROVING,
            'prompting-subagents': SHARED.union({'user-invocable'}),
            'prune-ticket': HUMAN_ONLY,
            'review-circus': PRE_APPROVING,
            'stick-the-landing': HUMAN_ONLY,
            'what-we-know': PRE_APPROVING,
            'whats-broken': PRE_APPROVING,
        }
    )

    def test_every_skill_directory_has_its_keys_pinned(self) -> None:
        assert {skill.name for skill in SKILL_FILES} == set(self.KEYS)

    @EVERY_SKILL
    def test_the_frontmatter_holds_exactly_the_keys_pinned_for_the_skill(
        self, skill: SkillFile
    ) -> None:
        assert skill.keys == self.KEYS[skill.name]

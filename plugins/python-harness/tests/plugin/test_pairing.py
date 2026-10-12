"""Which skill dispatches which agent, and that each dispatch block matches the agent it names."""

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from test_tool_references import (
    AGENT_FILES,
    PLUGIN_ROOT,
    SKILL_FILES,
    document_parts,
    line_entries,
    list_entries,
    skill_name,
)

AGENT_PREFIX = 'python-harness:'
AGENT_REFERENCE = re.compile(rf'{AGENT_PREFIX}(?P<name>[a-z][\w-]*)')
DISPATCH_SECTION = re.compile(r'^<dispatch>\n(?P<text>.*?)^</dispatch>$', re.MULTILINE | re.DOTALL)
DISPATCH_FIELD = re.compile(r'^- (?P<key>agent|model|effort|tools): (?P<value>.+)$', re.MULTILINE)

PAIRING = {
    'pylens': ('tactical-slop-review', ()),
    'test-engineer': ('design-tests', ('data-engineering', 'automate-task')),
    'reviewer': (
        'build-web-service',
        ('data-engineering', 'data-analysis', 'automate-task'),
    ),
    'pep-talk': (
        'automate-task',
        ('data-engineering', 'data-analysis', 'design-tests', 'build-web-service'),
    ),
}
DISPATCHERS = {agent: {driver, *extras} for agent, (driver, extras) in PAIRING.items()}
NO_DISPATCH = ('enterprise-design', 'design-persistence')
AGENT_TOOL = 'Agent'


@dataclass(frozen=True, kw_only=True)
class DispatchBlock:
    agent: str
    model: str
    effort: str | None
    tools: tuple[str, ...]


def parse_dispatch(section: str) -> list[DispatchBlock]:
    fields: list[dict[str, str]] = []
    for found in DISPATCH_FIELD.finditer(section):
        value = found['value'].replace('`', '')
        if found['key'] == 'agent':
            fields.append({})
        fields[-1][found['key']] = value.removeprefix(AGENT_PREFIX)
    return [
        DispatchBlock(
            agent=block['agent'],
            model=block['model'],
            effort=block.get('effort'),
            tools=tuple(block['tools'].split(', ')),
        )
        for block in fields
    ]


def dispatch_blocks(body: str) -> list[DispatchBlock]:
    found = DISPATCH_SECTION.search(body)
    return parse_dispatch(found['text']) if found else []


def declared_block(agent: str, frontmatter: str) -> DispatchBlock:
    efforts = line_entries(frontmatter, 'effort')
    return DispatchBlock(
        agent=agent,
        model=line_entries(frontmatter, 'model')[0],
        effort=efforts[0] if efforts else None,
        tools=tuple(line_entries(frontmatter, 'tools')),
    )


def agent_block(agent: str) -> DispatchBlock:
    frontmatter = document_parts(PLUGIN_ROOT.joinpath('agents', f'{agent}.md'))[0]
    return declared_block(agent, frontmatter)


def named_agents(body: str) -> set[str]:
    return {found['name'] for found in AGENT_REFERENCE.finditer(body)}


def dispatched_by(skill: str) -> set[str]:
    return {agent for agent, skills in DISPATCHERS.items() if skill in skills}


def reviewer_dispatch_sentences(body: str) -> list[str]:
    prose = ' '.join(DISPATCH_SECTION.sub('', body).split())
    return [
        sentence
        for sentence in re.split(r'(?<=\.) ', prose)
        if f'{AGENT_PREFIX}reviewer' in sentence
    ]


class TestPairing:
    def test_the_skills_that_dispatch_nothing_are_the_ones_outside_every_pairing(self) -> None:
        paired = set().union(*DISPATCHERS.values())
        every = {skill_name(document) for document in SKILL_FILES}

        assert every - paired == set(NO_DISPATCH)

    @pytest.mark.parametrize('agent', sorted(PAIRING))
    def test_the_skills_naming_an_agent_are_its_driver_and_its_extras(self, agent: str) -> None:
        naming = {
            skill_name(document)
            for document in SKILL_FILES
            if agent in named_agents(document_parts(document)[1])
        }

        assert naming == DISPATCHERS[agent]

    def test_every_agent_a_skill_names_is_one_of_the_agent_files(self) -> None:
        named = {
            name for document in SKILL_FILES for name in named_agents(document_parts(document)[1])
        }

        assert (named, {path.stem for path in AGENT_FILES}) == (set(PAIRING), set(PAIRING))

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_a_skill_carries_the_agent_tool_exactly_when_it_dispatches(
        self, document: Path
    ) -> None:
        frontmatter, body = document_parts(document)
        allowed = list_entries(frontmatter, 'allowed-tools')
        expected = dispatched_by(skill_name(document))

        assert (AGENT_TOOL in allowed, named_agents(body)) == (bool(expected), expected)


class TestReviewerDispatch:
    @pytest.mark.parametrize('skill', sorted(DISPATCHERS['reviewer']))
    def test_the_sentence_dispatching_the_reviewer_names_a_contract_and_acceptance_criteria(
        self, skill: str
    ) -> None:
        document = PLUGIN_ROOT.joinpath('skills', skill, 'SKILL.md')

        sentences = reviewer_dispatch_sentences(document_parts(document)[1])

        assert [('contract' in s, 'acceptance criteria' in s) for s in sentences] == [(True, True)]


class TestDispatchBlocks:
    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_each_dispatch_block_repeats_the_agent_it_names(self, document: Path) -> None:
        blocks = dispatch_blocks(document_parts(document)[1])

        assert blocks == [agent_block(block.agent) for block in blocks]

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_a_skill_holds_one_dispatch_block_for_each_agent_it_dispatches(
        self, document: Path
    ) -> None:
        blocks = dispatch_blocks(document_parts(document)[1])

        assert sorted(block.agent for block in blocks) == sorted(
            dispatched_by(skill_name(document))
        )


class TestDispatchParser:
    @pytest.mark.parametrize(
        ('model', 'effort', 'tools', 'matches'),
        [
            pytest.param('haiku', '- effort: low\n', 'Read, Grep, `x`', True, id='repeats-it'),
            pytest.param('sonnet', '- effort: low\n', 'Read, Grep, `x`', False, id='wrong-model'),
            pytest.param('haiku', '- effort: low\n', 'Read, Grep', False, id='missing-tool'),
            pytest.param('haiku', '', 'Read, Grep, `x`', False, id='missing-effort'),
            pytest.param(
                'haiku', '- effort: low\n', '`x`, Read, Grep', False, id='tools-reordered'
            ),
        ],
    )
    def test_a_block_is_equal_to_the_declaration_only_when_it_repeats_every_field(
        self, model: str, effort: str, tools: str, matches: bool
    ) -> None:
        frontmatter = 'name: lens\nmodel: haiku\neffort: low\ntools: Read, Grep, x\n'
        section = f'Intro.\n\n- agent: `python-harness:lens`\n- model: {model}\n{effort}'
        section += f'- tools: {tools}\n\nOutro.\n'

        assert (parse_dispatch(section) == [declared_block('lens', frontmatter)]) is matches

    def test_a_dispatch_section_that_names_no_agent_holds_no_block(self) -> None:
        body = '<dispatch>\nThis skill dispatches no agent.\n</dispatch>\n'

        assert dispatch_blocks(body) == []

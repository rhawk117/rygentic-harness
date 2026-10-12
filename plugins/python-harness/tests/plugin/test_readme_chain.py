"""The plugin README's skill chain table against the inputs and handoff of each skill."""

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from test_tool_references import PLUGIN_ROOT, SKILL_FILES, document_parts, skill_name

README = PLUGIN_ROOT.joinpath('README.md')
CHAIN_SECTION = re.compile(
    r'^## The skill chain\n(?P<text>.*?)(?=^## |\Z)', re.MULTILINE | re.DOTALL
)
CHAIN_COLUMNS = ['Skill', 'Track', 'Receives from', 'Hands to']
SKILL_LIST = re.compile(r'none|`[a-z-]+`(?:, `[a-z-]+`)*')
BACKTICKED = re.compile(r'`([a-z-]+)`')
SKILLS = frozenset(skill_name(document) for document in SKILL_FILES)
NONE_CELL = 'none'


@dataclass(frozen=True, kw_only=True)
class ChainRow:
    track: str
    receives: str
    hands: str


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def chain_table() -> list[list[str]]:
    section = CHAIN_SECTION.search(README.read_text(encoding='utf-8'))
    assert section is not None
    lines = [line for line in section['text'].splitlines() if line.startswith('|')]
    return [table_cells(line) for line in lines]


def chain_rows() -> dict[str, ChainRow]:
    _, _, *rows = chain_table()
    return {
        skill.strip('`'): ChainRow(track=track, receives=receives, hands=hands)
        for skill, track, receives, hands in rows
    }


def cell_skills(cell: str) -> frozenset[str]:
    return frozenset(BACKTICKED.findall(cell))


def section_text(body: str, tag: str) -> str:
    found = re.search(rf'^<{tag}>\n(?P<text>.*?)^</{tag}>$', body, re.MULTILINE | re.DOTALL)
    assert found is not None
    return found['text']


def named_skills(text: str, own: str) -> frozenset[str]:
    return frozenset(
        name for name in SKILLS - {own} if re.search(rf'(?<![\w-]){re.escape(name)}(?![\w-])', text)
    )


def chain_mismatch(skill: str, row: ChainRow, body: str) -> tuple[set[str], set[str]]:
    received = named_skills(section_text(body, 'inputs'), skill) ^ cell_skills(row.receives)
    handed = named_skills(section_text(body, 'handoff'), skill) ^ cell_skills(row.hands)
    return set(received), set(handed)


class TestChainTable:
    def test_the_table_has_the_four_columns(self) -> None:
        assert chain_table()[0] == CHAIN_COLUMNS

    def test_the_table_has_one_row_for_each_skill_directory(self) -> None:
        rows = chain_rows()

        assert (len(rows), set(rows)) == (8, set(SKILLS))

    def test_every_list_cell_is_none_or_backticked_skill_names(self) -> None:
        cells = [cell for row in chain_rows().values() for cell in (row.receives, row.hands)]

        assert [cell for cell in cells if not SKILL_LIST.fullmatch(cell)] == []

    def test_every_skill_named_in_a_cell_is_a_skill_directory(self) -> None:
        cells = [cell for row in chain_rows().values() for cell in (row.receives, row.hands)]

        assert set().union(*map(cell_skills, cells)) <= SKILLS


class TestChainAgainstSkills:
    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_the_row_names_the_skills_the_inputs_and_handoff_name(self, document: Path) -> None:
        skill = skill_name(document)

        mismatch = chain_mismatch(skill, chain_rows()[skill], document_parts(document)[1])

        assert mismatch == (set(), set())

    def test_a_row_that_names_the_wrong_skill_is_reported(self) -> None:
        skill = 'design-tests'
        document = PLUGIN_ROOT.joinpath('skills', skill, 'SKILL.md')
        row = ChainRow(track='service', receives='`enterprise-design`', hands=NONE_CELL)

        mismatch = chain_mismatch(skill, row, document_parts(document)[1])

        assert mismatch == ({'design-persistence', 'enterprise-design'}, {'tactical-slop-review'})

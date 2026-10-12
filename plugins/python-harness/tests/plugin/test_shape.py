"""The one layout every skill and every agent of the plugin follows."""

import re
from pathlib import Path

import pytest
from test_tool_references import AGENT_FILES, SKILL_FILES, document_parts, list_entries

CODE_FENCE = re.compile(r'^```.*?^```$', re.MULTILINE | re.DOTALL)
TAG_LINE = re.compile(r'^<(?P<closing>/?)(?P<name>[a-z_]+)>$', re.MULTILINE)
FRONTMATTER_KEY = re.compile(r'^(?P<key>[A-Za-z][\w-]*):', re.MULTILINE)

SKILL_SECTIONS = ('purpose', 'inputs', 'workflow', 'dispatch', 'gates', 'output', 'handoff')
AGENT_SECTIONS = (
    'role',
    'context',
    'inputs',
    'workflow',
    'constraints',
    'output_format',
    'verification',
)
SKILL_KEYS = ['name', 'description', 'argument-hint', 'paths', 'allowed-tools']
SKILL_OPTIONAL_KEY = 'disallowed-tools'
AGENT_KEYS = [
    'name',
    'description',
    'tools',
    'disallowedTools',
    'skills',
    'model',
    'effort',
    'maxTurns',
    'omitClaudeMd',
    'color',
]
AGENT_REQUIRED_KEYS = {'name', 'description', 'tools', 'model', 'maxTurns', 'color'}
CODE_PATHS = ['**/*.py', '**/*.pyi', '**/pyproject.toml']
DATA_PATHS = [*CODE_PATHS, '**/*.csv', '**/*.parquet', '**/*.ipynb']
DATA_SKILLS = frozenset({'data-analysis', 'data-engineering'})


def sections(*names: str) -> list[str]:
    return [tag for name in names for tag in (f'<{name}>', f'</{name}>')]


def top_level_tags(body: str) -> list[str]:
    tags: list[str] = []
    open_section = None
    for found in TAG_LINE.finditer(CODE_FENCE.sub('', body)):
        if open_section in (None, found['name']):
            tags.append(f'<{found["closing"]}{found["name"]}>')
            open_section = None if found['closing'] else found['name']
    return tags


def frontmatter_keys(frontmatter: str) -> list[str]:
    return FRONTMATTER_KEY.findall(frontmatter)


def skill_paths(frontmatter: str) -> list[str]:
    return [entry.strip('"') for entry in list_entries(frontmatter, 'paths')]


def skill_id(document: Path) -> str:
    return document.parent.name


class TestSkillShape:
    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_id)
    def test_a_skill_body_holds_the_seven_sections_once_each_in_order(self, document: Path) -> None:
        body = document_parts(document)[1]

        assert top_level_tags(body) == sections(*SKILL_SECTIONS)

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_id)
    def test_a_skill_frontmatter_holds_its_keys_in_order_and_no_other(self, document: Path) -> None:
        keys = frontmatter_keys(document_parts(document)[0])

        assert keys in (SKILL_KEYS, [*SKILL_KEYS, SKILL_OPTIONAL_KEY])

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_id)
    def test_a_skill_is_named_for_its_directory(self, document: Path) -> None:
        frontmatter = document_parts(document)[0]

        assert f'name: {skill_id(document)}' in frontmatter.splitlines()

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_id)
    def test_a_skill_watches_the_longer_path_list_only_when_it_works_on_data(
        self, document: Path
    ) -> None:
        expected = DATA_PATHS if skill_id(document) in DATA_SKILLS else CODE_PATHS

        assert skill_paths(document_parts(document)[0]) == expected


class TestAgentShape:
    @pytest.mark.parametrize('document', AGENT_FILES, ids=lambda path: path.stem)
    def test_an_agent_body_holds_the_seven_sections_once_each_in_order(
        self, document: Path
    ) -> None:
        body = document_parts(document)[1]

        assert top_level_tags(body) == sections(*AGENT_SECTIONS)

    @pytest.mark.parametrize('document', AGENT_FILES, ids=lambda path: path.stem)
    def test_an_agent_frontmatter_keys_are_an_ordered_subset_with_the_required_ones(
        self, document: Path
    ) -> None:
        keys = frontmatter_keys(document_parts(document)[0])

        assert (keys, set(keys) >= AGENT_REQUIRED_KEYS) == (
            [key for key in AGENT_KEYS if key in keys],
            True,
        )

    @pytest.mark.parametrize('document', AGENT_FILES, ids=lambda path: path.stem)
    def test_an_agent_is_named_for_its_file(self, document: Path) -> None:
        frontmatter = document_parts(document)[0]

        assert f'name: {document.stem}' in frontmatter.splitlines()


class TestSectionParser:
    @pytest.mark.parametrize(
        ('body', 'expected'),
        [
            pytest.param(
                '<a>\ntext\n</a>\n\n<b>\n</b>\n', sections('a', 'b'), id='sections-in-order'
            ),
            pytest.param(
                '<a>\n<x>\n</x>\n</a>\n', sections('a'), id='nested-tags-are-not-sections'
            ),
            pytest.param(
                '<a>\n```\n<b>\n```\n</a>\n', sections('a'), id='tags-in-a-code-fence-are-skipped'
            ),
            pytest.param('<a>\n</a>\n<a>\n</a>\n', sections('a', 'a'), id='a-repeat-is-reported'),
            pytest.param('<a>\ntext\n', ['<a>'], id='an-unclosed-section-is-reported'),
        ],
    )
    def test_top_level_tags_lists_the_sections_the_body_opens_and_closes(
        self, body: str, expected: list[str]
    ) -> None:
        assert top_level_tags(body) == expected

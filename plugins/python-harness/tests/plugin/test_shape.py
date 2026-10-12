"""The one layout every skill and every agent of the plugin follows."""

import re
from itertools import takewhile
from pathlib import Path

import pytest
from test_tool_references import (
    AGENT_FILES,
    PLUGIN_ROOT,
    SKILL_DISALLOWED,
    SKILL_FILES,
    document_parts,
    list_entries,
    skill_name,
)

CODE_FENCE = re.compile(r'^```.*?^```$', re.MULTILINE | re.DOTALL)
TAG_LINE = re.compile(r'^<(?P<closing>/?)(?P<name>[a-z_]+)>$', re.MULTILINE)
FRONTMATTER_KEY = re.compile(r'^(?P<key>[A-Za-z][\w-]*):', re.MULTILINE)
PARENTHESISED = re.compile(r'\((?P<name>[^)]*)\)')
TRIGGER_REQUEST = re.compile(r'^- request: "(?P<request>.+)"$', re.MULTILINE)
TRIGGER_SET = PLUGIN_ROOT.joinpath('tuning', 'trigger-set.yml')

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
SKILL_KEYS = ['name', 'description', 'when_to_use', 'argument-hint', 'paths', 'allowed-tools']
SKILL_OPTIONAL_KEY = 'disallowed-tools'
SKILL_NAMES = frozenset(SKILL_DISALLOWED)
TRIGGER_KEYS = ('description', 'when_to_use')
DESCRIPTION_LIMIT = 400
LISTING_LIMIT = 1536
WRAP_COLUMN = 100
PATTERN = (
    'name: design-tests\n'
    'description: >-\n'
    '  Designs the tests that prove a contract and hands the test files on.\n'
    'when_to_use: >-\n'
    '  Use when tests are brittle or the user asks "what would prove this".\n'
    '  Not for deciding the contract (enterprise-design).\n'
    'argument-hint: "[behavior to test]"\n'
    'paths:\n'
    '  - "**/*.py"\n'
    'allowed-tools:\n'
    '  - Read\n'
)
PADDING = f'  {"padding " * 11}padded.\n'
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


def block_lines(frontmatter: str, key: str) -> list[str]:
    lines = frontmatter.splitlines()
    if f'{key}: >-' not in lines:
        return []
    following = lines[lines.index(f'{key}: >-') + 1 :]
    return list(takewhile(lambda line: line.startswith('  '), following))


def folded(frontmatter: str, key: str) -> str:
    return ' '.join(line.strip() for line in block_lines(frontmatter, key))


def broken_rules(frontmatter: str, name: str) -> list[str]:
    description = folded(frontmatter, 'description')
    when_to_use = folded(frontmatter, 'when_to_use')
    wrapped = [line for key in TRIGGER_KEYS for line in block_lines(frontmatter, key)]
    closing = when_to_use.rpartition('. ')[2]
    neighbours = set(PARENTHESISED.findall(closing))
    held = {
        'keys': frontmatter_keys(frontmatter) in (SKILL_KEYS, [*SKILL_KEYS, SKILL_OPTIONAL_KEY]),
        'folded-blocks': all(f'{key}: >-' in frontmatter.splitlines() for key in TRIGGER_KEYS),
        'wrapped': all(len(line) <= WRAP_COLUMN for line in wrapped),
        'description-opening': bool(description) and not description.startswith('Use when'),
        'description-length': len(description) <= DESCRIPTION_LIMIT,
        'when-to-use-opening': when_to_use.startswith('Use when '),
        'not-for-closing': closing.startswith('Not for ') and closing.endswith('.'),
        'neighbour-named': bool(neighbours) and neighbours <= SKILL_NAMES - {name},
        'listing-length': len(description) + len(when_to_use) <= LISTING_LIMIT,
        'angle-brackets': not set('<>') & set(description + when_to_use),
    }
    return [rule for rule, holds in held.items() if not holds]


def trigger_requests() -> list[str]:
    return TRIGGER_REQUEST.findall(TRIGGER_SET.read_text(encoding='utf-8'))


def copied_requests(frontmatter: str, requests: list[str]) -> list[str]:
    text = ' '.join(folded(frontmatter, key) for key in TRIGGER_KEYS)
    return [request for request in requests if request in text]


class TestSkillShape:
    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_a_skill_body_holds_the_seven_sections_once_each_in_order(self, document: Path) -> None:
        body = document_parts(document)[1]

        assert top_level_tags(body) == sections(*SKILL_SECTIONS)

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_a_skill_frontmatter_holds_its_keys_in_order_and_no_other(self, document: Path) -> None:
        keys = frontmatter_keys(document_parts(document)[0])

        assert keys in (SKILL_KEYS, [*SKILL_KEYS, SKILL_OPTIONAL_KEY])

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_a_skill_is_named_for_its_directory(self, document: Path) -> None:
        frontmatter = document_parts(document)[0]

        assert f'name: {skill_name(document)}' in frontmatter.splitlines()

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_a_skill_watches_the_longer_path_list_only_when_it_works_on_data(
        self, document: Path
    ) -> None:
        expected = DATA_PATHS if skill_name(document) in DATA_SKILLS else CODE_PATHS

        assert skill_paths(document_parts(document)[0]) == expected


class TestSkillTriggerText:
    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_a_skill_description_and_when_to_use_follow_the_one_pattern(
        self, document: Path
    ) -> None:
        frontmatter = document_parts(document)[0]

        assert broken_rules(frontmatter, skill_name(document)) == []

    @pytest.mark.parametrize(
        ('frontmatter', 'expected'),
        [
            pytest.param(PATTERN, [], id='the-pattern'),
            pytest.param(f'{PATTERN}model: sonnet\n', ['keys'], id='a-key-outside-the-list'),
            pytest.param(
                PATTERN.replace('paths:\n  - "**/*.py"\n', '') + 'paths:\n  - "**/*.py"\n',
                ['keys'],
                id='the-keys-out-of-order',
            ),
            pytest.param(
                PATTERN.replace('description: >-\n  Designs', 'description: Designs'),
                ['folded-blocks', 'description-opening'],
                id='a-description-on-its-key-line',
            ),
            pytest.param(
                PATTERN.replace('when_to_use: >-', 'when_to_use: >'),
                ['folded-blocks', 'when-to-use-opening', 'not-for-closing', 'neighbour-named'],
                id='a-when-to-use-that-keeps-its-newline',
            ),
            pytest.param(
                PATTERN.replace('contract and', f'contract {"and " * 10}and'),
                ['wrapped'],
                id='a-line-past-100-columns',
            ),
            pytest.param(
                PATTERN.replace('  Designs the tests', '  Use when designing the tests'),
                ['description-opening'],
                id='a-description-that-says-when',
            ),
            pytest.param(
                PATTERN.replace('when_to_use: >-\n', f'{PADDING * 5}when_to_use: >-\n'),
                ['description-length'],
                id='a-description-past-400-characters',
            ),
            pytest.param(
                PATTERN.replace('  Use when tests', '  When tests'),
                ['when-to-use-opening'],
                id='a-when-to-use-that-opens-otherwise',
            ),
            pytest.param(
                PATTERN.replace('  Not for deciding the contract (enterprise-design).\n', ''),
                ['not-for-closing', 'neighbour-named'],
                id='no-not-for-sentence',
            ),
            pytest.param(
                PATTERN.replace('design).', 'design). It ends otherwise.'),
                ['not-for-closing', 'neighbour-named'],
                id='a-not-for-sentence-that-is-not-last',
            ),
            pytest.param(
                PATTERN.replace('(enterprise-design)', '(design-tests)'),
                ['neighbour-named'],
                id='a-not-for-sentence-naming-the-skill-itself',
            ),
            pytest.param(
                PATTERN.replace('(enterprise-design)', '(design-everything)'),
                ['neighbour-named'],
                id='a-not-for-sentence-naming-no-existing-skill',
            ),
            pytest.param(
                PATTERN.replace(' (enterprise-design)', ''),
                ['neighbour-named'],
                id='a-not-for-sentence-naming-nothing',
            ),
            pytest.param(
                PATTERN.replace('  Not for', f'{PADDING * 16}  Not for'),
                ['listing-length'],
                id='a-pair-past-1536-characters',
            ),
            pytest.param(
                PATTERN.replace('a contract', 'a <contract>'),
                ['angle-brackets'],
                id='an-angle-bracket',
            ),
        ],
    )
    def test_frontmatter_that_breaks_a_rule_is_reported_under_that_rule(
        self, frontmatter: str, expected: list[str]
    ) -> None:
        assert broken_rules(frontmatter, 'design-tests') == expected

    def test_every_request_of_the_trigger_set_is_read(self) -> None:
        text = TRIGGER_SET.read_text(encoding='utf-8')

        requests = trigger_requests()

        assert (bool(requests), len(requests)) == (True, text.count('- request:'))

    @pytest.mark.parametrize('document', SKILL_FILES, ids=skill_name)
    def test_a_skill_copies_no_request_of_the_trigger_set(self, document: Path) -> None:
        frontmatter = document_parts(document)[0]

        assert copied_requests(frontmatter, trigger_requests()) == []

    @pytest.mark.parametrize('replaced', ['a contract', 'tests are brittle'], ids=TRIGGER_KEYS)
    def test_a_request_copied_into_either_text_is_reported(self, replaced: str) -> None:
        requests = ['automate my nightly backup', 'design a schema for orders']
        frontmatter = PATTERN.replace(replaced, requests[1])

        assert copied_requests(frontmatter, requests) == [requests[1]]


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

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st
from mightymodels_plugin.tools.ticket.ticket_file import SubsetError, parse, quoted, with_context


class TestQuoted:
    @given(value=st.text())
    def test_text_is_quoted_as_the_standard_library_writes_it_unescaped(self, value: str) -> None:
        assert quoted(value) == json.dumps(value, ensure_ascii=False)


class TestParse:
    def test_reads_scalars_lists_and_nested_mappings(self) -> None:
        source = (
            '# a ticket\n'
            'task: "retry-queue"   # the slug\n'
            'issue: 42\n'
            'jira:\n'
            'context:\n'
            '  - "a: b"\n'
            '  - plain # trailing\n'
            '\n'
            'handoff-context:\n'
            '  plan-first: true\n'
            '  scope: large\n'
        )

        assert parse(source) == {
            'task': 'retry-queue',
            'issue': 42,
            'jira': None,
            'context': ['a: b', 'plain'],
            'handoff-context': {'plan-first': True, 'scope': 'large'},
        }

    def test_an_empty_file_is_an_empty_mapping(self) -> None:
        assert parse('# nothing yet\n\n') == {}

    @pytest.mark.parametrize(
        ('source', 'number', 'reason'),
        [
            pytest.param('a: 1\n b: 2\n', 2, 'multiple of two spaces', id='odd-indent'),
            pytest.param('  a: 1\n', 1, 'unexpected indentation', id='indented-first-line'),
            pytest.param('a: 1\n    b: 2\n', 2, 'unexpected indentation', id='indent-after-scalar'),
            pytest.param('a:\n  b: 1\n    c: 2\n', 3, 'unexpected indentation', id='too-deep'),
            pytest.param('a: 1\na: 2\n', 2, 'duplicate key a', id='duplicate-key'),
            pytest.param('a:\n  - x\n  b: 1\n', 3, 'mixed list and mapping', id='mixed'),
            pytest.param('a: "open\n', 1, 'unterminated quoted string', id='unterminated'),
            pytest.param('a: "x" y\n', 1, 'unexpected text after the string', id='trailing'),
            pytest.param('a: {b: 1}\n', 1, 'unsupported YAML syntax', id='flow-mapping'),
            pytest.param('a: &anchor\n', 1, 'unsupported YAML syntax', id='anchor'),
            pytest.param('just words\n', 1, 'expected "key: value"', id='no-key'),
            pytest.param('- a\n- b\n', 1, 'the top level must be a mapping', id='top-level-list'),
        ],
    )
    def test_text_outside_the_subset_is_refused_with_its_line(
        self, source: str, number: int, reason: str
    ) -> None:
        with pytest.raises(SubsetError) as error:
            parse(source)

        assert error.value.number == number
        assert reason in error.value.reason


class TestWithContext:
    def test_replaces_the_context_block_between_its_neighbours(self) -> None:
        source = 'task: "t"\ncontext:   # rollup\n  - "old"\n  - "older"\n\nsummary: "s"\n'

        assert with_context(source, ['new']) == ('task: "t"\ncontext:\n  - "new"\n\nsummary: "s"\n')

    def test_appends_the_context_block_when_the_ticket_has_none(self) -> None:
        assert with_context('task: "t"\n', ['new']) == 'task: "t"\ncontext:\n  - "new"\n'

    def test_replaces_a_context_block_that_ends_the_file(self) -> None:
        source = 'task: "t"\ncontext:\n  - "old"\n'

        assert with_context(source, ['a', 'b']) == 'task: "t"\ncontext:\n  - "a"\n  - "b"\n'

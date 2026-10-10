"""The codec's JSON, byte for byte, and the text it refuses to read."""

import msgspec
import pytest
from mightymodels_plugin.core.codec import (
    UnreadableJsonError,
    decode_text,
    encode_compact,
    encode_indented,
)


class Reading(msgspec.Struct, frozen=True, kw_only=True):
    name: str
    ratio: float | None
    distance: float | None
    counts: dict[str, int]
    cycles: list[list[str]]
    approximate: bool


class TestEncodeIndented:
    READING = Reading(
        name='billing',
        ratio=0.333,
        distance=None,
        counts={'python': 3, 'javascript': 1},
        cycles=[['core', 'io'], []],
        approximate=False,
    )
    ENCODED_READING = (
        b'{\n'
        b'  "name": "billing",\n'
        b'  "ratio": 0.333,\n'
        b'  "distance": null,\n'
        b'  "counts": {\n'
        b'    "python": 3,\n'
        b'    "javascript": 1\n'
        b'  },\n'
        b'  "cycles": [\n'
        b'    [\n'
        b'      "core",\n'
        b'      "io"\n'
        b'    ],\n'
        b'    []\n'
        b'  ],\n'
        b'  "approximate": false\n'
        b'}'
    )
    ACCENTED = 'src/café.py'
    ENCODED_ACCENTED = b'"src/caf\xc3\xa9.py"'

    def test_a_struct_is_written_in_field_order_with_two_space_indentation(self) -> None:
        assert encode_indented(self.READING) == self.ENCODED_READING

    def test_a_character_outside_ascii_is_written_as_utf8(self) -> None:
        assert encode_indented(self.ACCENTED) == self.ENCODED_ACCENTED


class TestEncodeCompact:
    ENCODED_DECISION = b'{"zone":{"path":"src/caf\xc3\xa9.py","held":[true,null]},"attempts":2}'

    @pytest.fixture
    def decision(self) -> dict[str, object]:
        return {'zone': {'path': 'src/café.py', 'held': [True, None]}, 'attempts': 2}

    def test_a_nested_mapping_is_written_in_the_order_held_with_nothing_between_tokens(
        self, decision: dict[str, object]
    ) -> None:
        assert encode_compact(decision) == self.ENCODED_DECISION


class TestDecodeText:
    @pytest.mark.parametrize(
        ('text', 'decoded'),
        [
            pytest.param(
                '{"zone": {"path": "src/caf\\u00e9.py"}, "attempts": 2}',
                {'zone': {'path': 'src/café.py'}, 'attempts': 2},
                id='object',
            ),
            pytest.param('[1, 2.5, "three", true, null]', [1, 2.5, 'three', True, None], id='list'),
            pytest.param('7', 7, id='scalar'),
        ],
    )
    def test_a_document_is_read_into_plain_values(self, text: str, decoded: object) -> None:
        assert decode_text(text) == decoded

    @pytest.mark.parametrize(
        'text',
        [
            pytest.param('{"ratio": NaN}', id='nan'),
            pytest.param('{"ratio": Infinity}', id='infinity'),
            pytest.param('{"ratio": 1e400}', id='number-out-of-range'),
            pytest.param('{"name": "\\ud800"}', id='escaped-lone-surrogate'),
            pytest.param('{"name": "\ud800"}', id='raw-lone-surrogate'),
            pytest.param('{} trailing', id='trailing-text'),
            pytest.param('', id='empty'),
        ],
    )
    def test_text_msgspec_refuses_is_raised_as_the_codecs_own_error(self, text: str) -> None:
        with pytest.raises(UnreadableJsonError) as refusal:
            decode_text(text)

        assert isinstance(refusal.value.__cause__, ValueError)

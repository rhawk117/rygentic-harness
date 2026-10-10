"""The codec's indented JSON, byte for byte."""

import msgspec
from mightymodels_plugin.core.codec import encode_indented


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

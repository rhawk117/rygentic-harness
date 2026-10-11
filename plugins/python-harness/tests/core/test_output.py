"""JSON documents from dataclasses, enums, paths and collections."""

import io
import json
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path
from types import MappingProxyType

import pytest
from python_harness.core.output import UnsupportedJsonValueError, to_json_value, write_document


class Colour(StrEnum):
    RED = auto()
    BLUE = auto()


@dataclass(frozen=True, slots=True)
class Leaf:
    path: Path
    colours: frozenset[Colour]


@dataclass(frozen=True, slots=True)
class Branch:
    name: str
    leaves: tuple[Leaf, ...]
    _hidden: int = 0

    @property
    def leaf_count(self) -> int:
        return len(self.leaves)

    @property
    def _secret(self) -> int:
        return self._hidden


class TestToJsonValue:
    BRANCH = Branch('trunk', (Leaf(Path('a/b.py'), frozenset({Colour.RED, Colour.BLUE})),))
    EXPECTED = MappingProxyType(
        {
            'name': 'trunk',
            'leaves': [{'path': 'a/b.py', 'colours': ['blue', 'red']}],
            'leaf_count': 1,
        }
    )
    COMPACT = (
        '{"name":"trunk","leaves":[{"path":"a/b.py","colours":["blue","red"]}],"leaf_count":1}\n'
    )

    def test_dataclass_document_has_public_fields_and_properties(self) -> None:
        assert to_json_value(self.BRANCH) == self.EXPECTED

    @pytest.mark.parametrize(
        'value',
        [pytest.param(object(), id='plain-object'), pytest.param(Branch, id='class')],
    )
    def test_unsupported_values_are_rejected(self, value: object) -> None:
        with pytest.raises(UnsupportedJsonValueError):
            to_json_value(value)

    def test_write_document_emits_parseable_json(self) -> None:
        stream = io.StringIO()

        write_document(self.BRANCH, stream)

        assert json.loads(stream.getvalue()) == self.EXPECTED

    def test_write_document_is_compact_with_a_trailing_newline(self) -> None:
        stream = io.StringIO()

        write_document(self.BRANCH, stream)

        assert stream.getvalue() == self.COMPACT

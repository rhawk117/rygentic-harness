"""JSON documents built from result values."""

import inspect
import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from functools import singledispatch
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from python_harness.core.errors import PythonHarnessError

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None

COMPACT_SEPARATORS = (',', ':')


class UnsupportedJsonValueError(PythonHarnessError):
    def __init__(self, value: object) -> None:
        super().__init__(f'cannot encode {type(value).__name__} as JSON')
        self.value = value


def is_property(member: object) -> bool:
    return isinstance(member, property)


def public_property_names(cls: type) -> tuple[str, ...]:
    members = inspect.getmembers(cls, is_property)
    return tuple(name for name, _ in members if not name.startswith('_'))


def dataclass_to_json(value: 'DataclassInstance') -> dict[str, JsonValue]:
    names = [item.name for item in fields(value) if not item.name.startswith('_')]
    names.extend(public_property_names(type(value)))
    return {name: to_json_value(getattr(value, name)) for name in names}


@singledispatch
def to_json_value(value: object) -> JsonValue:
    if is_dataclass(value) and not isinstance(value, type):
        return dataclass_to_json(value)
    raise UnsupportedJsonValueError(value)


@to_json_value.register
def scalar_to_json(value: str | int | float | bool | None) -> JsonValue:  # noqa: FBT001  singledispatch dispatches on the positional argument.
    return value


@to_json_value.register
def path_to_json(value: Path) -> JsonValue:
    return value.as_posix()


@to_json_value.register(tuple | list)
def sequence_to_json(value: tuple[object, ...] | list[object]) -> JsonValue:
    return [to_json_value(item) for item in value]


@to_json_value.register(frozenset | set)
def set_to_json(value: frozenset[object] | set[object]) -> JsonValue:
    return sequence_to_json(tuple(sorted(value, key=str)))


@to_json_value.register(Mapping)
def mapping_to_json(value: Mapping[object, object]) -> JsonValue:
    return {str(key): to_json_value(item) for key, item in value.items()}


def write_document(document: object, stream: TextIO) -> None:
    json.dump(to_json_value(document), stream, separators=COMPACT_SEPARATORS)
    stream.write('\n')

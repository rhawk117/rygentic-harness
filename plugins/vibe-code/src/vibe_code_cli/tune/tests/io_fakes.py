import errno
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path
from typing import Self, TypedDict, Unpack

import msgspec
from hypothesis import strategies as st

INT64 = st.integers(min_value=-(2**63), max_value=2**63 - 1)
FINITE_FLOATS = st.floats(allow_nan=False, allow_infinity=False)


class StagingOptions(TypedDict):
    dir: Path
    prefix: str
    suffix: str
    delete: bool
    delete_on_close: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class TornStagingFile:
    path: Path
    kept_bytes: int
    delete: bool

    @property
    def name(self) -> str:
        return str(self.path)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self.delete:
            self.path.unlink(missing_ok=True)

    def write(self, data: bytes) -> int:
        self.path.write_bytes(data[: self.kept_bytes])
        raise OSError(errno.ENOSPC, 'simulated full disk', self.name)


@dataclass(slots=True, kw_only=True, frozen=True)
class TornStagingFiles:
    kept_bytes: int

    def __call__(self, **options: Unpack[StagingOptions]) -> TornStagingFile:
        name = f'{options["prefix"]}torn{options["suffix"]}'
        return TornStagingFile(
            path=options['dir'].joinpath(name),
            kept_bytes=self.kept_bytes,
            delete=options['delete'],
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class FailingRename:
    def __call__(self, target: Path) -> Path:
        raise OSError(errno.EXDEV, 'simulated failed rename', str(target))


class Shade(StrEnum):
    LIGHT = auto()
    DARK = auto()


class Leaf(msgspec.Struct, frozen=True, kw_only=True):
    label: str
    weight: float


class SampleState(msgspec.Struct, frozen=True, kw_only=True):
    name: str
    count: int
    enabled: bool
    shade: Shade
    blob: bytes
    tags: tuple[str, ...]
    scores: dict[str, int]
    leaves: tuple[Leaf, ...]
    parent: Leaf | None = None


class CounterState(msgspec.Struct, frozen=True, kw_only=True):
    value: int


class SamplePacket(msgspec.Struct, frozen=True, kw_only=True):
    packet_id: str
    state: SampleState


class SampleAnswer(msgspec.Struct, frozen=True, kw_only=True):
    approved: bool
    reason: str


LEAVES = st.builds(Leaf, label=st.text(), weight=FINITE_FLOATS)
SAMPLE_STATES = st.builds(
    SampleState,
    name=st.text(),
    count=INT64,
    enabled=st.booleans(),
    shade=st.sampled_from(Shade),
    blob=st.binary(),
    tags=st.lists(st.text(), max_size=4).map(tuple),
    scores=st.dictionaries(st.text(), INT64, max_size=4),
    leaves=st.lists(LEAVES, max_size=4).map(tuple),
    parent=st.none() | LEAVES,
)
VALID_ANSWERS = st.builds(SampleAnswer, approved=st.booleans(), reason=st.text())


@st.composite
def truncated_answers(draw: st.DrawFn) -> bytes:
    encoded = msgspec.json.encode(draw(VALID_ANSWERS))
    return encoded[: draw(st.integers(min_value=0, max_value=len(encoded) - 1))]

import secrets
from collections.abc import Generator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import msgspec

from vibe_code_cli.tune.errors import (
    IncompatibleStateError,
    MalformedAnswerError,
    StateMissingError,
)
from vibe_code_cli.tune.locking import exclusive_lock, write_atomically

RUN_ID_BYTES = 3


class PacketFile(msgspec.Struct, frozen=True, kw_only=True):
    packet_id: str
    path: str


@runtime_checkable
class StateSession[S](Protocol):
    def exists(self) -> bool: ...

    def read(self) -> S: ...

    def commit(self, state: S) -> None: ...


@runtime_checkable
class LoopStore[S](Protocol):
    @property
    def path(self) -> Path: ...

    def read(self) -> S: ...

    def transaction(self) -> AbstractContextManager[StateSession[S]]: ...


@runtime_checkable
class Packet(Protocol):
    @property
    def packet_id(self) -> str: ...


@runtime_checkable
class PacketPublisher[P: Packet](Protocol):
    def publish(self, packets: Sequence[P]) -> tuple[PacketFile, ...]: ...


@runtime_checkable
class RunIdSource(Protocol):
    def new_id(self) -> str: ...


def encode_json(value: object) -> str:
    encoded = msgspec.json.encode(value)
    return msgspec.json.format(encoded, indent=2).decode() + '\n'


def decode_answer[T](packet_id: str, data: bytes, shape: type[T]) -> T:
    try:
        return msgspec.json.decode(data, type=shape)
    except (msgspec.DecodeError, msgspec.ValidationError) as problem:
        raise MalformedAnswerError(packet_id, str(problem)) from None


@dataclass(slots=True, kw_only=True, frozen=True)
class StateCodec[S]:
    state_type: type[S]

    def encode(self, state: S) -> bytes:
        return msgspec.json.format(msgspec.json.encode(state), indent=2)

    def decode(self, data: bytes) -> S:
        return msgspec.json.decode(data, type=self.state_type)


@dataclass(slots=True, kw_only=True, frozen=True)
class JsonStateSession[S]:
    path: Path
    codec: StateCodec[S]

    def exists(self) -> bool:
        return self.path.is_file()

    def read(self) -> S:
        if not self.exists():
            raise StateMissingError(self.path)
        try:
            return self.codec.decode(self.path.read_bytes())
        except (msgspec.ValidationError, msgspec.DecodeError):
            raise IncompatibleStateError(self.path) from None

    def commit(self, state: S) -> None:
        write_atomically(self.path, self.codec.encode(state))


@dataclass(slots=True, kw_only=True, frozen=True)
class JsonLoopStore[S]:
    path: Path
    codec: StateCodec[S]

    @property
    def lock_path(self) -> Path:
        return self.path.with_name(f'.{self.path.name}.lock')

    def read(self) -> S:
        return JsonStateSession(path=self.path, codec=self.codec).read()

    @contextmanager
    def transaction(self) -> Generator[StateSession[S], None, None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with exclusive_lock(self.lock_path):
            yield JsonStateSession(path=self.path, codec=self.codec)


@dataclass(slots=True, kw_only=True, frozen=True)
class FilePacketPublisher[P: Packet]:
    directory: Path

    def publish_one(self, packet: P) -> PacketFile:
        path = self.directory.joinpath(f'{packet.packet_id}.json')
        write_atomically(path, msgspec.json.format(msgspec.json.encode(packet), indent=2))
        return PacketFile(packet_id=packet.packet_id, path=str(path.resolve()))

    def publish(self, packets: Sequence[P]) -> tuple[PacketFile, ...]:
        self.directory.mkdir(parents=True, exist_ok=True)
        return tuple(self.publish_one(packet) for packet in packets)


@dataclass(slots=True, kw_only=True, frozen=True)
class RandomRunIds:
    def new_id(self) -> str:
        return secrets.token_hex(RUN_ID_BYTES)

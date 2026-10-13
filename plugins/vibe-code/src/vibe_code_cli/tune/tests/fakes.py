import re
import threading
from collections.abc import Generator, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path

from vibe_code_cli.tune.domain.state import LoopState
from vibe_code_cli.tune.domain.values import LoopOptions, RoutingOptions, Skill, TriggerExample
from vibe_code_cli.tune.errors import RoutingFailedError, StateMissingError
from vibe_code_cli.tune.repository import StratifiedSplitter, TriggerEntry
from vibe_code_cli.tune.routing import RoutedBatch, Router
from vibe_code_cli.tune.schemas import JudgePacket
from vibe_code_cli.tune.store import PacketFile, StateSession
from vibe_code_cli.tune.wiring import STATE_CODEC

STOPWORDS = frozenset({'a', 'an', 'and', 'for', 'i', 'is', 'my', 'the', 'this', 'to', 'use'})
WORD = re.compile(r'[a-z_]+')
MEMORY_LOCATION = Path('memory:state')
BUILTIN_COMPETITORS = frozenset({'code-review', 'debug'})


def words(text: str) -> frozenset[str]:
    found = (match.group() for match in WORD.finditer(text.lower()))
    return frozenset(found) - STOPWORDS


def overlapping_skills(descriptions: Mapping[str, str], request: str) -> list[str]:
    asked = words(request)
    return sorted(name for name, text in descriptions.items() if words(text) & asked)


@dataclass(slots=True, kw_only=True)
class MemoryLoopStore:
    data: bytes | None = None
    commits: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def path(self) -> Path:
        return MEMORY_LOCATION

    def read(self) -> LoopState:
        return MemoryStateSession(store=self).read()

    @contextmanager
    def transaction(self) -> Generator[StateSession[LoopState], None, None]:
        with self.lock:
            yield MemoryStateSession(store=self)


@dataclass(slots=True, kw_only=True)
class MemoryStateSession:
    store: MemoryLoopStore

    def exists(self) -> bool:
        return self.store.data is not None

    def read(self) -> LoopState:
        if self.store.data is None:
            raise StateMissingError(MEMORY_LOCATION)
        return STATE_CODEC.decode(self.store.data)

    def commit(self, state: LoopState) -> None:
        self.store.data = STATE_CODEC.encode(state)
        self.store.commits += 1


@dataclass(slots=True, kw_only=True)
class MemoryPacketPublisher:
    packets: dict[str, JudgePacket] = field(default_factory=dict)

    def publish(self, packets: Sequence[JudgePacket]) -> tuple[PacketFile, ...]:
        self.packets.update({packet.packet_id: packet for packet in packets})
        return tuple(
            PacketFile(packet_id=packet.packet_id, path=f'memory:{packet.packet_id}')
            for packet in packets
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class MemoryWrite:
    path: Path
    skill: str
    description: str
    written: dict[str, str]

    def commit(self) -> None:
        self.written[self.skill] = self.description


@dataclass(slots=True, kw_only=True)
class MemorySkillRepository:
    libraries: Mapping[Path, tuple[Skill, ...]]
    written: dict[str, str] = field(default_factory=dict)

    def discover(self, locations: Sequence[Path]) -> tuple[Skill, ...]:
        return tuple(skill for location in locations for skill in self.libraries[location])

    def plan_write(self, skill: Skill, description: str) -> MemoryWrite:
        return MemoryWrite(
            path=Path(skill.path),
            skill=skill.name,
            description=description,
            written=self.written,
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class MemoryTriggerSetReader:
    trigger_sets: Mapping[Path, Sequence[TriggerEntry]]

    def read(self, path: Path, options: LoopOptions) -> tuple[TriggerExample, ...]:
        return StratifiedSplitter(options=options).assign(self.trigger_sets[path])


@dataclass(slots=True, kw_only=True)
class SequentialRunIds:
    numbers: Iterator[int] = field(default_factory=count)

    def new_id(self) -> str:
        return f't{next(self.numbers)}'


@dataclass(slots=True, kw_only=True, frozen=True)
class OverlapRouter:
    fail_on: str | None = None

    def failing_request(self, requests: Sequence[str]) -> str | None:
        marker = self.fail_on
        if marker is None:
            return None
        return next((request for request in requests if marker in request), None)

    async def route(self, descriptions: Mapping[str, str], requests: Sequence[str]) -> RoutedBatch:
        if failing := self.failing_request(requests):
            raise RoutingFailedError(failing, 'scripted failure')
        verdicts = [frozenset(overlapping_skills(descriptions, request)) for request in requests]
        return RoutedBatch(verdicts=verdicts, competitors=BUILTIN_COMPETITORS)


@dataclass(slots=True, kw_only=True)
class OverlapRouterFactory:
    fail_on: str | None = None
    built: int = 0

    def build(self, skills: tuple[Skill, ...], options: RoutingOptions) -> Router:
        assert skills
        assert options.concurrency > 0
        self.built += 1
        return OverlapRouter(fail_on=self.fail_on)

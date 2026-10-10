from enum import StrEnum, auto

import msgspec


class Judge(StrEnum):
    CLAUDE_CODE = 'claude-code'
    SUBAGENT = 'subagent'

    @property
    def routed(self) -> bool:
        return self is not Judge.SUBAGENT


class Split(StrEnum):
    TRAIN = auto()
    VALIDATION = auto()


class Stage(StrEnum):
    JUDGING = auto()
    PROPOSING = auto()
    DONE = auto()


class Skill(msgspec.Struct, frozen=True, kw_only=True):
    name: str
    path: str
    description: str
    when_to_use: str = ''


class TriggerExample(msgspec.Struct, frozen=True, kw_only=True):
    request_id: str
    request: str
    expected: frozenset[str]
    split: Split


class RoutingOptions(msgspec.Struct, frozen=True, kw_only=True):
    concurrency: int = 4
    timeout_seconds: float = 240.0
    model: str | None = None


class LoopOptions(msgspec.Struct, frozen=True, kw_only=True):
    judge: Judge = Judge.CLAUDE_CODE
    routing: RoutingOptions = msgspec.field(default_factory=RoutingOptions)
    validation_fraction: float = 0.3
    batch_size: int = 12
    max_rounds: int = 8
    patience: int = 3
    min_gain: float = 0.0
    max_description_chars: int = 1024
    max_listing_chars: int = 1536
    seed: int = 0


class Evaluation(msgspec.Struct, frozen=True, kw_only=True):
    descriptions: dict[str, str]
    verdicts: dict[str, frozenset[str]] = msgspec.field(default_factory=dict)
    tuned_skill: str | None = None


class JudgeRecord(msgspec.Struct, frozen=True, kw_only=True):
    packet_id: str
    request_ids: tuple[str, ...]
    skill_order: tuple[str, ...]


class ProposalRecord(msgspec.Struct, frozen=True, kw_only=True):
    packet_id: str
    skill: str


class RoundResult(msgspec.Struct, frozen=True, kw_only=True):
    number: int
    skill: str
    description: str
    train: float
    validation: float
    accepted: bool

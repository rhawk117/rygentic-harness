"""The one routing table: which model alias and effort each worker runs on.

Every worker but the two reviewers is fixed: it runs on the same model at every scope and a ticket
cannot change it. A reviewer's model comes from the review's depth, and `OVERRIDE_MODEL` is the one
model a single review run may move its heavier-weighted reviewer to.
"""

from collections.abc import Mapping
from enum import StrEnum, auto
from types import MappingProxyType


class Model(StrEnum):
    HAIKU = auto()
    SONNET = auto()
    OPUS = auto()
    FABLE = auto()


class Effort(StrEnum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    XHIGH = auto()
    MAX = auto()


class Scope(StrEnum):
    SM = auto()
    MED = auto()
    LARGE = auto()


class Depth(StrEnum):
    QUICK = auto()
    STANDARD = auto()
    DEEP = auto()


class Worker(StrEnum):
    CODE_SCOUT = 'code-scout'
    WEB_SCOUT = 'web-scout'
    QUALITYLENS = 'qualitylens'
    ENGINEER = 'engineer'
    ARCHITECT = 'architect'
    GITTY_UP = 'gitty-up'
    WINGMAN = 'wingman'
    MERGE_VADER_REVIEWER = 'merge-vader-reviewer'
    UNCLE_BOB_REVIEWER = 'uncle-bob-reviewer'


type ScopeRouting = Mapping[Scope, Model]


def at_every_scope(model: Model) -> ScopeRouting:
    return MappingProxyType(dict.fromkeys(Scope, model))


ROUTING: Mapping[Worker, ScopeRouting] = MappingProxyType(
    {
        Worker.CODE_SCOUT: at_every_scope(Model.HAIKU),
        Worker.WEB_SCOUT: at_every_scope(Model.HAIKU),
        Worker.QUALITYLENS: at_every_scope(Model.HAIKU),
        Worker.ENGINEER: at_every_scope(Model.SONNET),
        Worker.ARCHITECT: at_every_scope(Model.OPUS),
        Worker.GITTY_UP: at_every_scope(Model.HAIKU),
        Worker.WINGMAN: at_every_scope(Model.FABLE),
        Worker.MERGE_VADER_REVIEWER: at_every_scope(Model.OPUS),
        Worker.UNCLE_BOB_REVIEWER: at_every_scope(Model.OPUS),
    }
)
EFFORT: Mapping[Model, Effort] = MappingProxyType(
    {
        Model.HAIKU: Effort.HIGH,
        Model.SONNET: Effort.MEDIUM,
        Model.OPUS: Effort.MEDIUM,
        Model.FABLE: Effort.HIGH,
    }
)
REVIEWER_WORKERS = frozenset({Worker.MERGE_VADER_REVIEWER, Worker.UNCLE_BOB_REVIEWER})
FIXED_WORKERS = frozenset(Worker) - REVIEWER_WORKERS


def models_at(scope: Scope) -> dict[Worker, Model]:
    return {worker: by_scope[scope] for worker, by_scope in ROUTING.items()}


DEPTH_MODELS: Mapping[Depth, Model] = MappingProxyType(
    {Depth.QUICK: Model.SONNET, Depth.STANDARD: Model.OPUS, Depth.DEEP: Model.OPUS}
)
OVERRIDE_MODEL = Model.FABLE
DEFAULT_SCOPE = Scope.MED


def fixed_model(worker: Worker) -> Model:
    return ROUTING[worker][DEFAULT_SCOPE]


def reviewer_model(depth: Depth) -> Model:
    return DEPTH_MODELS[depth]

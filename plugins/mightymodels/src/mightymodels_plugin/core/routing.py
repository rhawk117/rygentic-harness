"""The one routing table: which model alias and effort each worker runs on.

Every worker but the two reviewers is fixed: it runs on the same model at every scope and a ticket
cannot change it. A reviewer's model comes from the review's depth, and `OVERRIDE_MODEL` is the one
model a single review run may move its heavier-weighted reviewer to.

`FOLDERS` names the folder of `agents/` each worker's file is in. Claude Code makes the folder part
of the worker's agent type, `mightymodels:<folder>:<name>`.
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
    FACT_CHECKER = 'fact-checker'
    ENGINEER = 'engineer'
    ARCHITECT = 'architect'
    INTERN = 'intern'
    GITTY_UP = 'gitty-up'
    WINGMAN = 'wingman'
    TERRY_TOOLCHAIN = 'terry-toolchain'
    MERGE_VADER = 'merge-vader'
    UNCLE_BOB = 'uncle-bob'


class Folder(StrEnum):
    REVIEW = auto()
    WORKERS = auto()
    TRIAGE = auto()


FOLDERS: Mapping[Worker, Folder] = MappingProxyType(
    {
        Worker.CODE_SCOUT: Folder.TRIAGE,
        Worker.WEB_SCOUT: Folder.TRIAGE,
        Worker.QUALITYLENS: Folder.REVIEW,
        Worker.FACT_CHECKER: Folder.REVIEW,
        Worker.ENGINEER: Folder.WORKERS,
        Worker.ARCHITECT: Folder.WORKERS,
        Worker.INTERN: Folder.WORKERS,
        Worker.GITTY_UP: Folder.WORKERS,
        Worker.WINGMAN: Folder.TRIAGE,
        Worker.TERRY_TOOLCHAIN: Folder.TRIAGE,
        Worker.MERGE_VADER: Folder.REVIEW,
        Worker.UNCLE_BOB: Folder.REVIEW,
    }
)

type ScopeRouting = Mapping[Scope, Model]


def at_every_scope(model: Model) -> ScopeRouting:
    return MappingProxyType(dict.fromkeys(Scope, model))


ROUTING: Mapping[Worker, ScopeRouting] = MappingProxyType(
    {
        Worker.CODE_SCOUT: at_every_scope(Model.HAIKU),
        Worker.WEB_SCOUT: at_every_scope(Model.HAIKU),
        Worker.QUALITYLENS: at_every_scope(Model.HAIKU),
        Worker.FACT_CHECKER: at_every_scope(Model.HAIKU),
        Worker.ENGINEER: at_every_scope(Model.SONNET),
        Worker.ARCHITECT: at_every_scope(Model.OPUS),
        Worker.INTERN: at_every_scope(Model.HAIKU),
        Worker.GITTY_UP: at_every_scope(Model.HAIKU),
        Worker.WINGMAN: at_every_scope(Model.FABLE),
        Worker.TERRY_TOOLCHAIN: at_every_scope(Model.SONNET),
        Worker.MERGE_VADER: at_every_scope(Model.OPUS),
        Worker.UNCLE_BOB: at_every_scope(Model.OPUS),
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
REVIEWER_WORKERS = frozenset({Worker.MERGE_VADER, Worker.UNCLE_BOB})
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

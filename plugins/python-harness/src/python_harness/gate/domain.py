"""Planned verification commands, how they ran, and what the run left behind."""

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum, auto
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from python_harness.gate.errors import InvalidRuffVersionError
from python_harness.survey.domain import Domain

RUFF_VERSION_OPTION = 'ruff_version'
RUFF_VERSION_VARIABLE = 'PYTHON_HARNESS_RUFF_VERSION'
RUFF_VERSION_PATTERN = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+')


class GateTool(StrEnum):
    RUFF_CHECK = auto()
    RUFF_FORMAT = auto()
    TY = auto()
    PYTEST = auto()


class ConfigKind(StrEnum):
    RUFF = auto()
    TY = auto()


class ConfigSource(StrEnum):
    REPOSITORY = auto()
    FALLBACK = auto()
    DEFAULTS = auto()


@dataclass(frozen=True, slots=True)
class RuffVersion:
    text: str

    def __post_init__(self) -> None:
        if RUFF_VERSION_PATTERN.fullmatch(self.text) is None:
            raise InvalidRuffVersionError(RUFF_VERSION_OPTION, RUFF_VERSION_VARIABLE, self.text)


DEFAULT_RUFF_VERSION = RuffVersion('0.16.9')


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    distribution: str
    arguments: tuple[str, ...]
    config: ConfigKind | None = None
    runs_in_project_environment: bool = False
    required_domain: Domain | None = None
    pinned_version: RuffVersion | None = None


type ToolInvocations = Mapping[GateTool, ToolInvocation]


def default_tool_invocations(ruff_version: RuffVersion = DEFAULT_RUFF_VERSION) -> ToolInvocations:
    return MappingProxyType(
        {
            GateTool.RUFF_CHECK: ToolInvocation(
                'ruff',
                ('ruff', 'check', '--no-fix', '--statistics', '--no-cache'),
                config=ConfigKind.RUFF,
                pinned_version=ruff_version,
            ),
            GateTool.RUFF_FORMAT: ToolInvocation(
                'ruff',
                ('ruff', 'format', '--check', '--no-cache'),
                config=ConfigKind.RUFF,
                pinned_version=ruff_version,
            ),
            GateTool.TY: ToolInvocation(
                'ty',
                ('ty', 'check'),
                config=ConfigKind.TY,
                runs_in_project_environment=True,
            ),
            GateTool.PYTEST: ToolInvocation(
                'pytest',
                ('pytest', '-q', '-p', 'no:cacheprovider'),
                runs_in_project_environment=True,
                required_domain=Domain.PYTEST,
            ),
        }
    )


PYTHON_HARNESS_ENVIRONMENT = frozenset(
    {
        'PYTHONDONTWRITEBYTECODE',
        'UV',
        'VIRTUAL_ENV',
    }
)


COLOUR_FORCING_ENVIRONMENT = frozenset({'CLICOLOR_FORCE', 'FORCE_COLOR'})


def default_child_environment() -> Mapping[str, str]:
    return MappingProxyType({'NO_COLOR': '1', 'PYTHONDONTWRITEBYTECODE': '1'})


def default_launcher_environment() -> Path | None:
    if sys.prefix == sys.base_prefix:
        return None
    return Path(sys.prefix)


@dataclass(frozen=True, slots=True)
class GateOptions:
    fallbacks: Mapping[ConfigKind, Path] = field(default_factory=dict)
    dropped_environment: frozenset[str] = PYTHON_HARNESS_ENVIRONMENT | COLOUR_FORCING_ENVIRONMENT
    launcher_environment: Path | None = field(default_factory=default_launcher_environment)
    child_environment: Mapping[str, str] = field(default_factory=default_child_environment)
    timeout_seconds: float = 600.0
    output_tail_lines: int = 40
    skipped: frozenset[GateTool] = frozenset()
    tools: ToolInvocations = field(default_factory=default_tool_invocations)


@dataclass(frozen=True, slots=True)
class GateInputs:
    declared_distributions: frozenset[str]
    has_uv_lock: bool
    project_configs: frozenset[ConfigKind]
    domains: frozenset[Domain]
    source_roots: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConfigSelection:
    source: ConfigSource
    arguments: tuple[str, ...]


type ConfigArguments = Mapping[ConfigKind, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class Launcher:
    program: str
    arguments: tuple[str, ...] = ()
    pins_version: bool = False


@dataclass(frozen=True, slots=True)
class GateCommand:
    tool: GateTool
    program: str
    arguments: tuple[str, ...]

    @property
    def argv(self) -> tuple[str, ...]:
        return (self.program, *self.arguments)


@dataclass(frozen=True, slots=True)
class ResolvedCommand:
    command: GateCommand
    executable: str

    @property
    def argv(self) -> tuple[str, ...]:
        return (self.executable, *self.command.arguments)


@dataclass(frozen=True, slots=True)
class GatePlan:
    commands: tuple[GateCommand, ...]
    ruff_config_source: ConfigSource
    ty_config_source: ConfigSource


@dataclass(frozen=True, slots=True)
class ProcessSettings:
    root: Path
    environment: Mapping[str, str]
    timeout_seconds: float
    output_tail_lines: int


@dataclass(frozen=True, slots=True)
class Exited:
    exit_code: int
    kind: Literal['exited'] = field(default='exited', init=False)


@dataclass(frozen=True, slots=True)
class TimedOut:
    kind: Literal['timed_out'] = field(default='timed_out', init=False)


type GateOutcome = Exited | TimedOut


@dataclass(frozen=True, slots=True)
class GateResult:
    command: GateCommand
    outcome: GateOutcome
    output_tail: str

    @property
    def timed_out(self) -> bool:
        return isinstance(self.outcome, TimedOut)

    @property
    def passed(self) -> bool:
        return isinstance(self.outcome, Exited) and self.outcome.exit_code == 0


@dataclass(frozen=True, slots=True)
class UntrackedSnapshot:
    prefix: str
    paths: frozenset[str]


@dataclass(frozen=True, slots=True)
class CreatedPaths:
    paths: tuple[str, ...]
    kind: Literal['tracked'] = field(default='tracked', init=False)


@dataclass(frozen=True, slots=True)
class NotTracked:
    kind: Literal['not_tracked'] = field(default='not_tracked', init=False)


type CreationTracking = CreatedPaths | NotTracked
type UntrackedBaseline = UntrackedSnapshot | NotTracked


@dataclass(frozen=True, slots=True)
class GateReport:
    ruff_config_source: ConfigSource
    ty_config_source: ConfigSource
    results: tuple[GateResult, ...]
    created_paths: CreationTracking

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

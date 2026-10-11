"""The project under review: manifest and layout facts, inferred mode and domains."""

from dataclasses import dataclass, field
from enum import StrEnum, auto
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

PYPROJECT = 'pyproject.toml'
RUFF_CONFIG_FILES = ('.ruff.toml', 'ruff.toml')
TY_CONFIG_FILES = ('ty.toml',)
UV_LOCK = 'uv.lock'


class Mode(StrEnum):
    LIBRARY = auto()
    APPLICATION = auto()


class Domain(StrEnum):
    PYTEST = auto()
    HYPOTHESIS = auto()
    SQLALCHEMY = auto()
    FASTAPI = auto()
    MCP = auto()
    PYDANTIC = auto()
    MSGSPEC = auto()
    CLI = auto()
    ASYNCIO = auto()


type DomainMarkers = Mapping[Domain, frozenset[str]]


def default_domain_markers() -> DomainMarkers:
    return MappingProxyType(
        {
            Domain.PYTEST: frozenset({'pytest'}),
            Domain.HYPOTHESIS: frozenset({'hypothesis'}),
            Domain.SQLALCHEMY: frozenset({'sqlalchemy', 'sqlmodel'}),
            Domain.FASTAPI: frozenset({'fastapi'}),
            Domain.MCP: frozenset({'mcp', 'fastmcp'}),
            Domain.PYDANTIC: frozenset({'pydantic', 'pydantic-settings', 'pydantic_settings'}),
            Domain.MSGSPEC: frozenset({'msgspec'}),
            Domain.CLI: frozenset({'argparse', 'click', 'typer'}),
            Domain.ASYNCIO: frozenset({'asyncio', 'anyio'}),
        }
    )


@dataclass(frozen=True, slots=True)
class SurveyOptions:
    domain_markers: DomainMarkers = field(default_factory=default_domain_markers)


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    name: str | None
    requires_python: str | None
    build_backend: str | None
    entry_points: tuple[str, ...]
    classifiers: tuple[str, ...]
    dependencies: tuple[str, ...]
    dev_dependencies: tuple[str, ...]
    optional_dependencies: tuple[str, ...]

    @property
    def declared_distributions(self) -> frozenset[str]:
        return frozenset((*self.dependencies, *self.dev_dependencies))

    def declares(self, distribution: str) -> bool:
        return distribution in self.declared_distributions


NO_MANIFEST = ProjectManifest(
    name=None,
    requires_python=None,
    build_backend=None,
    entry_points=(),
    classifiers=(),
    dependencies=(),
    dev_dependencies=(),
    optional_dependencies=(),
)


@dataclass(frozen=True, slots=True)
class LayoutFacts:
    has_py_typed: bool
    has_dunder_main: bool
    has_src_layout: bool
    has_tests_directory: bool
    has_uv_lock: bool


@dataclass(frozen=True, slots=True)
class ModeInference:
    mode: Mode
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectSurvey:
    root: str
    manifest: ProjectManifest
    layout: LayoutFacts
    mode: ModeInference
    domains: tuple[Domain, ...]
    ruff_config: str | None
    external_packages: tuple[str, ...]
    source_roots: tuple[str, ...]
    ty_config: str | None = None

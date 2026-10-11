"""Root-contained paths and Python file discovery for the project under inspection."""

import subprocess
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from functools import partial
from itertools import chain
from pathlib import Path, PurePosixPath

from python_harness.core.errors import (
    PathOutsideWorkspaceError,
    TargetPathMissingError,
    WorkspaceRootMissingError,
)
from python_harness.core.uv import run_uv_workspace

DEFAULT_EXCLUDED_DIRECTORIES = frozenset(
    {
        '.git',
        '.hg',
        '.mypy_cache',
        '.nox',
        '.pytest_cache',
        '.ruff_cache',
        '.tox',
        '.venv',
        '__pycache__',
        'build',
        'dist',
        'node_modules',
        'venv',
    }
)


@dataclass(frozen=True, slots=True)
class DiscoveryOptions:
    excluded_directories: frozenset[str] = DEFAULT_EXCLUDED_DIRECTORIES
    source_root_names: tuple[str, ...] = ('src',)
    test_directory_names: frozenset[str] = frozenset({'tests', 'test'})
    test_file_prefixes: tuple[str, ...] = ('test_',)
    test_file_suffixes: tuple[str, ...] = ('_test.py',)


@dataclass(frozen=True, slots=True)
class Workspace:
    root: Path
    source_roots: tuple[Path, ...]
    options: DiscoveryOptions = field(default_factory=DiscoveryOptions)
    fallback_diagnostics: tuple[str, ...] = ()

    def resolve(self, relative: str | Path) -> Path:
        candidate = self.root.joinpath(relative).resolve()
        if not candidate.is_relative_to(self.root):
            raise PathOutsideWorkspaceError(candidate, self.root)
        return candidate

    def relative(self, path: Path) -> str:
        return self.resolve(path).relative_to(self.root).as_posix()

    def python_files(self, under: str | Path) -> tuple[Path, ...]:
        base = self.resolve(under)
        if not base.exists():
            raise TargetPathMissingError(base)
        if base.is_file():
            return tuple(path for path in (base,) if path.suffix == '.py')
        excluded = self.options.excluded_directories
        return tuple(sorted(walk_python_files(base, root=self.root, excluded=excluded)))

    def python_files_in(self, paths: Iterable[str]) -> tuple[Path, ...]:
        found = chain.from_iterable(self.python_files(path) for path in paths)
        return tuple(sorted(frozenset(found)))

    def is_test_path(self, path: str) -> bool:
        location = PurePosixPath(path)
        test_directories = self.options.test_directory_names
        in_test_directory = not test_directories.isdisjoint(location.parent.parts)
        return in_test_directory or is_test_file_name(location.name, self.options)


def is_test_file_name(name: str, options: DiscoveryOptions) -> bool:
    prefixed = name.startswith(options.test_file_prefixes)
    return prefixed or name.endswith(options.test_file_suffixes)


def resolves_within(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root)


def walk_python_files(base: Path, *, root: Path, excluded: frozenset[str]) -> Iterator[Path]:
    for directory, subdirectories, filenames in base.walk():
        subdirectories[:] = [name for name in subdirectories if name not in excluded]
        python_names = (name for name in filenames if name.endswith('.py'))
        candidates = (directory.joinpath(name) for name in python_names)
        yield from (path for path in candidates if resolves_within(path, root))


def find_source_roots(root: Path, options: DiscoveryOptions) -> tuple[Path, ...]:
    candidates = (root.joinpath(name) for name in options.source_root_names)
    return tuple(path for path in candidates if path.is_dir())


def discover_uv_members(
    root: Path,
    uv_runner: Callable[[Path], str],
) -> tuple[Path, ...] | str:
    try:
        return tuple(Path(line) for line in uv_runner(root).splitlines() if line)
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TimeoutError,
        subprocess.TimeoutExpired,
    ) as error:
        return f'uv workspace discovery failed: {error}'


def validate_workspace_members(root: Path, members: tuple[Path, ...]) -> tuple[Path, ...] | str:
    if not members:
        return 'uv workspace discovery failed: no workspace members'
    if any(not member.is_absolute() for member in members):
        return 'uv workspace discovery failed: non-absolute member path'
    resolved = tuple(member.resolve() for member in members)
    if any(not member.is_relative_to(root) for member in resolved):
        return 'uv workspace discovery failed: path outside the project root'
    return resolved


def derive_workspace_source_roots(
    members: tuple[Path, ...],
    options: DiscoveryOptions,
) -> tuple[Path, ...]:
    return tuple(
        source_root
        for member in members
        for source_root in (find_source_roots(member, options) or (member,))
    )


def construct_workspace(
    root: Path,
    source_roots: tuple[Path, ...],
    options: DiscoveryOptions,
    *,
    diagnostic: str | None = None,
) -> Workspace:
    diagnostics = () if diagnostic is None else (diagnostic,)
    return Workspace(root, source_roots, options, diagnostics)


def open_workspace(
    root: Path,
    options: DiscoveryOptions | None = None,
    *,
    uv_runner: Callable[[Path], str] = run_uv_workspace,
) -> Workspace:
    resolved = root.resolve()
    if not resolved.is_dir():
        raise WorkspaceRootMissingError(resolved)
    chosen = DiscoveryOptions() if options is None else options
    fallback = find_source_roots(resolved, chosen)
    discovered = discover_uv_members(resolved, uv_runner)
    if isinstance(discovered, str):
        return construct_workspace(resolved, fallback, chosen, diagnostic=discovered)
    members = validate_workspace_members(resolved, discovered)
    if isinstance(members, str):
        return construct_workspace(resolved, fallback, chosen, diagnostic=members)
    roots = derive_workspace_source_roots(members, chosen)
    return construct_workspace(resolved, roots, chosen)


def find_ancestor(start: Path, contains: Callable[[Path], bool]) -> Path | None:
    candidates = (start, *start.parents)
    return next((path for path in candidates if contains(path)), None)


def list_ancestors_to(start: Path, boundary: Path) -> tuple[Path, ...]:
    if not start.is_relative_to(boundary):
        return (start,)
    candidates = (start, *start.parents)
    return tuple(path for path in candidates if path.is_relative_to(boundary))


def has_entry(directory: Path, name: str) -> bool:
    return directory.joinpath(name).exists()


def find_search_boundary(start: Path, markers: Sequence[str]) -> Path:
    holders = (find_ancestor(start, partial(has_entry, name=name)) for name in markers)
    return next((holder for holder in holders if holder is not None), start)

"""The repository the plugin works in: where it is, its paths under `.mightymodels/`, and git.

Each edge builds one workspace, the server in its lifespan and `verify run` for its one command.
An edge starts wherever the session did, which may be a subdirectory, so it asks `Git.checkout`
where it is and builds the workspace at the toplevel: `.mightymodels/` sits there whatever
directory the edge started in. With no git executable, or outside a work tree, the answer is the
refusal. A `Checkout` is the toplevel and the origin remote's URL, and its `repository_key` names
the repository for the state database: from the origin when that is exactly an owner and a name on
a host, and from the toplevel path otherwise.

Every path under the state directory comes whole from `contained_in`, which resolves it and
refuses one that leaves the resolved state directory, so a symlink planted below it carries no
read and no write outside. The state directory is held privately, so nothing outside this module
joins a part onto it and every path passes through `contained_in`.

The files a ticket leaves for whoever picks it up are named by `HandoffFiles`, which the
workspace carries as `handoffs`: the snapshot, a closing's archive, and the debug note whose
presence says a debug is still live. It holds the same resolved state directory and hands out
contained paths only.

A persona report is the one path a symlink may not stand in for, wherever the symlink points.
Resolving the report would hide that its last part is one, so `Workspace.persona_report` looks at
the name as the reviewer wrote it before resolving it, and hands out a contained file only when
that name is no symlink.

Git runs in `Git._answer` and nowhere else, through the process runner and within the timeout
that `git_at` gives it. `git_at` looks the executable up on PATH once, and every call of that
`Git` and of the workspace built from it runs what was found. A missing git binary is an answer
without an exit code, never an exception, and so is a git that could not be launched, did not
finish in time or printed what is not text; HEAD is absent there as it is outside a repository or
before the first commit. `Git.refusal` and `Git.checkout` tell the two apart: `GitMissingError`
when there is no executable, `GitNoAnswerError` naming the cause otherwise. An operation that
cannot work without git asks `Git.refusal` first and raises what it returns, and one that can
says in its result that git was not consulted.
"""

import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path

from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.process import (
    FailedRun,
    FailureKind,
    ProcessRunner,
    process_runner,
)
from mightymodels_plugin.core.repository_key import RepositoryKey, local_key, origin_key
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import ARCHIVES_DIRECTORY, Slug

PROJECT_DIR_VARIABLE = 'CLAUDE_PROJECT_DIR'
STATE_DIRECTORY = '.mightymodels'
RUNTIME_DIRECTORY = '.runtime'
GIT_EXECUTABLE = 'git'
GIT_NOT_FOUND = 'no git executable is on PATH'
GIT_TIMEOUT_SECONDS = 30
TICKET_FILE = 'ticket.yml'
TICKET_DRAFT = f'{TICKET_FILE}.tmp'
EXCLUDE_LINE = f'{STATE_DIRECTORY}/'
HANDOFFS_DIRECTORY = 'handoffs'
SNAPSHOT_NAME = 'snapshot'
LIVE_DEBUG_FILE = 'whats-broken.md'
SAFE_REVISION = re.compile(r'[0-9A-Za-z][0-9A-Za-z._/-]*')


class OutsideStateDirectoryError(StateError):
    def __init__(self, shown: str) -> None:
        super().__init__(
            f'{shown} resolves outside {STATE_DIRECTORY}/ and is not read or written; '
            'remove the symlink that leads there'
        )
        self.shown = shown


class GitMissingError(StateError):
    def __init__(self) -> None:
        super().__init__('this needs git and no git executable is on PATH')


class GitNoAnswerError(StateError):
    def __init__(self, detail: str) -> None:
        super().__init__(f'this needs git and git did not answer: {detail}')
        self.detail = detail


class NotARepositoryError(StateError):
    def __init__(self, root: Path, detail: str) -> None:
        super().__init__(f'{root} is not inside a git repository: {detail}')
        self.root = root
        self.detail = detail


class UnsafeRevisionError(StateError):
    def __init__(self, revision: str) -> None:
        super().__init__(f'{revision!r} is not a plain revision name')
        self.revision = revision


class GitUnavailableError(StateError):
    def __init__(self, detail: str) -> None:
        super().__init__(f'git could not list the commit changes: {detail}')
        self.detail = detail


type GitUnanswered = GitMissingError | GitNoAnswerError
type GitRefusal = GitUnanswered | NotARepositoryError


class UntrackedFiles(StrEnum):
    NORMAL = auto()
    NO = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class GitAnswer:
    exit: int | None
    stdout: str
    stderr: str
    failure: FailureKind | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Checkout:
    toplevel: Path
    origin_url: str | None

    def repository_key(self) -> RepositoryKey:
        owner_and_name = None if self.origin_url is None else origin_key(self.origin_url)
        return local_key(self.toplevel) if owner_and_name is None else owner_and_name


@dataclass(slots=True, kw_only=True, frozen=True)
class PersonaReport:
    relative: str
    file: Path | None


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordFiles:
    markdown: Path
    record: Path


def find_root(environ: Mapping[str, str], cwd: Path) -> Path:
    project_dir = environ.get(PROJECT_DIR_VARIABLE, '')
    return Path(project_dir) if project_dir else cwd


def revision_error(*revisions: str) -> UnsafeRevisionError | None:
    unsafe = next(
        (revision for revision in revisions if not SAFE_REVISION.fullmatch(revision)), None
    )
    return None if unsafe is None else UnsafeRevisionError(unsafe)


def unanswered_error(answer: GitAnswer) -> GitUnanswered | None:
    if answer.failure is None:
        return None
    if answer.failure is FailureKind.NOT_FOUND:
        return GitMissingError()
    return GitNoAnswerError(answer.stderr)


def contained_in(state_directory: Path, *parts: str) -> Path:
    resolved = state_directory.joinpath(*parts).resolve()
    if not resolved.is_relative_to(state_directory):
        raise OutsideStateDirectoryError(str(Path(STATE_DIRECTORY, *parts)))
    return resolved


def review_parts(slug: Slug | None, run: RunId) -> tuple[str, ...]:
    if slug is None:
        return RUNTIME_DIRECTORY, 'reviews', run.root
    return slug.root, 'review', run.root


def exclude_state(common_directory: Path) -> None:
    exclude = common_directory.joinpath('info', 'exclude')
    current = exclude.read_text(encoding='utf-8') if exclude.is_file() else ''
    if EXCLUDE_LINE in current.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = '' if not current or current.endswith('\n') else '\n'
    exclude.write_text(f'{current}{separator}{EXCLUDE_LINE}\n', encoding='utf-8')


@dataclass(slots=True, kw_only=True, frozen=True)
class Git:
    root: Path
    executable: str | None
    processes: ProcessRunner
    timeout: float

    def _answer(self, *arguments: str) -> GitAnswer:
        if self.executable is None:
            return GitAnswer(
                exit=None, stdout='', stderr=GIT_NOT_FOUND, failure=FailureKind.NOT_FOUND
            )
        run = self.processes.run(
            [self.executable, '-C', str(self.root), *arguments], timeout=self.timeout
        )
        if isinstance(run, FailedRun):
            return GitAnswer(exit=None, stdout='', stderr=run.detail, failure=run.kind)
        return GitAnswer(exit=run.exit, stdout=run.stdout, stderr=run.stderr, failure=None)

    def refusal(self) -> GitRefusal | None:
        answer = self._answer('rev-parse', '--git-dir')
        if (unanswered := unanswered_error(answer)) is not None:
            return unanswered
        if answer.exit != 0:
            return NotARepositoryError(self.root, answer.stderr.strip())
        return None

    def checkout(self) -> Checkout | GitRefusal:
        toplevel = self._answer('rev-parse', '--show-toplevel')
        if (unanswered := unanswered_error(toplevel)) is not None:
            return unanswered
        if toplevel.exit != 0:
            return NotARepositoryError(self.root, toplevel.stderr.strip())
        origin = self._answer('config', '--get', 'remote.origin.url')
        if (unanswered := unanswered_error(origin)) is not None:
            return unanswered
        url = origin.stdout.removesuffix('\n')
        return Checkout(
            toplevel=Path(toplevel.stdout.removesuffix('\n')).resolve(),
            origin_url=url if origin.exit == 0 and url else None,
        )

    def common_directory(self) -> Path | None:
        answer = self._answer('rev-parse', '--path-format=absolute', '--git-common-dir')
        return Path(answer.stdout.strip()) if answer.exit == 0 else None

    def resolve_head(self) -> str | None:
        answer = self._answer('rev-parse', '--verify', '--quiet', 'HEAD')
        return answer.stdout.strip() if answer.exit == 0 else None

    def resolve_commit(self, revision: str) -> str | None:
        error = revision_error(revision)
        if error is not None:
            raise error
        answer = self._answer('rev-parse', '--verify', '--quiet', f'{revision}^{{commit}}')
        return answer.stdout.strip() if answer.exit == 0 else None

    def is_ancestor(self, base: str, commit: str) -> bool:
        error = revision_error(base, commit)
        if error is not None:
            raise error
        answer = self._answer('merge-base', '--is-ancestor', base, commit)
        if answer.exit not in {0, 1}:
            raise GitUnavailableError(answer.stderr.strip())
        return answer.exit == 0

    def changed_files(self, base: str, commit: str) -> set[str]:
        error = revision_error(base, commit)
        if error is not None:
            raise error
        answer = self._answer('diff', '--name-only', f'{base}..{commit}', '--')
        if answer.exit != 0:
            raise GitUnavailableError(answer.stderr.strip())
        return {line for line in answer.stdout.splitlines() if line}

    def current_branch(self) -> str | None:
        answer = self._answer('symbolic-ref', '--quiet', '--short', 'HEAD')
        return answer.stdout.strip() if answer.exit == 0 else None

    def dirty_paths(self, *, untracked: UntrackedFiles) -> list[str] | None:
        answer = self._answer('status', '--porcelain', f'--untracked-files={untracked}')
        if answer.exit != 0:
            return None
        return [line[3:] for line in answer.stdout.splitlines() if line.strip()]

    def commits_on_no_remote(self, branch: str) -> int | None:
        error = revision_error(branch)
        if error is not None:
            raise error
        answer = self._answer('rev-list', '--count', f'refs/heads/{branch}', '--not', '--remotes')
        return int(answer.stdout) if answer.exit == 0 else None


@dataclass(slots=True, kw_only=True, frozen=True)
class HandoffFiles:
    _state_directory: Path

    def snapshot(self, slug: Slug) -> RecordFiles:
        parts = (slug.root, HANDOFFS_DIRECTORY)
        return RecordFiles(
            markdown=contained_in(self._state_directory, *parts, f'{SNAPSHOT_NAME}.md'),
            record=contained_in(self._state_directory, *parts, f'{SNAPSHOT_NAME}.json'),
        )

    def archive(self, slug: Slug, repeat: int) -> RecordFiles:
        name = slug.root if repeat == 1 else f'{slug.root}-{repeat}'
        return RecordFiles(
            markdown=contained_in(self._state_directory, ARCHIVES_DIRECTORY, f'{name}.md'),
            record=contained_in(self._state_directory, ARCHIVES_DIRECTORY, f'{name}.json'),
        )

    def live_debug(self, slug: Slug) -> Path:
        return contained_in(self._state_directory, slug.root, LIVE_DEBUG_FILE)


@dataclass(slots=True, kw_only=True, frozen=True)
class Workspace:
    root: Path
    _state_directory: Path
    git: Git
    handoffs: HandoffFiles

    def contained(self, *parts: str) -> Path:
        return contained_in(self._state_directory, *parts)

    def relative_to_root(self, contained: Path) -> str:
        return str(Path(STATE_DIRECTORY).joinpath(contained.relative_to(self._state_directory)))

    def ticket_file(self, slug: Slug) -> Path:
        return self.contained(slug.root, TICKET_FILE)

    def ticket_draft(self, slug: Slug) -> Path:
        return self.contained(slug.root, TICKET_DRAFT)

    def task_brief(self, slug: Slug, number: int) -> Path:
        return self.contained(slug.root, 'briefs', f'task-{number:02d}.md')

    def review_directory(self, slug: Slug | None, run: RunId) -> Path:
        return self.contained(*review_parts(slug, run))

    def persona_report(self, slug: Slug | None, run: RunId, *, name: str) -> PersonaReport:
        parts = (*review_parts(slug, run), name)
        directory = self.review_directory(slug, run)
        is_symlink = self._state_directory.joinpath(*parts).is_symlink()
        return PersonaReport(
            relative=str(Path(self.relative_to_root(directory), name)),
            file=None if is_symlink else self.contained(*parts),
        )

    def exclude_state_from_git(self) -> None:
        common_directory = self.git.common_directory()
        if common_directory is None:
            return
        exclude_state(common_directory)


def git_at(root: Path) -> Git:
    return Git(
        root=root.resolve(),
        executable=shutil.which(GIT_EXECUTABLE),
        processes=process_runner(),
        timeout=GIT_TIMEOUT_SECONDS,
    )


def workspace_of(git: Git) -> Workspace:
    state_directory = git.root.joinpath(STATE_DIRECTORY).resolve()
    return Workspace(
        root=git.root,
        _state_directory=state_directory,
        git=git,
        handoffs=HandoffFiles(_state_directory=state_directory),
    )


def workspace_at(root: Path) -> Workspace:
    return workspace_of(git_at(root))

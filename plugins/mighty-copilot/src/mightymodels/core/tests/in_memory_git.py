"""A git history kept in memory, standing in for `Git` wherever a service asks `GitQueries`.

A test arranges it with `commit`, which records the files a commit changed on top of HEAD and
moves HEAD to it, or on another history when it is `unrelated`. HEAD is the newest commit, and
there is none before the first. It answers only for the commits it holds and launches nothing.

The rest is what it was built with. A branch named in `branches` is in the repository and at
HEAD, and any other branch is not there. `dirty` is `None` when the status cannot be read.
"""

import hashlib
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from mightymodels.core.workspace import GitRefusal, UntrackedFiles, revision_error

HEAD = 'HEAD'
BRANCH_REFS = 'refs/heads/'
SHA_LENGTH = 40


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedCommit:
    sha: str
    parent: str | None
    changed: frozenset[str]


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryGit:
    branch: str | None = 'main'
    branches: Collection[str] = ()
    refused: GitRefusal | None = None
    dirty: Sequence[str] | None = ()
    untracked: Sequence[str] = ()
    unpushed: Mapping[str, int] = field(default_factory=dict)
    commits: list[RecordedCommit] = field(default_factory=list)

    def commit(self, *changed: str, unrelated: bool = False) -> str:
        sha = hashlib.sha256(str(len(self.commits)).encode()).hexdigest()[:SHA_LENGTH]
        parent = None if unrelated else self.resolve_head()
        self.commits.append(RecordedCommit(sha=sha, parent=parent, changed=frozenset(changed)))
        return sha

    def history_of(self, sha: str) -> list[RecordedCommit]:
        held = {commit.sha: commit for commit in self.commits}
        reached: list[RecordedCommit] = []
        current = held.get(sha)
        while current is not None:
            reached.append(current)
            current = None if current.parent is None else held.get(current.parent)
        return reached

    def refusal(self) -> GitRefusal | None:
        return self.refused

    def resolve_head(self) -> str | None:
        return self.commits[-1].sha if self.commits else None

    def resolve_commit(self, revision: str) -> str | None:
        if (error := revision_error(revision)) is not None:
            raise error
        if revision == HEAD or revision.removeprefix(BRANCH_REFS) in self.branches:
            return self.resolve_head()
        named = {commit.sha for commit in self.commits if commit.sha.startswith(revision)}
        return named.pop() if len(named) == 1 else None

    def is_ancestor(self, base: str, commit: str) -> bool:
        if (error := revision_error(base, commit)) is not None:
            raise error
        return base in {reached.sha for reached in self.history_of(commit)}

    def changed_files(self, base: str, commit: str) -> set[str]:
        if (error := revision_error(base, commit)) is not None:
            raise error
        behind = {reached.sha for reached in self.history_of(base)}
        since = (reached for reached in self.history_of(commit) if reached.sha not in behind)
        return {path for reached in since for path in reached.changed}

    def current_branch(self) -> str | None:
        return self.branch

    def dirty_paths(self, *, untracked: UntrackedFiles) -> list[str] | None:
        if self.dirty is None:
            return None
        shown = self.untracked if untracked is UntrackedFiles.NORMAL else ()
        return [*self.dirty, *shown]

    def commits_on_no_remote(self, branch: str) -> int | None:
        if (error := revision_error(branch)) is not None:
            raise error
        return self.unpushed.get(branch)

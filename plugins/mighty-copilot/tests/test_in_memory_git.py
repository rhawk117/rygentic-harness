"""The git history kept in memory answers the eight questions a service asks git."""

from dataclasses import replace
from operator import methodcaller
from pathlib import Path

import pytest
from mightymodels.core.tests.in_memory_git import InMemoryGit
from mightymodels.core.workspace import (
    GitMissingError,
    GitQueries,
    UnsafeRevisionError,
    UntrackedFiles,
    git_at,
)

OPTION_SHAPED = '--output=/tmp/pwned'
SHORT = 12


class TestInMemoryGit:
    def test_the_stand_in_and_git_both_answer_the_git_queries(
        self, in_memory_git: InMemoryGit, tmp_path: Path
    ) -> None:
        assert isinstance(in_memory_git, GitQueries)
        assert isinstance(git_at(tmp_path), GitQueries)

    def test_there_is_no_head_before_the_first_commit(self, in_memory_git: InMemoryGit) -> None:
        assert in_memory_git.resolve_head() is None
        assert in_memory_git.resolve_commit('HEAD') is None

    def test_a_commit_moves_head_and_resolves_by_its_short_id(
        self, in_memory_git: InMemoryGit
    ) -> None:
        first = in_memory_git.commit('src/queue.py')
        second = in_memory_git.commit('src/client.py')

        assert in_memory_git.resolve_head() == second
        assert in_memory_git.resolve_commit('HEAD') == second
        assert in_memory_git.resolve_commit(first[:SHORT]) == first
        assert in_memory_git.resolve_commit('0' * SHORT) is None

    def test_changed_files_are_those_of_the_commits_after_the_base(
        self, in_memory_git: InMemoryGit
    ) -> None:
        base = in_memory_git.commit('src/queue.py')
        in_memory_git.commit('src/client.py')
        head = in_memory_git.commit('deploy/values.yaml')

        assert in_memory_git.is_ancestor(base, head)
        assert not in_memory_git.is_ancestor(head, base)
        assert in_memory_git.changed_files(base, head) == {'src/client.py', 'deploy/values.yaml'}

    def test_a_commit_on_an_unrelated_history_has_no_ancestor(
        self, in_memory_git: InMemoryGit
    ) -> None:
        base = in_memory_git.commit('src/queue.py')

        head = in_memory_git.commit('src/queue.py', unrelated=True)

        assert in_memory_git.resolve_head() == head
        assert not in_memory_git.is_ancestor(base, head)

    @pytest.mark.parametrize(
        'ask',
        [
            pytest.param(methodcaller('resolve_commit', OPTION_SHAPED), id='resolve-commit'),
            pytest.param(methodcaller('is_ancestor', 'HEAD', OPTION_SHAPED), id='is-ancestor'),
            pytest.param(methodcaller('changed_files', OPTION_SHAPED, 'HEAD'), id='changed-files'),
            pytest.param(methodcaller('commits_on_no_remote', OPTION_SHAPED), id='unpushed'),
        ],
    )
    def test_an_option_shaped_revision_is_refused_as_git_refuses_it(
        self, in_memory_git: InMemoryGit, ask: methodcaller
    ) -> None:
        with pytest.raises(UnsafeRevisionError):
            ask(in_memory_git)

    def test_the_branch_the_dirty_paths_and_the_unpushed_commits_are_what_it_was_given(
        self, in_memory_git: InMemoryGit
    ) -> None:
        git = replace(
            in_memory_git, dirty=['src/queue.py'], untracked=['notes.txt'], unpushed={'main': 2}
        )

        assert git.current_branch() == 'main'
        assert git.dirty_paths(untracked=UntrackedFiles.NORMAL) == ['src/queue.py', 'notes.txt']
        assert git.dirty_paths(untracked=UntrackedFiles.NO) == ['src/queue.py']
        assert (git.commits_on_no_remote('main'), git.commits_on_no_remote('other')) == (2, None)

    def test_a_refusal_and_a_detached_head_are_answered_as_given(
        self, in_memory_git: InMemoryGit
    ) -> None:
        refused = GitMissingError()
        git = replace(in_memory_git, branch=None, refused=refused)

        assert (in_memory_git.refusal(), git.refusal()) == (None, refused)
        assert git.current_branch() is None

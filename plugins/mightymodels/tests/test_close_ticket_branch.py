from dataclasses import replace

import pytest
from mightymodels_plugin.core.tests.in_memory_git import InMemoryGit
from mightymodels_plugin.tools.close.tests.repo import CHECKED_OUT, TICKET, CloseRepo


class TestTheTicketBranch:
    @pytest.fixture
    def ticket_branch(self) -> str:
        return CHECKED_OUT

    @pytest.fixture
    def in_memory_git(self) -> InMemoryGit:
        return InMemoryGit(branch=CHECKED_OUT, branches=[CHECKED_OUT], unpushed={CHECKED_OUT: 1})

    @pytest.fixture
    def repo_with_an_uncommitted_change(self, close_repo: CloseRepo) -> CloseRepo:
        return close_repo.seeing(replace(close_repo.git, dirty=['queue.py']))

    @pytest.fixture
    def repo_with_the_branch_on_a_remote(self, close_repo: CloseRepo) -> CloseRepo:
        return close_repo.seeing(replace(close_repo.git, unpushed={CHECKED_OUT: 0}))

    @pytest.fixture
    def repo_on_another_branch_with_an_uncommitted_change(
        self, repo_with_an_uncommitted_change: CloseRepo
    ) -> CloseRepo:
        elsewhere = replace(repo_with_an_uncommitted_change.git, branch='elsewhere')
        return repo_with_an_uncommitted_change.seeing(elsewhere)

    def test_a_branch_with_commits_on_no_remote_blocks(self, close_repo: CloseRepo) -> None:
        view = close_repo.closings.check(TICKET)

        assert 'branch feature has 1 commits on no remote' in view.text

    def test_a_checked_out_branch_with_uncommitted_changes_blocks(
        self, repo_with_an_uncommitted_change: CloseRepo
    ) -> None:
        view = repo_with_an_uncommitted_change.closings.check(TICKET)

        assert view.blockers == (
            'branch feature has 1 commits on no remote',
            'branch feature is checked out with uncommitted changes',
        )

    def test_a_branch_whose_commits_are_on_a_remote_does_not_block(
        self, repo_with_the_branch_on_a_remote: CloseRepo
    ) -> None:
        view = repo_with_the_branch_on_a_remote.closings.check(TICKET)

        assert (view.blocked, view.blockers) == (False, ())

    def test_uncommitted_changes_on_another_branch_do_not_block(
        self, repo_on_another_branch_with_an_uncommitted_change: CloseRepo
    ) -> None:
        view = repo_on_another_branch_with_an_uncommitted_change.closings.check(TICKET)

        assert view.blockers == ('branch feature has 1 commits on no remote',)


class TestABranchGitHasNoAnswerFor:
    @pytest.fixture
    def ticket_branch(self) -> str:
        return CHECKED_OUT

    @pytest.fixture
    def in_memory_git(self) -> InMemoryGit:
        return InMemoryGit(branch=CHECKED_OUT, branches=[CHECKED_OUT], unpushed={CHECKED_OUT: 1})

    @pytest.fixture
    def repo_with_the_branch_deleted(self, close_repo: CloseRepo) -> CloseRepo:
        return close_repo.seeing(replace(close_repo.git, branch='elsewhere', branches=[]))

    @pytest.fixture
    def repo_whose_unpushed_commits_git_cannot_count(self, close_repo: CloseRepo) -> CloseRepo:
        return close_repo.seeing(replace(close_repo.git, unpushed={}))

    @pytest.fixture
    def repo_whose_status_git_cannot_read(self, close_repo: CloseRepo) -> CloseRepo:
        return close_repo.seeing(replace(close_repo.git, dirty=None))

    def test_a_branch_that_is_no_longer_in_the_repository_does_not_block(
        self, repo_with_the_branch_deleted: CloseRepo
    ) -> None:
        view = repo_with_the_branch_deleted.closings.check(TICKET)

        assert (view.blocked, view.blockers) == (False, ())

    def test_a_branch_whose_unpushed_commits_git_cannot_count_blocks(
        self, repo_whose_unpushed_commits_git_cannot_count: CloseRepo
    ) -> None:
        view = repo_whose_unpushed_commits_git_cannot_count.closings.check(TICKET)

        assert view.blockers == (
            'branch feature could not be checked: git could not count its commits on no remote',
        )

    def test_a_checked_out_branch_whose_status_git_cannot_read_blocks(
        self, repo_whose_status_git_cannot_read: CloseRepo
    ) -> None:
        view = repo_whose_status_git_cannot_read.closings.check(TICKET)

        assert view.blockers == (
            'branch feature has 1 commits on no remote',
            'branch feature could not be checked: git could not read the working-tree status',
        )

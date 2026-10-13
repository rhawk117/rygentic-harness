from dataclasses import dataclass, replace
from operator import methodcaller
from pathlib import Path

import pytest
from mightymodels.core.tests.support import Recorder
from mightymodels.core.workspace import Git, UntrackedFiles, git_at

BASE = 'main'
COMMIT = 'feature/retry-queue'


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordingGit:
    git: Git
    recorder: Recorder

    def vectors_after(self, call: methodcaller) -> list[list[str]]:
        call(self.git)
        return [recorded.argv for recorded in self.recorder.calls()]

    def vectors_of(self, *git_arguments: list[str]) -> list[list[str]]:
        return [
            [self.recorder.executable, '-C', str(self.git.root), *arguments]
            for arguments in git_arguments
        ]


@pytest.fixture
def recording_git(tmp_path: Path, recorder: Recorder) -> RecordingGit:
    git = replace(git_at(tmp_path.joinpath('checkout')), executable=recorder.executable)
    return RecordingGit(git=git, recorder=recorder)


class TestGitArgumentVectors:
    @pytest.mark.parametrize(
        ('call', 'git_arguments'),
        [
            pytest.param(methodcaller('refusal'), [['rev-parse', '--git-dir']], id='refusal'),
            pytest.param(
                methodcaller('checkout'),
                [['rev-parse', '--show-toplevel'], ['config', '--get', 'remote.origin.url']],
                id='checkout',
            ),
            pytest.param(
                methodcaller('common_directory'),
                [['rev-parse', '--path-format=absolute', '--git-common-dir']],
                id='common_directory',
            ),
            pytest.param(
                methodcaller('resolve_head'),
                [['rev-parse', '--verify', '--quiet', 'HEAD']],
                id='resolve_head',
            ),
            pytest.param(
                methodcaller('resolve_commit', COMMIT),
                [['rev-parse', '--verify', '--quiet', f'{COMMIT}^{{commit}}']],
                id='resolve_commit',
            ),
            pytest.param(
                methodcaller('is_ancestor', BASE, COMMIT),
                [['merge-base', '--is-ancestor', BASE, COMMIT]],
                id='is_ancestor',
            ),
            pytest.param(
                methodcaller('changed_files', BASE, COMMIT),
                [['diff', '--name-only', f'{BASE}..{COMMIT}', '--']],
                id='changed_files',
            ),
            pytest.param(
                methodcaller('current_branch'),
                [['symbolic-ref', '--quiet', '--short', 'HEAD']],
                id='current_branch',
            ),
            pytest.param(
                methodcaller('dirty_paths', untracked=UntrackedFiles.NORMAL),
                [['status', '--porcelain', '--untracked-files=normal']],
                id='dirty_paths-with-untracked-files',
            ),
            pytest.param(
                methodcaller('dirty_paths', untracked=UntrackedFiles.NO),
                [['status', '--porcelain', '--untracked-files=no']],
                id='dirty_paths-without-untracked-files',
            ),
            pytest.param(
                methodcaller('commits_on_no_remote', COMMIT),
                [['rev-list', '--count', f'refs/heads/{COMMIT}', '--not', '--remotes']],
                id='commits_on_no_remote',
            ),
        ],
    )
    def test_a_git_method_passes_its_argument_vector_after_the_checkout_root(
        self, recording_git: RecordingGit, call: methodcaller, git_arguments: list[list[str]]
    ) -> None:
        vectors = recording_git.vectors_after(call)

        assert vectors == recording_git.vectors_of(*git_arguments)

from pathlib import Path

import pytest
from mightymodels_evals.errors import RepoCommandError
from mightymodels_evals.repo import Repo


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    tmp_path.joinpath('src').mkdir()
    tmp_path.joinpath('src/app.py').write_text('value = 1\n', encoding='utf-8')
    built = Repo(tmp_path)
    built.init_commit('initial')
    return built


def test_init_commit_produces_clean_tree(repo: Repo) -> None:
    assert repo.status_lines() == []
    assert repo.commit_subjects() != []


def test_status_and_diff_track_changes(repo: Repo) -> None:
    repo.root.joinpath('src/app.py').write_text('value = 2\n', encoding='utf-8')
    assert repo.diff_names() == ['src/app.py']
    assert any('app.py' in line for line in repo.status_lines('src'))


def test_commit_subjects_scoped_by_pathspec(repo: Repo) -> None:
    repo.root.joinpath('docs.md').write_text('notes\n', encoding='utf-8')
    repo.commit_all('add docs')
    assert len(repo.commit_subjects()) == 2
    assert len(repo.commit_subjects('src')) == 1


def test_branch_and_move(repo: Repo) -> None:
    repo.checkout_new('feature/x')
    assert repo.has_branch('feature/x')
    assert not repo.has_branch('feature/missing')

    repo.move('src/app.py', 'src/core.py')
    repo.commit_all('rename app to core')
    assert repo.root.joinpath('src/core.py').is_file()


def test_run_raises_on_failure(repo: Repo) -> None:
    with pytest.raises(RepoCommandError, match='failed'):
        repo.run('mv', 'src/absent.py', 'src/other.py')

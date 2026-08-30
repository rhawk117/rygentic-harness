from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from pydantic_evals.evaluators import EvaluatorContext

if TYPE_CHECKING:
    from pydantic_evals.otel.span_tree import SpanTree

from plugin_evals.artifacts import RunArtifacts
from plugin_evals.evaluators import (
    FileContains,
    FileLineCap,
    GitCommitsTouchingAtMost,
    GitStatusClean,
    GlobFileContainsAll,
    ResponseTailAsksQuestion,
)
from plugin_evals.evaluators.base import CheckContext
from plugin_evals.repo import Repo


def _repo(tmp_path: Path) -> Path:
    tmp_path.joinpath('src').mkdir()
    tmp_path.joinpath('src/app.py').write_text('value = 1\n')
    Repo(tmp_path).init_commit('initial')
    return tmp_path


def _ctx(workdir: Path, response: str = '') -> CheckContext:
    return EvaluatorContext(
        name='test-case',
        inputs={},
        metadata=None,
        expected_output=None,
        output=RunArtifacts(workdir=workdir, response=response),
        duration=0.0,
        _span_tree=cast('SpanTree', None),  # no Check reads the span tree
        attributes={},
        metrics={},
    )


def test_file_contains_both_polarities(tmp_path: Path) -> None:
    tmp_path.joinpath('a.md').write_text('hello world')
    assert (
        FileContains(path='a.md', needle='hello').evaluate(_ctx(tmp_path)).value is True
    )
    assert (
        FileContains(path='a.md', needle='absent', expect=False)
        .evaluate(_ctx(tmp_path))
        .value
        is True
    )
    assert (
        FileContains(path='a.md', needle='absent').evaluate(_ctx(tmp_path)).value is False
    )
    assert (
        FileContains(path='missing.md', needle='x').evaluate(_ctx(tmp_path)).value
        is False
    )


def test_file_line_cap(tmp_path: Path) -> None:
    tmp_path.joinpath('b.md').write_text('one\ntwo\nthree\n')
    assert FileLineCap(path='b.md', max_lines=3).evaluate(_ctx(tmp_path)).value is True
    assert FileLineCap(path='b.md', max_lines=2).evaluate(_ctx(tmp_path)).value is False


def test_git_status_clean_respects_allowlist(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert GitStatusClean().evaluate(_ctx(repo)).value is True

    repo.joinpath('scout-dispatches').mkdir()
    repo.joinpath('scout-dispatches/01.md').write_text('q')
    assert GitStatusClean().evaluate(_ctx(repo)).value is False
    allowed = GitStatusClean(allow_untracked_under=['scout-dispatches'])
    assert allowed.evaluate(_ctx(repo)).value is True


def test_commit_count_catches_committed_work(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    check = GitCommitsTouchingAtMost(pathspec='src', max_count=1)
    assert check.evaluate(_ctx(repo)).value is True

    repo.joinpath('src/app.py').write_text('value = 2\n')
    Repo(repo).commit_all('sneaky fix')
    result = check.evaluate(_ctx(repo))
    assert result.value is False
    assert 'sneaky' in (result.reason or '')


def test_glob_file_contains_all_filters_by_name(tmp_path: Path) -> None:
    d = tmp_path.joinpath('dispatches')
    d.mkdir()
    d.joinpath('budgetron-e501.md').write_text('Fix: wrap line\nVerify: ruff check')
    d.joinpath('engineer-t1.md').write_text('Fix: nothing')
    check = GlobFileContainsAll(
        pattern='dispatches/*', name_regex='budgetron', needles=['Fix:', 'Verify:']
    )
    assert check.evaluate(_ctx(tmp_path)).value is True
    miss = GlobFileContainsAll(
        pattern='dispatches/*', name_regex='engineer', needles=['Verify:']
    )
    assert miss.evaluate(_ctx(tmp_path)).value is False


@pytest.mark.parametrize(
    ('response', 'expected'),
    [('all done. Which way?', True), ('all done, proceeding.', False)],
)
def test_response_tail_question(tmp_path: Path, response: str, *, expected: bool) -> None:
    assert ResponseTailAsksQuestion().evaluate(_ctx(tmp_path, response)).value is expected

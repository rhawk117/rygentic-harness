import io
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Self

import pytest
from mightymodels_plugin.cli import build_parser
from mightymodels_plugin.commands.rejection import EXIT_REJECTED
from mightymodels_plugin.commands.review_signals import Analysis, write_report
from mightymodels_plugin.core.process import CompletedRun, FailedRun, FailureKind, RunOutcome
from mightymodels_plugin.core.workspace import GIT_TIMEOUT_SECONDS, git_at

COMMAND = 'review-signals'
GIT = '/opt/git/bin/git'
LOG = [GIT, 'log', '--no-merges', '--no-renames', '--numstat', '--format=%x1e%H']
NO_COMMITS = CompletedRun(exit=0, stdout='', stderr='')
USAGE_ERROR = 2


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedRun:
    argv: list[str]
    timeout: float
    cwd: Path | None


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordingRunner:
    outcome: RunOutcome
    runs: list[RecordedRun] = field(default_factory=list)

    def run(self, argv: Sequence[str], *, timeout: float, cwd: Path | None = None) -> RunOutcome:
        self.runs.append(RecordedRun(argv=list(argv), timeout=timeout, cwd=cwd))
        return self.outcome


@dataclass(slots=True, kw_only=True, frozen=True)
class Reported:
    code: int
    vectors: list[list[str]]
    out: str
    err: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Checkout:
    root: Path
    executable: str | None
    runner: RecordingRunner
    capsys: pytest.CaptureFixture[str]

    def answering(self, outcome: RunOutcome) -> Self:
        return replace(self, runner=RecordingRunner(outcome=outcome))

    def report(self, *arguments: str) -> Reported:
        git = replace(git_at(self.root), executable=self.executable, processes=self.runner)
        code = write_report(build_parser().parse_args([COMMAND, *arguments]), git)
        captured = self.capsys.readouterr()
        return Reported(
            code=code,
            vectors=[run.argv for run in self.runner.runs],
            out=captured.out,
            err=captured.err,
        )


@pytest.fixture
def checkout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Checkout:
    root = tmp_path.joinpath('checkout')
    root.joinpath('.git').mkdir(parents=True)
    return Checkout(
        root=root, executable=GIT, runner=RecordingRunner(outcome=NO_COMMITS), capsys=capsys
    )


class TestGitLogArgumentVector:
    @pytest.mark.parametrize('report', list(Analysis))
    @pytest.mark.parametrize(
        ('target_flags', 'target'),
        [
            pytest.param((), [], id='whole-repository'),
            pytest.param(('--target', 'src'), ['src'], id='target'),
        ],
    )
    @pytest.mark.parametrize(
        ('window_flags', 'window'),
        [
            pytest.param((), ['--max-count=500', 'HEAD'], id='default-window'),
            pytest.param(('--max-commits', '40'), ['--max-count=40', 'HEAD'], id='max-commits'),
            pytest.param(('--all-history',), ['HEAD'], id='all-history'),
            pytest.param(
                ('--since', '2026-01-01'),
                ['--max-count=500', '--since=2026-01-01', 'HEAD'],
                id='since',
            ),
            pytest.param(
                ('--baseline-ref', 'release/1.2'),
                ['--max-count=500', 'release/1.2..HEAD'],
                id='baseline-ref',
            ),
            pytest.param(
                ('--max-commits', '40', '--since', '2026-01-01', '--baseline-ref', 'main'),
                ['--max-count=40', '--since=2026-01-01', 'main..HEAD'],
                id='max-commits-since-and-baseline-ref',
            ),
            pytest.param(
                ('--all-history', '--since', '2026-01-01', '--baseline-ref', 'v1.2.0'),
                ['--since=2026-01-01', 'v1.2.0..HEAD'],
                id='all-history-since-and-baseline-ref',
            ),
        ],
    )
    def test_git_is_passed_the_vector_the_script_built_for_the_window(
        self,
        checkout: Checkout,
        report: str,
        window_flags: tuple[str, ...],
        window: list[str],
        target_flags: tuple[str, ...],
        target: list[str],
    ) -> None:
        reported = checkout.report(report, *window_flags, *target_flags)

        assert (reported.code, reported.vectors) == (0, [[*LOG, *window, '--', *target]])

    @pytest.mark.parametrize(
        ('flags', 'values'),
        [
            pytest.param(
                ('--since', '6 months ago'),
                ['--max-count=500', '--since=6 months ago', 'HEAD', '--'],
                id='since-holding-a-space',
            ),
            pytest.param(
                ('--target', 'release notes/v2 draft.md'),
                ['--max-count=500', 'HEAD', '--', 'release notes/v2 draft.md'],
                id='target-holding-spaces',
            ),
            pytest.param(
                ('--target=--output=report',),
                ['--max-count=500', 'HEAD', '--', '--output=report'],
                id='option-shaped-target',
            ),
            pytest.param(
                ('--since', '6 months ago', '--target', 'release notes'),
                ['--max-count=500', '--since=6 months ago', 'HEAD', '--', 'release notes'],
                id='since-and-target-holding-spaces',
            ),
        ],
    )
    def test_each_value_is_one_element_and_the_target_follows_the_separator(
        self, checkout: Checkout, flags: tuple[str, ...], values: list[str]
    ) -> None:
        reported = checkout.report(Analysis.CHURN, *flags)

        assert reported.vectors == [[*LOG, *values]]

    def test_git_runs_once_at_the_repository_root_under_the_git_timeout(
        self, checkout: Checkout
    ) -> None:
        checkout.report(Analysis.HOTSPOTS)

        assert [(run.timeout, run.cwd) for run in checkout.runner.runs] == [
            (GIT_TIMEOUT_SECONDS, checkout.root)
        ]


class TestStandardOutput:
    TARGET = 'café'

    @pytest.fixture
    def written(self, checkout: Checkout, monkeypatch: pytest.MonkeyPatch) -> tuple[int, bytes]:
        underneath = io.BytesIO()
        monkeypatch.setattr(sys, 'stdout', io.TextIOWrapper(underneath, encoding='ascii'))
        git = replace(
            git_at(checkout.root), executable=checkout.executable, processes=checkout.runner
        )
        arguments = build_parser().parse_args([COMMAND, Analysis.CHURN, '--target', self.TARGET])
        return write_report(arguments, git), underneath.getvalue()

    def test_a_target_outside_ascii_is_written_as_utf8_whatever_the_text_stream_encodes(
        self, written: tuple[int, bytes]
    ) -> None:
        code, document = written

        assert code == 0
        assert json.loads(document)['target'] == self.TARGET


class TestTargetThatIsNotUnicode:
    NAME = 'caf\udce9'
    LINK = 'link'
    REASON = "--target resolves to 'caf\\udce9', which is not valid Unicode"

    @pytest.fixture
    def linked(self, checkout: Checkout) -> Checkout:
        checkout.root.joinpath(self.NAME).mkdir()
        checkout.root.joinpath(self.LINK).symlink_to(self.NAME, target_is_directory=True)
        return checkout

    @pytest.mark.parametrize(
        'target',
        [
            pytest.param(NAME, id='lone-surrogate'),
            pytest.param(LINK, id='symlink-to-a-name-that-is-not-utf8'),
        ],
    )
    def test_it_is_rejected_before_git_runs(self, linked: Checkout, target: str) -> None:
        reported = linked.report(Analysis.CHURN, '--target', target)

        assert reported == Reported(
            code=EXIT_REJECTED, vectors=[], out='', err=f'error: {self.REASON}\n'
        )


class TestRefusedValues:
    @pytest.mark.parametrize(
        ('flags', 'reason'),
        [
            pytest.param(
                ('--since=--output=/tmp/x',),
                "--since '--output=/tmp/x' is not a plain value",
                id='option-shaped-since',
            ),
            pytest.param(
                ('--since', '$(id)'),
                "--since '$(id)' is not a plain value",
                id='shell-shaped-since',
            ),
            pytest.param(
                ('--baseline-ref=--output=/tmp/x',),
                "--baseline-ref '--output=/tmp/x' is not a plain value",
                id='option-shaped-baseline-ref',
            ),
            pytest.param(
                ('--baseline-ref', 'main branch'),
                "--baseline-ref 'main branch' is not a plain value",
                id='baseline-ref-holding-a-space',
            ),
            pytest.param(
                ('--target', '../..'),
                "--target '../..' is outside the repository",
                id='target-outside-the-repository',
            ),
            pytest.param(
                ('--target', '/etc'),
                "--target '/etc' is outside the repository",
                id='absolute-target-outside-the-repository',
            ),
        ],
    )
    def test_a_refused_value_is_rejected_before_git_runs(
        self, checkout: Checkout, flags: tuple[str, ...], reason: str
    ) -> None:
        reported = checkout.report(Analysis.CHURN, *flags)

        assert reported == Reported(
            code=EXIT_REJECTED, vectors=[], out='', err=f'error: {reason}\n'
        )

    @pytest.mark.parametrize(
        'arguments',
        [
            pytest.param((Analysis.CHURN, '--max-commits', '0'), id='max-commits'),
            pytest.param((Analysis.HOTSPOTS, '--limit', '0'), id='limit'),
            pytest.param((Analysis.COUPLING, '--min-shared', '0'), id='min-shared'),
            pytest.param((Analysis.COUPLING, '--max-changeset', '-1'), id='max-changeset'),
        ],
    )
    def test_a_count_below_one_is_refused_by_the_parser_before_git_runs(
        self, checkout: Checkout, arguments: tuple[str, ...]
    ) -> None:
        with pytest.raises(SystemExit) as stop:
            checkout.report(*arguments)

        assert (stop.value.code, checkout.runner.runs) == (USAGE_ERROR, [])
        assert 'must be at least 1' in checkout.capsys.readouterr().err


class TestGitFailures:
    @pytest.mark.parametrize(
        ('outcome', 'reason'),
        [
            pytest.param(
                FailedRun(
                    kind=FailureKind.TIMED_OUT, detail='timed out after 30s', stdout='', stderr=''
                ),
                'timed out after 30s',
                id='timeout',
            ),
            pytest.param(
                FailedRun(kind=FailureKind.NOT_FOUND, detail='No such file', stdout='', stderr=''),
                'No such file',
                id='missing-executable',
            ),
            pytest.param(
                FailedRun(
                    kind=FailureKind.REFUSED, detail='Permission denied', stdout='', stderr=''
                ),
                'Permission denied',
                id='refused-launch',
            ),
            pytest.param(
                FailedRun(
                    kind=FailureKind.UNDECODABLE,
                    detail="can't decode byte 0xff",
                    stdout='',
                    stderr='',
                ),
                "can't decode byte 0xff",
                id='undecodable-output',
            ),
            pytest.param(
                CompletedRun(exit=128, stdout='', stderr="fatal: bad revision 'gone..HEAD'\n"),
                "fatal: bad revision 'gone..HEAD'",
                id='non-zero-exit',
            ),
        ],
    )
    def test_a_git_that_fails_is_rejected_with_its_reason(
        self, checkout: Checkout, outcome: RunOutcome, reason: str
    ) -> None:
        reported = checkout.answering(outcome).report(Analysis.CHURN)

        assert (reported.code, reported.out, reported.err) == (
            EXIT_REJECTED,
            '',
            f'error: git log failed: {reason}\n',
        )

    def test_a_missing_git_executable_is_rejected_before_anything_runs(
        self, checkout: Checkout
    ) -> None:
        reported = replace(checkout, executable=None).report(Analysis.CHURN)

        assert reported == Reported(
            code=EXIT_REJECTED, vectors=[], out='', err='error: git is not on PATH\n'
        )

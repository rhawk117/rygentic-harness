import errno
import os
import sys
from dataclasses import dataclass, replace
from operator import methodcaller
from pathlib import Path

import pytest
from mightymodels_plugin.core.declarative import WORD_LIMIT
from mightymodels_plugin.core.process import FailedRun, FailureKind, ProcessRunner, process_runner
from mightymodels_plugin.core.workspace import (
    GIT_NOT_FOUND,
    GIT_TIMEOUT_SECONDS,
    Git,
    GitMissingError,
    GitNoAnswerError,
    GitRefusal,
    GitUnavailableError,
    UntrackedFiles,
    Workspace,
    git_at,
)
from mightymodels_plugin.tools.contract.executor import (
    RunSite,
    execute,
    failure_outcome,
    receipt_for,
    with_cause,
)
from mightymodels_plugin.tools.contract.schema import ApprovedCommand, Outcome, Phase

PRINTED = 'printed before the timeout'
WARNED = 'warned before the timeout'
KIND_ONLY_TIMEOUT = 0.2
OUTPUT_TIMEOUT = 2
COMMAND_TIMEOUT = 1
REVISION = 'main'
HANGS = f"""#!{sys.executable}
import sys
import time

print({PRINTED!r}, flush=True)
print({WARNED!r}, file=sys.stderr, flush=True)
time.sleep(60)
"""
UNDECODABLE = f"""#!{sys.executable}
import sys

sys.stdout.buffer.write(bytes([255, 254]))
"""
ANSWERS_UNTIL_ASKED_FOR_THE_ORIGIN = f"""#!{sys.executable}
import sys
import time

print('/')
if 'config' in sys.argv:
    time.sleep(60)
"""
VALUE_READS = (
    methodcaller('common_directory'),
    methodcaller('resolve_head'),
    methodcaller('resolve_commit', REVISION),
    methodcaller('current_branch'),
    methodcaller('dirty_paths', untracked=UntrackedFiles.NO),
    methodcaller('commits_on_no_remote', REVISION),
)
KINDS = (
    pytest.param(FailureKind.TIMED_OUT, id='timeout'),
    pytest.param(FailureKind.NOT_FOUND, id='missing-executable'),
    pytest.param(FailureKind.REFUSED, id='refused-launch'),
    pytest.param(FailureKind.UNDECODABLE, id='undecodable-output'),
)


def executable_file(file: Path, source: str) -> str:
    file.write_text(source, encoding='utf-8')
    file.chmod(0o700)
    return str(file)


@dataclass(slots=True, kw_only=True, frozen=True)
class FailingPrograms:
    directory: Path
    runner: ProcessRunner

    def of(self, kind: FailureKind) -> str:
        return str(self.directory.joinpath(kind))

    def failure(self, kind: FailureKind, timeout: float) -> FailedRun:
        run = self.runner.run([self.of(kind)], timeout=timeout)
        assert isinstance(run, FailedRun)
        return run

    def git(self, kind: FailureKind) -> Git:
        return replace(git_at(self.directory), executable=self.of(kind), timeout=KIND_ONLY_TIMEOUT)

    def command(self, kind: FailureKind, timeout: int) -> ApprovedCommand:
        return ApprovedCommand(id='fails', argv=(self.of(kind),), expect_exit=0, timeout=timeout)


@pytest.fixture
def failing(tmp_path: Path) -> FailingPrograms:
    directory = tmp_path.joinpath('programs')
    directory.mkdir()
    programs = FailingPrograms(directory=directory, runner=process_runner())
    executable_file(Path(programs.of(FailureKind.TIMED_OUT)), HANGS)
    executable_file(Path(programs.of(FailureKind.UNDECODABLE)), UNDECODABLE)
    Path(programs.of(FailureKind.REFUSED)).write_text('not executable\n', encoding='utf-8')
    return programs


class TestRunnerFailures:
    NUL_LAUNCHES = (
        pytest.param((sys.executable, '-c', 'pass', 'a\0b'), None, id='nul-in-argument'),
        pytest.param(('pro\0gram',), None, id='nul-in-program'),
        pytest.param((sys.executable, '-c', 'pass'), Path('work\0ing'), id='nul-in-cwd'),
    )
    LONE_SURROGATE_LAUNCHES = (
        pytest.param((sys.executable, '-c', 'pass', '\ud800'), id='lone-surrogate-in-argument'),
    )

    @pytest.fixture
    def runner(self) -> ProcessRunner:
        return process_runner()

    @pytest.mark.parametrize('kind', KINDS)
    def test_a_run_that_fails_comes_back_as_a_failure_of_its_own_kind(
        self, failing: FailingPrograms, kind: FailureKind
    ) -> None:
        failure = failing.failure(kind, KIND_ONLY_TIMEOUT)

        assert (failure.kind, bool(failure.detail)) == (kind, True)

    def test_a_timed_out_run_keeps_what_it_printed_and_names_the_wait(
        self, failing: FailingPrograms
    ) -> None:
        failure = failing.failure(FailureKind.TIMED_OUT, OUTPUT_TIMEOUT)

        assert failure == FailedRun(
            kind=FailureKind.TIMED_OUT,
            detail=f'timed out after {OUTPUT_TIMEOUT}s',
            stdout=f'{PRINTED}\n',
            stderr=f'{WARNED}\n',
        )

    @pytest.mark.parametrize(('argv', 'cwd'), NUL_LAUNCHES)
    def test_a_launch_that_holds_a_nul_comes_back_refused_and_names_the_null_byte(
        self, runner: ProcessRunner, argv: tuple[str, ...], cwd: Path | None
    ) -> None:
        run = runner.run(argv, timeout=KIND_ONLY_TIMEOUT, cwd=cwd)

        assert isinstance(run, FailedRun)
        assert (run.kind, 'embedded null byte' in run.detail) == (FailureKind.REFUSED, True)

    @pytest.mark.parametrize('argv', LONE_SURROGATE_LAUNCHES)
    def test_a_launch_that_holds_a_lone_surrogate_comes_back_refused_and_names_the_surrogate(
        self, runner: ProcessRunner, argv: tuple[str, ...]
    ) -> None:
        run = runner.run(argv, timeout=KIND_ONLY_TIMEOUT)

        assert isinstance(run, FailedRun)
        assert (run.kind, 'surrogates not allowed' in run.detail) == (FailureKind.REFUSED, True)


class TestGitFailures:
    REFUSALS = (
        pytest.param(FailureKind.TIMED_OUT, GitNoAnswerError, id='timeout'),
        pytest.param(FailureKind.NOT_FOUND, GitMissingError, id='missing-executable'),
        pytest.param(FailureKind.REFUSED, GitNoAnswerError, id='refused-launch'),
        pytest.param(FailureKind.UNDECODABLE, GitNoAnswerError, id='undecodable-output'),
    )

    @pytest.fixture
    def git_without_an_origin_answer(self, tmp_path: Path) -> Git:
        program = executable_file(tmp_path.joinpath('git'), ANSWERS_UNTIL_ASKED_FOR_THE_ORIGIN)
        return replace(git_at(tmp_path), executable=program, timeout=KIND_ONLY_TIMEOUT)

    def test_git_at_gives_git_a_process_runner_and_the_git_timeout(self, tmp_path: Path) -> None:
        git = git_at(tmp_path)

        assert (isinstance(git.processes, ProcessRunner), git.timeout) == (
            True,
            GIT_TIMEOUT_SECONDS,
        )

    @pytest.mark.parametrize(('kind', 'refusal'), REFUSALS)
    def test_refusal_says_git_is_missing_only_when_the_executable_is(
        self, failing: FailingPrograms, kind: FailureKind, refusal: type[GitRefusal]
    ) -> None:
        refused = failing.git(kind).refusal()

        assert (type(refused), GIT_NOT_FOUND in str(refused)) == (
            refusal,
            kind is FailureKind.NOT_FOUND,
        )

    @pytest.mark.parametrize(('kind', 'refusal'), REFUSALS)
    def test_checkout_says_git_is_missing_only_when_the_executable_is(
        self, failing: FailingPrograms, kind: FailureKind, refusal: type[GitRefusal]
    ) -> None:
        refused = failing.git(kind).checkout()

        assert (type(refused), GIT_NOT_FOUND in str(refused)) == (
            refusal,
            kind is FailureKind.NOT_FOUND,
        )

    def test_a_git_that_outlives_its_timeout_is_refused_naming_that_timeout(
        self, failing: FailingPrograms
    ) -> None:
        refused = failing.git(FailureKind.TIMED_OUT).refusal()

        assert str(refused) == (
            f'this needs git and git did not answer: timed out after {KIND_ONLY_TIMEOUT}s'
        )

    def test_checkout_is_refused_when_git_does_not_answer_for_the_origin(
        self, git_without_an_origin_answer: Git
    ) -> None:
        assert type(git_without_an_origin_answer.checkout()) is GitNoAnswerError

    @pytest.mark.parametrize('kind', KINDS)
    def test_a_method_that_reads_a_value_answers_none(
        self, failing: FailingPrograms, kind: FailureKind
    ) -> None:
        git = failing.git(kind)

        assert [read(git) for read in VALUE_READS] == [None] * len(VALUE_READS)

    @pytest.mark.parametrize('kind', KINDS)
    @pytest.mark.parametrize(
        'comparison',
        [
            pytest.param(methodcaller('is_ancestor', REVISION, REVISION), id='is_ancestor'),
            pytest.param(methodcaller('changed_files', REVISION, REVISION), id='changed_files'),
        ],
    )
    def test_a_method_that_compares_commits_raises_that_git_is_unavailable(
        self, failing: FailingPrograms, kind: FailureKind, comparison: methodcaller
    ) -> None:
        git = failing.git(kind)

        with pytest.raises(GitUnavailableError) as raised:
            comparison(git)

        assert raised.value.detail
        assert GIT_NOT_FOUND not in raised.value.detail


class TestExecuteFailures:
    @pytest.mark.parametrize(
        ('kind', 'outcome', 'cause'),
        [
            pytest.param(
                FailureKind.TIMED_OUT,
                Outcome.TIMEOUT,
                f'timed out after {COMMAND_TIMEOUT}s',
                id='timeout',
            ),
            pytest.param(
                FailureKind.NOT_FOUND,
                Outcome.NOT_FOUND,
                os.strerror(errno.ENOENT),
                id='missing-executable',
            ),
            pytest.param(
                FailureKind.REFUSED,
                Outcome.REFUSED,
                os.strerror(errno.EACCES),
                id='refused-launch',
            ),
            pytest.param(
                FailureKind.UNDECODABLE,
                Outcome.UNDECODABLE,
                "can't decode byte 0xff",
                id='undecodable-output',
            ),
        ],
    )
    def test_execute_answers_with_an_outcome_no_exit_code_and_the_cause_in_stderr(
        self, failing: FailingPrograms, kind: FailureKind, outcome: Outcome, cause: str
    ) -> None:
        command = failing.command(kind, COMMAND_TIMEOUT)

        execution = execute(command, failing.directory, processes=failing.runner)

        assert (execution.outcome, execution.exit, cause in execution.stderr) == (
            outcome,
            None,
            True,
        )

    def test_a_command_that_outlives_its_timeout_keeps_what_it_printed_in_its_receipt(
        self, failing: FailingPrograms, repository_workspace: Workspace
    ) -> None:
        command = failing.command(FailureKind.TIMED_OUT, OUTPUT_TIMEOUT)

        site = RunSite(
            root=repository_workspace.root, git=repository_workspace.git, processes=failing.runner
        )
        receipt = receipt_for(command, site, Phase.TASK)

        assert (receipt.outcome, receipt.exit, receipt.stdout_tail, receipt.stderr_tail) == (
            Outcome.TIMEOUT,
            None,
            PRINTED,
            f'{WARNED}\ntimed out after {OUTPUT_TIMEOUT}s',
        )

    @pytest.mark.parametrize(
        ('captured', 'stderr'),
        [
            pytest.param('', 'cause', id='nothing-captured'),
            pytest.param('warning\n', 'warning\ncause', id='a-finished-line'),
            pytest.param('warning', 'warning\ncause', id='an-unfinished-line'),
        ],
    )
    def test_the_cause_is_the_last_line_of_stderr(self, captured: str, stderr: str) -> None:
        assert with_cause(captured, 'cause') == stderr


class TestOutcomes:
    def test_every_failure_kind_has_an_outcome_of_its_own_and_none_is_fail(self) -> None:
        outcomes = {failure_outcome(kind) for kind in FailureKind}

        assert (len(outcomes), Outcome.FAILED in outcomes) == (len(FailureKind), False)

    def test_every_outcome_fits_the_word_column_it_is_stored_in(self) -> None:
        assert [outcome for outcome in Outcome if len(outcome) > WORD_LIMIT] == []

import sys
from pathlib import Path

import pytest
from mightymodels_plugin.core.process import (
    Captured,
    CompletedRun,
    ProcessRunner,
    captured_text,
    process_runner,
)

TIMEOUT = 30


def python(code: str) -> list[str]:
    return [sys.executable, '-c', code]


@pytest.fixture
def runner() -> ProcessRunner:
    return process_runner()


class TestCompletedRun:
    BOTH_STREAMS = python('import sys; print("out"); print("err", file=sys.stderr); sys.exit(3)')
    WORKING_DIRECTORY = python('from pathlib import Path; print(Path.cwd())')
    CARRIAGE_RETURNS = python(r'import sys; sys.stdout.buffer.write(b"one\r\ntwo\rthree\n")')

    def test_the_factory_returns_a_process_runner(self, runner: ProcessRunner) -> None:
        assert isinstance(runner, ProcessRunner)

    def test_a_finished_run_comes_back_with_its_exit_code_and_both_streams(
        self, runner: ProcessRunner
    ) -> None:
        run = runner.run(self.BOTH_STREAMS, timeout=TIMEOUT)

        assert run == CompletedRun(exit=3, stdout='out\n', stderr='err\n')

    def test_a_run_starts_in_the_directory_it_is_given(
        self, runner: ProcessRunner, tmp_path: Path
    ) -> None:
        run = runner.run(self.WORKING_DIRECTORY, timeout=TIMEOUT, cwd=tmp_path)

        assert run == CompletedRun(exit=0, stdout=f'{tmp_path.resolve()}\n', stderr='')

    def test_a_finished_run_reads_every_line_ending_as_a_newline(
        self, runner: ProcessRunner
    ) -> None:
        run = runner.run(self.CARRIAGE_RETURNS, timeout=TIMEOUT)

        assert run == CompletedRun(exit=0, stdout='one\ntwo\nthree\n', stderr='')


class TestCapturedText:
    @pytest.mark.parametrize(
        ('captured', 'text'),
        [
            pytest.param(None, '', id='nothing-captured'),
            pytest.param('already text\n', 'already text\n', id='text'),
            pytest.param(b'one\r\ntwo\rthree\n', 'one\ntwo\nthree\n', id='carriage-returns'),
            pytest.param(
                'café'.encode()[:-1], 'caf\N{REPLACEMENT CHARACTER}', id='a-character-cut-in-half'
            ),
        ],
    )
    def test_what_a_timed_out_run_printed_is_read_as_a_finished_run_is(
        self, captured: Captured, text: str
    ) -> None:
        assert captured_text(captured) == text

"""Structural checks and tool runs of automate-task's check_script.py."""

import ast
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import check_script
import pytest
from pytest_mock import MockerFixture
from python_harness.gate.domain import DEFAULT_RUFF_VERSION

PLUGIN = Path(__file__).resolve().parents[2]
SCRIPT = PLUGIN / 'skills' / 'automate-task' / 'scripts'
TEMPLATE = SCRIPT.parent / 'assets' / 'script.template.py'
LSP_CONFIG = PLUGIN / '.lsp.json'


HEADER = '# /// script\n# requires-python = ">=3.12"\n# dependencies = []\n# ///\n'
GOOD_SCRIPT = (
    HEADER
    + """import argparse
import logging

logger = logging.getLogger(__name__)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
"""
)
ASYNC_MAIN = (
    'async def main() -> int:\n    return 0\n\nif __name__ == "__main__":\n'
    '    raise SystemExit(main())\n'
)
STATUS = check_script.Status
RUFF_VERSION = check_script.PINNED_TOOL_VERSIONS['ruff']
TY_VERSION = check_script.PINNED_TOOL_VERSIONS['ty']


def make_source(text: str) -> Any:
    return check_script.ScriptSource(path=Path('script.py'), text=text, tree=ast.parse(text))


def completed(returncode: int, stdout: str = '', stderr: str = '') -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TestStructuralChecks:
    def test_a_conforming_script_passes_every_check(self) -> None:
        source = make_source(GOOD_SCRIPT)

        statuses = {check(source).status for check in check_script.STRUCTURAL_CHECKS}

        assert statuses == {STATUS.PASS, STATUS.SKIP}

    @pytest.mark.parametrize(
        ('check', 'text'),
        [
            ('check_inline_metadata', 'print(1)\n'),
            ('check_inline_metadata', '# /// script\n# dependencies = []\n# ///\nprint(1)\n'),
            ('check_cli', 'import os\n'),
            ('check_dry_run', "import argparse\nflag = '--other'\n"),
            ('check_logging', 'import os\n'),
            ('check_logging', 'import logging\nlogging.info("x")\n'),
            ('check_main_exit_code', 'import os\n'),
            ('check_main_exit_code', 'def main():\n    return 0\n'),
            ('check_main_exit_code', 'def main() -> int:\n    return 0\n'),
            ('check_workers_flag', 'import threading\n'),
            ('check_no_shell', 'run(["x"], shell=True)\n'),
            ('check_subprocess_timeouts', 'import subprocess\nsubprocess.run(["x"])\n'),
        ],
    )
    def test_each_check_fails_on_a_violation(self, check: str, text: str) -> None:
        finding = getattr(check_script, check)(make_source(text))

        assert finding.status is STATUS.FAIL
        assert finding.line.startswith(f'FAIL {finding.check}: ')

    @pytest.mark.parametrize(
        ('check', 'text'),
        [
            ('check_inline_metadata', HEADER),
            ('check_cli', 'import click\n'),
            ('check_dry_run', "flag = '--dry-run'\n"),
            ('check_logging', 'import logging\nlogger = logging.getLogger(__name__)\n'),
            ('check_main_exit_code', ASYNC_MAIN),
            ('check_workers_flag', "import asyncio\nflag = '--workers'\n"),
            ('check_no_shell', 'run(["x"], shell=False)\nrun(["y"], shell=flag)\n'),
            (
                'check_subprocess_timeouts',
                'import subprocess\nsubprocess.run(["x"], timeout=3)\nother.run(["y"])\n',
            ),
        ],
    )
    def test_each_check_passes_a_conforming_fragment(self, check: str, text: str) -> None:
        finding = getattr(check_script, check)(make_source(text))

        assert finding.status is STATUS.PASS

    def test_a_sequential_script_skips_the_workers_check(self) -> None:
        finding = check_script.check_workers_flag(make_source('import os\n'))

        assert finding.status is STATUS.SKIP

    def test_the_script_template_passes_every_structural_check(self) -> None:
        source = make_source(TEMPLATE.read_text(encoding='utf-8'))

        statuses = {check(source).status for check in check_script.STRUCTURAL_CHECKS}

        assert statuses <= {STATUS.PASS, STATUS.SKIP}

    def test_violation_details_name_the_offending_lines(self) -> None:
        text = 'import subprocess\nsubprocess.run(["x"], shell=True)\n'

        shell = check_script.check_no_shell(make_source(text))
        timeout = check_script.check_subprocess_timeouts(make_source(text))

        assert shell.detail == 'shell=True on lines [2]'
        assert timeout.detail == 'add timeout= on lines [2]'


class TestImportResolution:
    def test_a_logger_from_another_module_does_not_satisfy_the_logging_check(self) -> None:
        source = make_source('import structlog\nlog = structlog.getLogger()\n')

        finding = check_script.check_logging(source)

        assert finding.status is STATUS.FAIL
        assert finding.detail.startswith('create logger')

    @pytest.mark.parametrize(
        'text',
        [
            'from subprocess import run\nrun(["x"])\n',
            'import subprocess as sp\nsp.run(["x"])\n',
            'from subprocess import check_output as out\nout(["x"])\n',
        ],
    )
    def test_aliased_subprocess_calls_need_a_timeout(self, text: str) -> None:
        finding = check_script.check_subprocess_timeouts(make_source(text))

        assert finding.status is STATUS.FAIL

    def test_an_aliased_subprocess_call_with_a_timeout_passes(self) -> None:
        text = 'from subprocess import run\nrun(["x"], timeout=3)\n'

        assert check_script.check_subprocess_timeouts(make_source(text)).status is STATUS.PASS

    @pytest.mark.parametrize(
        'text',
        [
            'from logging import getLogger\nlogger = getLogger(__name__)\n',
            'import logging as log\nlogger = log.getLogger(__name__)\n',
        ],
    )
    def test_an_aliased_get_logger_satisfies_the_logging_check(self, text: str) -> None:
        assert check_script.check_logging(make_source(text)).status is STATUS.PASS

    @pytest.mark.parametrize(
        'text',
        ['from concurrent import futures\n', 'import multiprocessing.pool\n'],
    )
    def test_submodule_imports_count_as_concurrent(self, text: str) -> None:
        finding = check_script.check_workers_flag(make_source(text))

        assert finding.status is STATUS.FAIL


class TestResolveTool:
    def test_an_installed_tool_is_used_directly(self, mocker: MockerFixture) -> None:
        mocker.patch.object(check_script.shutil, 'which', return_value='/bin/ruff')

        assert check_script.resolve_tool('ruff') == ['ruff']

    @pytest.mark.parametrize(('tool', 'version'), [('ruff', RUFF_VERSION), ('ty', TY_VERSION)])
    def test_uvx_is_the_fallback_at_the_pinned_version(
        self, mocker: MockerFixture, tool: str, version: str
    ) -> None:
        mocker.patch.object(
            check_script.shutil, 'which', side_effect=lambda name: name if name == 'uvx' else None
        )

        assert check_script.resolve_tool(tool) == ['uvx', f'{tool}@{version}']

    def test_the_ty_pin_is_the_version_the_language_server_runs(self) -> None:
        servers = json.loads(LSP_CONFIG.read_text(encoding='utf-8'))
        (pinned,) = [arg for arg in servers['ty']['args'] if arg.startswith('ty@')]

        assert check_script.PINNED_TOOL_VERSIONS['ty'] == pinned.removeprefix('ty@')

    def test_the_ruff_pin_is_the_gate_default_version(self) -> None:
        assert check_script.PINNED_TOOL_VERSIONS['ruff'] == DEFAULT_RUFF_VERSION.text

    def test_neither_available_gives_none(self, mocker: MockerFixture) -> None:
        mocker.patch.object(check_script.shutil, 'which', return_value=None)

        assert check_script.resolve_tool('ruff') is None


class TestRunTool:
    @pytest.fixture
    def runner(self, mocker: MockerFixture) -> MagicMock:
        mocker.patch.object(check_script, 'resolve_tool', return_value=['ruff'])
        return mocker.patch.object(check_script, 'subprocess')

    def test_a_missing_tool_is_skipped_without_running_anything(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(check_script, 'resolve_tool', return_value=None)
        runner = mocker.patch.object(check_script, 'subprocess')

        finding = check_script.run_tool('ruff', ['check'], check_script.CheckOptions())

        assert finding.status is STATUS.SKIP
        assert finding.detail == 'ruff and uvx not installed'
        runner.run.assert_not_called()

    def test_a_clean_run_passes(self, runner: MagicMock) -> None:
        runner.run.return_value = completed(0)

        finding = check_script.run_tool('ruff', ['check', 'a.py'], check_script.CheckOptions())

        assert (finding.status, finding.detail) == (STATUS.PASS, 'clean')

    def test_the_command_and_timeout_come_from_the_arguments(self, runner: MagicMock) -> None:
        runner.run.return_value = completed(0)
        options = check_script.CheckOptions(tool_timeout_seconds=7.5)

        check_script.run_tool('ruff', ['check', 'a.py'], options)

        (command,) = runner.run.call_args.args
        assert command == ['ruff', 'check', 'a.py']
        assert runner.run.call_args.kwargs['timeout'] == 7.5
        assert runner.run.call_args.kwargs['check'] is False

    def test_a_failing_run_reports_the_last_five_lines(self, runner: MagicMock) -> None:
        output = '\n'.join(f'line {number}' for number in range(1, 8))
        runner.run.return_value = completed(1, stdout=output)

        finding = check_script.run_tool('ruff', ['check'], check_script.CheckOptions())

        assert finding.status is STATUS.FAIL
        assert finding.detail == 'line 3 | line 4 | line 5 | line 6 | line 7'

    def test_stderr_is_part_of_the_report(self, runner: MagicMock) -> None:
        runner.run.return_value = completed(1, stdout='out\n', stderr='err\n')

        finding = check_script.run_tool('ruff', ['check'], check_script.CheckOptions())

        assert finding.detail == 'out | err'

    def test_an_excluded_file_is_skipped(self, runner: MagicMock) -> None:
        runner.run.return_value = completed(1, stderr='warning: No Python files found')

        finding = check_script.run_tool('ty', ['check'], check_script.CheckOptions())

        assert (finding.status, finding.detail) == (STATUS.SKIP, 'file excluded by project config')

    def test_the_output_of_a_run_is_summarised_on_its_own(self) -> None:
        finding = check_script.summarize_tool_run('ruff', completed(1, stdout='bad\n'))

        assert (finding.check, finding.status, finding.detail) == ('ruff', STATUS.FAIL, 'bad')


class TestToolCannotRun:
    def test_a_timeout_is_a_finding_that_names_the_seconds(self, mocker: MockerFixture) -> None:
        mocker.patch.object(check_script, 'resolve_tool', return_value=['ruff'])
        mocker.patch.object(
            check_script.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ruff', 7.5)
        )
        options = check_script.CheckOptions(tool_timeout_seconds=7.5)

        finding = check_script.run_tool('ruff', ['check'], options)

        assert (finding.status, finding.detail) == (STATUS.ERROR, 'timed out after 7.5s')

    def test_a_type_checker_timeout_is_a_tool_error_not_an_advisory(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(check_script, 'resolve_tool', return_value=['ty'])
        mocker.patch.object(
            check_script.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ty', 120.0)
        )

        finding = check_script.run_type_check(Path('a.py'), check_script.CheckOptions())

        assert (finding.status, finding.detail) == (STATUS.ERROR, 'timed out after 120s')

    @pytest.mark.parametrize('tool', ['ruff', 'ty'])
    def test_a_tool_uvx_cannot_fetch_is_a_tool_error_and_never_runs(
        self, mocker: MockerFixture, tool: str
    ) -> None:
        mocker.patch.object(check_script, 'resolve_tool', return_value=['uvx', f'{tool}@9.9.9'])
        runner = mocker.patch.object(check_script, 'subprocess')
        runner.run.return_value = completed(1, stderr='No solution found when resolving')

        finding = check_script.run_tool(tool, ['check'], check_script.CheckOptions())

        assert finding.status is STATUS.ERROR
        assert finding.detail == (
            f'uvx could not fetch {tool}@9.9.9: No solution found when resolving'
        )
        runner.run.assert_called_once()
        assert runner.run.call_args.args == (['uvx', f'{tool}@9.9.9', '--version'],)

    def test_a_fetched_tool_through_uvx_runs_after_the_probe(self, mocker: MockerFixture) -> None:
        mocker.patch.object(check_script, 'resolve_tool', return_value=['uvx', 'ruff@1.0.0'])
        runner = mocker.patch.object(check_script, 'subprocess')
        runner.run.side_effect = [completed(0, stdout='ruff 1.0.0'), completed(1, stdout='bad')]

        finding = check_script.run_tool('ruff', ['check', 'a.py'], check_script.CheckOptions())

        assert (finding.status, finding.detail) == (STATUS.FAIL, 'bad')
        assert runner.run.call_args.args == (['uvx', 'ruff@1.0.0', 'check', 'a.py'],)

    def test_a_timeout_while_fetching_is_a_tool_error(self, mocker: MockerFixture) -> None:
        mocker.patch.object(check_script, 'resolve_tool', return_value=['uvx', 'ty@1.0.0'])
        mocker.patch.object(
            check_script.subprocess, 'run', side_effect=subprocess.TimeoutExpired('uvx', 5.0)
        )
        options = check_script.CheckOptions(tool_timeout_seconds=5.0)

        finding = check_script.run_tool('ty', ['check'], options)

        assert (finding.status, finding.detail) == (STATUS.ERROR, 'timed out after 5s')


class TestToolFindings:
    def test_a_type_check_failure_is_only_a_warning(self, mocker: MockerFixture) -> None:
        failure = check_script.Finding(check='ty', status=STATUS.FAIL, detail='bad')
        mocker.patch.object(check_script, 'run_tool', return_value=failure)

        finding = check_script.run_type_check(Path('a.py'), check_script.CheckOptions())

        assert finding.status is STATUS.WARN
        assert finding.detail.endswith(': bad')

    @pytest.mark.parametrize('status', [STATUS.PASS, STATUS.SKIP])
    def test_other_type_check_results_pass_through(
        self, mocker: MockerFixture, status: object
    ) -> None:
        result = check_script.Finding(check='ty', status=status, detail='fine')
        mocker.patch.object(check_script, 'run_tool', return_value=result)

        assert check_script.run_type_check(Path('a.py'), check_script.CheckOptions()) is result

    def test_the_type_checker_runs_in_concise_form(self, mocker: MockerFixture) -> None:
        runner = mocker.patch.object(
            check_script,
            'run_tool',
            return_value=check_script.Finding(check='ty', status=STATUS.PASS, detail='clean'),
        )

        check_script.run_type_check(Path('a.py'), check_script.CheckOptions())

        assert runner.call_args.args[:2] == (
            'ty',
            ['check', '--output-format', 'concise', str(Path('a.py').resolve())],
        )

    def test_the_linter_receives_the_resolved_path(self, mocker: MockerFixture) -> None:
        runner = mocker.patch.object(
            check_script,
            'run_tool',
            return_value=check_script.Finding(check='ruff', status=STATUS.PASS, detail='clean'),
        )

        list(check_script.iter_tool_findings(Path('a.py'), check_script.CheckOptions()))

        assert runner.call_args_list[0].args[1][-1] == str(Path('a.py').resolve())

    def test_both_tools_run_when_enabled(self, mocker: MockerFixture) -> None:
        mocker.patch.object(
            check_script,
            'run_tool',
            side_effect=lambda name, *_: check_script.Finding(
                check=name, status=STATUS.PASS, detail='clean'
            ),
        )

        findings = list(check_script.iter_tool_findings(Path('a.py'), check_script.CheckOptions()))

        assert [finding.check for finding in findings] == ['ruff', 'ty']

    def test_nothing_runs_when_tools_are_off(self, mocker: MockerFixture) -> None:
        runner = mocker.patch.object(check_script, 'run_tool')
        options = check_script.CheckOptions(run_tools=False)

        assert list(check_script.iter_tool_findings(Path('a.py'), options)) == []
        runner.assert_not_called()


class TestLoadSource:
    def test_a_readable_script_is_parsed(self, tmp_path: Path) -> None:
        path = tmp_path / 'ok.py'
        path.write_text('x = 1\n', encoding='utf-8')

        source = check_script.try_load_source(path)

        assert source.text == 'x = 1\n'
        assert source.path == path

    def test_a_missing_file_is_returned_as_the_error(self, tmp_path: Path) -> None:
        assert isinstance(check_script.try_load_source(tmp_path / 'absent.py'), OSError)

    def test_a_syntax_error_is_returned_as_the_error(self, tmp_path: Path) -> None:
        path = tmp_path / 'broken.py'
        path.write_text('def (:\n', encoding='utf-8')

        assert isinstance(check_script.try_load_source(path), SyntaxError)


class TestMain:
    def test_a_conforming_script_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / 'good.py'
        path.write_text(GOOD_SCRIPT, encoding='utf-8')

        code = check_script.main([str(path), '--no-tools'])

        output = capsys.readouterr().out.splitlines()
        assert code == check_script.ExitCode.OK == 0
        assert output[-1] == 'ALL REQUIRED CHECKS PASSED'
        assert 'PASS pep723: inline metadata with requires-python' in output
        assert 'SKIP workers: script is sequential' in output

    def test_a_failing_script_exits_one_and_names_the_checks(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / 'bad.py'
        path.write_text('print(1)\n', encoding='utf-8')

        code = check_script.main([str(path), '--no-tools'])

        last_line = capsys.readouterr().out.splitlines()[-1]
        assert code == check_script.ExitCode.FAILED == 1
        assert last_line == 'FAILED: pep723, cli, dry-run, logging, main'

    def test_an_unreadable_script_logs_the_message_only(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        missing = tmp_path / 'absent.py'

        code = check_script.main([str(missing), '--no-tools'])

        (record,) = caplog.records
        assert code == check_script.ExitCode.UNREADABLE == 2
        assert record.getMessage().startswith(f'cannot check {missing}: ')
        assert record.exc_info is None

    def test_a_syntax_error_is_unreadable_too(self, tmp_path: Path) -> None:
        path = tmp_path / 'broken.py'
        path.write_text('def (:\n', encoding='utf-8')

        assert check_script.main([str(path), '--no-tools']) == check_script.ExitCode.UNREADABLE

    def test_a_file_that_is_not_utf8_is_unreadable_too(self, tmp_path: Path) -> None:
        path = tmp_path / 'binary.py'
        path.write_bytes(b'\xff\xfe')

        assert check_script.main([str(path), '--no-tools']) == check_script.ExitCode.UNREADABLE

    def test_a_tool_timeout_keeps_the_structural_lines(
        self, tmp_path: Path, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / 'good.py'
        path.write_text(GOOD_SCRIPT, encoding='utf-8')
        mocker.patch.object(check_script, 'resolve_tool', return_value=['tool'])
        mocker.patch.object(
            check_script.subprocess, 'run', side_effect=subprocess.TimeoutExpired('tool', 120.0)
        )

        code = check_script.main([str(path)])

        output = capsys.readouterr().out.splitlines()
        assert code == check_script.ExitCode.TOOL_ERROR == 3
        assert 'PASS pep723: inline metadata with requires-python' in output
        assert output[-3:] == [
            'ERROR ruff: timed out after 120s',
            'ERROR ty: timed out after 120s',
            'TOOL ERROR: ruff, ty',
        ]

    def test_a_tool_uvx_cannot_fetch_exits_with_the_tool_error_code(
        self, tmp_path: Path, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / 'good.py'
        path.write_text(GOOD_SCRIPT, encoding='utf-8')
        mocker.patch.object(
            check_script, 'resolve_tool', side_effect=lambda tool: ['uvx', f'{tool}@9.9.9']
        )
        mocker.patch.object(
            check_script.subprocess,
            'run',
            return_value=completed(1, stderr='No solution found when resolving'),
        )

        code = check_script.main([str(path)])

        output = capsys.readouterr().out.splitlines()
        assert code == check_script.ExitCode.TOOL_ERROR
        assert (
            'ERROR ruff: uvx could not fetch ruff@9.9.9: No solution found when resolving' in output
        )
        assert 'ERROR ty: uvx could not fetch ty@9.9.9: No solution found when resolving' in output
        assert output[-1] == 'TOOL ERROR: ruff, ty'

    def test_a_failed_check_outranks_a_tool_error(
        self, tmp_path: Path, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / 'bad.py'
        path.write_text('print(1)\n', encoding='utf-8')
        mocker.patch.object(
            check_script,
            'iter_tool_findings',
            return_value=iter(
                [check_script.Finding(check='ruff', status=STATUS.ERROR, detail='x')]
            ),
        )

        code = check_script.main([str(path)])

        assert code == check_script.ExitCode.FAILED
        assert (
            capsys.readouterr().out.splitlines()[-1]
            == 'FAILED: pep723, cli, dry-run, logging, main'
        )

    def test_tool_findings_are_reported_and_a_tool_failure_fails_the_run(
        self, tmp_path: Path, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / 'good.py'
        path.write_text(GOOD_SCRIPT, encoding='utf-8')
        mocker.patch.object(
            check_script,
            'iter_tool_findings',
            return_value=iter([check_script.Finding(check='ruff', status=STATUS.FAIL, detail='x')]),
        )

        code = check_script.main([str(path)])

        output = capsys.readouterr().out.splitlines()
        assert code == check_script.ExitCode.FAILED
        assert output[-2:] == ['FAIL ruff: x', 'FAILED: ruff']

    def test_tools_are_skipped_by_the_no_tools_flag(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        path = tmp_path / 'good.py'
        path.write_text(GOOD_SCRIPT, encoding='utf-8')
        runner = mocker.patch.object(check_script, 'run_tool')

        check_script.main([str(path), '--no-tools'])

        runner.assert_not_called()

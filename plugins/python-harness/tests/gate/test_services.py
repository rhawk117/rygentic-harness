"""Running gate commands: outcomes, output tails, environment, timeouts and leftovers."""

import gc
import os
import signal
import stat
import sys
import time
import warnings
from collections.abc import Iterator
from contextlib import suppress
from types import MappingProxyType

import pytest
from python_harness.core.tests.fixtures import GitProject, ProjectBuilder, stubbed_uv
from python_harness.core.workspace import Workspace, open_workspace
from python_harness.gate.domain import (
    ConfigSource,
    CreatedPaths,
    Exited,
    GateCommand,
    GateOptions,
    GatePlan,
    GateReport,
    GateTool,
    NotTracked,
    TimedOut,
)
from python_harness.gate.errors import LauncherUnavailableError
from python_harness.gate.services import run_gate, run_gate_for
from python_harness.survey.errors import ManifestUnreadableError
from python_harness.survey.services import survey_project

NO_ENVIRONMENT = MappingProxyType({})
POLL_SECONDS = 0.05
RECORD_PID_AND_SLEEP = (
    'import os, pathlib, sys, time; '
    'pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); '
    'time.sleep(60)'
)


def is_gone_within(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(POLL_SECONDS)
    return False


def python_command(tool: GateTool, script: str, *arguments: str) -> GateCommand:
    return GateCommand(tool, sys.executable, ('-c', script, *arguments))


def plan_of(*commands: GateCommand) -> GatePlan:
    return GatePlan(commands, ConfigSource.DEFAULTS, ConfigSource.DEFAULTS)


@pytest.fixture
def workspace(project_builder: ProjectBuilder) -> Workspace:
    return project_builder.write({})


class TestPassAndFail:
    PLAN = plan_of(
        python_command(GateTool.RUFF_CHECK, 'print("All checks passed!")'),
        python_command(
            GateTool.TY,
            'import sys; print("error: unresolved", file=sys.stderr); sys.exit(3)',
        ),
    )
    OUTCOMES = (Exited(0), Exited(3))

    def test_results_keep_plan_order_and_exit_codes(self, workspace: Workspace) -> None:
        report = run_gate(workspace, self.PLAN, environment=NO_ENVIRONMENT)

        assert tuple(item.outcome for item in report.results) == self.OUTCOMES

    def test_report_fails_when_any_command_fails(self, workspace: Workspace) -> None:
        report = run_gate(workspace, self.PLAN, environment=NO_ENVIRONMENT)

        assert (report.passed, report.ruff_config_source, report.ty_config_source) == (
            False,
            ConfigSource.DEFAULTS,
            ConfigSource.DEFAULTS,
        )

    def test_stderr_is_merged_into_the_tail(self, workspace: Workspace) -> None:
        report = run_gate(workspace, self.PLAN, environment=NO_ENVIRONMENT)

        tails = tuple(item.output_tail for item in report.results)
        assert tails == ('All checks passed!', 'error: unresolved')


class TestOutputTail:
    OPTIONS = GateOptions(output_tail_lines=3)
    PLAN = plan_of(
        python_command(GateTool.PYTEST, 'for n in range(100): print(f"line {n}")'),
        python_command(GateTool.TY, 'import os; print(os.getcwd())'),
    )

    def test_only_the_last_lines_are_kept(self, workspace: Workspace) -> None:
        report = run_gate(workspace, self.PLAN, self.OPTIONS, environment=NO_ENVIRONMENT)

        assert report.results[0].output_tail == 'line 97\nline 98\nline 99'

    def test_commands_run_in_the_workspace_root(self, workspace: Workspace) -> None:
        report = run_gate(workspace, self.PLAN, self.OPTIONS, environment=NO_ENVIRONMENT)

        assert report.results[1].output_tail == workspace.root.as_posix()


class TestChildEnvironment:
    PLAN = plan_of(
        python_command(GateTool.TY, 'import os; print(os.getenv("UV"), os.getenv("KEPT"))'),
    )
    PARENT = MappingProxyType({'UV': '/usr/local/bin/uv', 'KEPT': 'yes'})

    def test_the_launchers_uv_variable_does_not_reach_the_projects_tools(
        self, workspace: Workspace
    ) -> None:
        report = run_gate(workspace, self.PLAN, environment=self.PARENT)

        assert report.results[0].output_tail == 'None yes'


class TestProgramResolution:
    LAUNCHER = 'python-harness-test-launcher'
    PLAN = plan_of(GateCommand(GateTool.TY, LAUNCHER, ('check',)))

    @pytest.fixture
    def launcher_directory(self, project_builder: ProjectBuilder) -> str:
        project_builder.write({f'launchers/{self.LAUNCHER}': '#!/bin/sh\necho "$@"\n'})
        launcher = project_builder.root.joinpath('launchers', self.LAUNCHER)
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
        return str(launcher.parent)

    def test_the_program_is_found_on_the_given_path(
        self, workspace: Workspace, launcher_directory: str
    ) -> None:
        environment = MappingProxyType({'PATH': launcher_directory})

        report = run_gate(workspace, self.PLAN, environment=environment)

        assert report.results[0].output_tail == 'check'


class TestMissingProgram:
    MISSING = 'python-harness-test-missing-launcher'
    PLAN = plan_of(
        python_command(GateTool.RUFF_CHECK, 'open("started.flag", "w").close()'),
        GateCommand(GateTool.TY, MISSING, ('ty', 'check')),
    )

    def test_the_error_names_the_missing_program(self, workspace: Workspace) -> None:
        with pytest.raises(LauncherUnavailableError) as caught:
            run_gate(workspace, self.PLAN, environment=NO_ENVIRONMENT)

        assert caught.value.program == self.MISSING

    def test_missing_program_stops_the_gate_before_anything_starts(
        self, workspace: Workspace
    ) -> None:
        with pytest.raises(LauncherUnavailableError):
            run_gate(workspace, self.PLAN, environment=NO_ENVIRONMENT)

        assert not workspace.root.joinpath('started.flag').exists()


class TestTimeout:
    OPTIONS = GateOptions(timeout_seconds=0.5)
    RECORDING_OPTIONS = GateOptions(timeout_seconds=3.0)
    DEADLINE_SECONDS = 15.0
    SLOW_PLAN = plan_of(
        python_command(
            GateTool.PYTEST,
            'import time; print("collecting", flush=True); time.sleep(60)',
        )
    )
    ORPHANING_PLAN = plan_of(
        python_command(
            GateTool.PYTEST,
            'import subprocess, sys; '
            'subprocess.run([sys.executable, "-c", "import time; time.sleep(60)"])',
        )
    )

    def test_slow_command_times_out_and_keeps_its_partial_output(
        self, workspace: Workspace
    ) -> None:
        report = run_gate(workspace, self.SLOW_PLAN, self.OPTIONS, environment=NO_ENVIRONMENT)

        result = report.results[0]
        assert (result.outcome, result.output_tail) == (TimedOut(), 'collecting')

    def test_grandchild_holding_the_output_pipe_is_killed_too(self, workspace: Workspace) -> None:
        started = time.monotonic()
        report = run_gate(workspace, self.ORPHANING_PLAN, self.OPTIONS, environment=NO_ENVIRONMENT)
        elapsed = time.monotonic() - started

        assert report.results[0].timed_out
        assert elapsed < self.DEADLINE_SECONDS

    def test_the_grandchild_process_no_longer_exists_after_the_timeout(
        self, workspace: Workspace
    ) -> None:
        pid_file = workspace.root.joinpath('grandchild.pid')
        plan = plan_of(
            python_command(
                GateTool.PYTEST,
                'import subprocess, sys; '
                'subprocess.run([sys.executable, "-c", sys.argv[1], sys.argv[2]])',
                RECORD_PID_AND_SLEEP,
                str(pid_file),
            )
        )

        report = run_gate(workspace, plan, self.RECORDING_OPTIONS, environment=NO_ENVIRONMENT)

        grandchild = int(pid_file.read_text(encoding='utf-8'))
        try:
            assert report.results[0].timed_out
            assert is_gone_within(grandchild, self.DEADLINE_SECONDS)
        finally:
            with suppress(ProcessLookupError):
                os.kill(grandchild, signal.SIGTERM)


class TestNormalExit:
    DEADLINE_SECONDS = 15.0
    START_DETACHED_GRANDCHILD = (
        'import pathlib, subprocess, sys, time\n'
        'subprocess.Popen(\n'
        '    [sys.executable, "-c", sys.argv[1], sys.argv[2]],\n'
        '    stdout=subprocess.DEVNULL,\n'
        '    stderr=subprocess.DEVNULL,\n'
        ')\n'
        'pid_file = pathlib.Path(sys.argv[2])\n'
        'while not (pid_file.exists() and pid_file.read_text()):\n'
        '    time.sleep(0.05)\n'
    )

    def test_a_grandchild_started_by_a_passing_check_is_gone_after_the_gate_returns(
        self, workspace: Workspace
    ) -> None:
        pid_file = workspace.root.joinpath('grandchild.pid')
        plan = plan_of(
            python_command(
                GateTool.PYTEST,
                self.START_DETACHED_GRANDCHILD,
                RECORD_PID_AND_SLEEP,
                str(pid_file),
            )
        )

        report = run_gate(workspace, plan, environment=NO_ENVIRONMENT)

        grandchild = int(pid_file.read_text(encoding='utf-8'))
        try:
            assert report.results[0].outcome == Exited(0)
            assert is_gone_within(grandchild, self.DEADLINE_SECONDS)
        finally:
            with suppress(ProcessLookupError):
                os.kill(grandchild, signal.SIGTERM)


class TestOutputPipeRelease:
    OPTIONS = GateOptions(timeout_seconds=0.5)
    HOLD_SECONDS = 2
    DETACHED_HOLDER = (
        'import subprocess, sys; '
        'subprocess.Popen([sys.executable, "-c", sys.argv[1]], start_new_session=True)'
    )
    HOLD_THE_PIPE = f'import time; time.sleep({HOLD_SECONDS})'
    GROUP_HOLDER = (
        'import subprocess, sys; '
        'subprocess.run([sys.executable, "-c", "import time; time.sleep(60)"])'
    )

    def resource_warnings_after(
        self, workspace: Workspace, plan: GatePlan, options: GateOptions | None = None
    ) -> list[str]:
        gc.collect()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            run_gate(workspace, plan, options, environment=NO_ENVIRONMENT)
            gc.collect()
        return [str(item.message) for item in caught if issubclass(item.category, ResourceWarning)]

    def test_a_descendant_that_left_the_group_and_holds_the_pipe_leaks_nothing(
        self, workspace: Workspace
    ) -> None:
        plan = plan_of(
            python_command(GateTool.PYTEST, self.DETACHED_HOLDER, self.HOLD_THE_PIPE),
        )

        assert self.resource_warnings_after(workspace, plan, self.OPTIONS) == []

    def test_a_timed_out_command_with_a_child_in_its_group_leaks_nothing(
        self, workspace: Workspace
    ) -> None:
        plan = plan_of(python_command(GateTool.PYTEST, self.GROUP_HOLDER))

        assert self.resource_warnings_after(workspace, plan, self.OPTIONS) == []

    def test_a_command_that_exits_normally_leaks_nothing(self, workspace: Workspace) -> None:
        plan = plan_of(python_command(GateTool.PYTEST, 'print("done")'))

        assert self.resource_warnings_after(workspace, plan) == []


class TestCheckStandardInput:
    OPTIONS = GateOptions(timeout_seconds=5.0)
    SERVER_BYTES = b'client request'
    COPY_STDIN = 'import sys; sys.stdout.write(sys.stdin.read())'

    @pytest.fixture
    def server_stdin(self) -> Iterator[None]:
        saved = os.dup(0)
        read_end, write_end = os.pipe()
        try:
            os.write(write_end, self.SERVER_BYTES)
            os.close(write_end)
            os.dup2(read_end, 0)
            os.close(read_end)
            yield
        finally:
            os.dup2(saved, 0)
            os.close(saved)

    @pytest.mark.usefixtures('server_stdin')
    def test_a_check_reads_the_null_device_and_leaves_the_server_stdin_unread(
        self, workspace: Workspace
    ) -> None:
        plan = plan_of(python_command(GateTool.PYTEST, self.COPY_STDIN))

        report = run_gate(workspace, plan, self.OPTIONS, environment=NO_ENVIRONMENT)

        assert self.SERVER_BYTES.decode() not in report.results[0].output_tail
        assert os.read(0, len(self.SERVER_BYTES)) == self.SERVER_BYTES


class TestConcurrency:
    OPTIONS = GateOptions(timeout_seconds=15.0)
    RENDEZVOUS = (
        'import pathlib, sys, time\n'
        'pathlib.Path(sys.argv[1]).touch()\n'
        'while not pathlib.Path(sys.argv[2]).exists():\n'
        '    time.sleep(0.05)\n'
    )
    PLAN = plan_of(
        python_command(GateTool.RUFF_CHECK, RENDEZVOUS, 'left.flag', 'right.flag'),
        python_command(GateTool.TY, RENDEZVOUS, 'right.flag', 'left.flag'),
    )

    def test_commands_that_wait_for_each_other_both_finish(self, workspace: Workspace) -> None:
        report = run_gate(workspace, self.PLAN, self.OPTIONS, environment=NO_ENVIRONMENT)

        assert report.passed


class TestCreatedPaths:
    PLAN = plan_of(
        python_command(
            GateTool.PYTEST,
            'import pathlib; '
            'pathlib.Path("build").mkdir(); '
            'pathlib.Path("build/report.txt").write_text("x"); '
            'pathlib.Path("notes.txt").write_text("x")',
        )
    )
    PROJECT = MappingProxyType({'service/.gitignore': 'build/\n', 'service/pkg/core.py': 'a = 1\n'})
    CREATED = CreatedPaths(('build/report.txt', 'notes.txt'))

    @pytest.fixture
    def repository_workspace(self, git_project: GitProject) -> Workspace:
        git_project.commit(self.PROJECT, 'base')
        git_project.builder.write({'service/draft.txt': 'already here\n'})
        return open_workspace(git_project.builder.root.joinpath('service'), uv_runner=stubbed_uv)

    def test_files_the_run_creates_are_listed_relative_to_the_workspace(
        self, repository_workspace: Workspace
    ) -> None:
        report = run_gate(repository_workspace, self.PLAN, environment=NO_ENVIRONMENT)

        assert report.created_paths == self.CREATED

    def test_created_files_are_left_in_place(self, repository_workspace: Workspace) -> None:
        run_gate(repository_workspace, self.PLAN, environment=NO_ENVIRONMENT)

        assert repository_workspace.root.joinpath('notes.txt').is_file()

    def test_outside_git_nothing_is_tracked(self, workspace: Workspace) -> None:
        report = run_gate(workspace, self.PLAN, environment=NO_ENVIRONMENT)

        assert report.created_paths == NotTracked()


class TestRuffCheckLeavesFilesAlone:
    SOURCE = 'src/shop/prices.py'
    UNUSED_IMPORT = b'import os\n\n\ndef price(total: int) -> int:\n    return total\n'
    PROJECT = MappingProxyType(
        {
            'pyproject.toml': (
                '[project]\nname = "shop"\nversion = "0"\nrequires-python = ">=3.14"\n'
                '[tool.ruff]\nfix = true\nunsafe-fixes = true\n'
                '[tool.ruff.lint]\nselect = ["F401"]\n'
            ),
            SOURCE: UNUSED_IMPORT.decode(),
        }
    )
    OPTIONS = GateOptions(skipped=frozenset({GateTool.RUFF_FORMAT, GateTool.TY, GateTool.PYTEST}))

    @pytest.fixture
    def checked(self, project_builder: ProjectBuilder) -> tuple[Workspace, GateReport]:
        workspace = project_builder.write(self.PROJECT)
        survey = survey_project(workspace)
        report = run_gate_for(workspace, survey, self.OPTIONS, environment=os.environ)
        return workspace, report

    def test_a_project_config_that_enables_fixes_does_not_change_the_source(
        self, checked: tuple[Workspace, GateReport]
    ) -> None:
        workspace, _ = checked

        assert workspace.root.joinpath(self.SOURCE).read_bytes() == self.UNUSED_IMPORT

    def test_the_violation_is_reported_instead_of_fixed(
        self, checked: tuple[Workspace, GateReport]
    ) -> None:
        _, report = checked

        (result,) = report.results
        assert (result.passed, 'F401' in result.output_tail) == (False, True)


class TestUnreadableManifest:
    UNDECODABLE_PYPROJECT = b'[project]\nname = "caf\xe9"\n'

    @pytest.fixture
    def undecodable_workspace(self, project_builder: ProjectBuilder) -> Workspace:
        workspace = project_builder.write({'pkg/__init__.py': ''})
        workspace.root.joinpath('pyproject.toml').write_bytes(self.UNDECODABLE_PYPROJECT)
        return workspace

    def test_an_undecodable_pyproject_stops_the_gate_with_its_path(
        self, undecodable_workspace: Workspace
    ) -> None:
        with pytest.raises(ManifestUnreadableError) as caught:
            run_gate_for(
                undecodable_workspace,
                survey_project(undecodable_workspace),
                environment=NO_ENVIRONMENT,
            )

        expected = undecodable_workspace.root.joinpath('pyproject.toml')
        assert caught.value.path == expected

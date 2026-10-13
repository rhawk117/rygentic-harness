"""Level and workload mapping of automate-task's parallelism.py."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import parallelism
import pytest
from pytest_mock import MockerFixture

SCRIPT = Path(__file__).resolve().parents[2] / 'skills' / 'automate-task' / 'scripts'

LEVELS = parallelism.Level
WORKLOADS = parallelism.Workload


def read_function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding='utf-8')
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    pytest.fail(f'{path.name} defines no function {name}')


def make_host(
    process_cpus: int = 8, cgroup_cpus: int | None = None, open_file_limit: int = 1024
) -> parallelism.HostFacts:
    return parallelism.HostFacts(
        process_cpus=process_cpus,
        cgroup_cpus=cgroup_cpus,
        open_file_limit=open_file_limit,
        gil_enabled=True,
    )


def make_request(
    workload: str, level: str, requested_workers: int | None = None
) -> parallelism.Request:
    return parallelism.Request(
        workload=WORKLOADS(workload), level=LEVELS(level), requested_workers=requested_workers
    )


class TestHostFacts:
    @pytest.mark.parametrize(
        ('process_cpus', 'cgroup_cpus', 'expected'),
        [(8, None, 8), (8, 2, 2), (2, 8, 2), (4, 0, 1)],
    )
    def test_usable_cpus_are_the_smaller_limit_and_at_least_one(
        self, process_cpus: int, cgroup_cpus: int | None, expected: int
    ) -> None:
        assert make_host(process_cpus, cgroup_cpus).cpus == expected


class TestReadCgroupCpus:
    @pytest.mark.parametrize(
        ('content', 'expected'),
        [('max 100000', None), ('50000', None), ('150000 100000', 2), ('200000 100000', 2)],
    )
    def test_the_quota_is_rounded_up_to_whole_cpus(
        self, tmp_path: Path, content: str, expected: int | None
    ) -> None:
        cpu_max = tmp_path / 'cpu.max'
        cpu_max.write_text(content + '\n', encoding='utf-8')

        assert parallelism.read_cgroup_cpus(cpu_max) == expected

    def test_a_missing_file_means_no_quota(self, tmp_path: Path) -> None:
        assert parallelism.read_cgroup_cpus(tmp_path / 'cpu.max') is None


class TestReadOpenFileLimit:
    def test_windows_gets_a_fixed_limit_without_the_resource_module(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(parallelism, 'sys', SimpleNamespace(platform='win32'))
        resource = mocker.patch.object(parallelism, 'resource', create=True)

        assert parallelism.read_open_file_limit() == 512
        resource.getrlimit.assert_not_called()

    @pytest.mark.parametrize(('soft', 'expected'), [(256, 256), (0, 1024), (-1, 1024)])
    def test_posix_reads_the_soft_descriptor_limit(
        self, mocker: MockerFixture, soft: int, expected: int
    ) -> None:
        mocker.patch.object(parallelism, 'sys', SimpleNamespace(platform='linux'))
        resource = mocker.patch.object(parallelism, 'resource')
        resource.getrlimit.return_value = (soft, 4096)

        assert parallelism.read_open_file_limit() == expected
        resource.getrlimit.assert_called_once_with(resource.RLIMIT_NOFILE)


class TestDetectHost:
    @pytest.fixture
    def quiet_host(self, mocker: MockerFixture) -> None:
        mocker.patch.object(parallelism, 'read_open_file_limit', return_value=2048)
        mocker.patch.object(parallelism, 'read_cgroup_cpus', return_value=2)
        mocker.patch.object(
            parallelism,
            'os',
            SimpleNamespace(process_cpu_count=lambda: 6),
        )

    @pytest.mark.usefixtures('quiet_host')
    def test_detected_values_are_combined(self) -> None:
        host = parallelism.detect_host(None)

        assert (host.process_cpus, host.cgroup_cpus, host.open_file_limit) == (6, 2, 2048)
        assert host.cpus == 2

    @pytest.mark.usefixtures('quiet_host')
    def test_an_override_replaces_detection_and_ignores_the_cgroup(self) -> None:
        host = parallelism.detect_host(3)

        assert (host.process_cpus, host.cgroup_cpus) == (3, None)

    @pytest.mark.usefixtures('quiet_host')
    def test_an_unknown_cpu_count_falls_back_to_one(self, mocker: MockerFixture) -> None:
        mocker.patch.object(parallelism, 'os', SimpleNamespace(process_cpu_count=lambda: None))

        assert parallelism.detect_host(None).process_cpus == 1

    @pytest.mark.parametrize(
        ('probe', 'expected'),
        [(None, True), (lambda: True, True), (lambda: False, False)],
    )
    @pytest.mark.usefixtures('quiet_host')
    def test_the_gil_probe_decides_gil_state(
        self, mocker: MockerFixture, probe: object, expected: object
    ) -> None:
        facts = {} if probe is None else {'_is_gil_enabled': probe}
        mocker.patch.object(parallelism, 'sys', SimpleNamespace(platform='linux', **facts))

        assert parallelism.detect_host(None).gil_enabled is expected


class TestWorkerCounts:
    @pytest.mark.parametrize(
        ('level', 'expected'),
        [('sequential', 1), ('moderate', 4), ('a-lot', 7), ('toaster', 8)],
    )
    def test_cpu_workers_follow_the_level(self, level: str, expected: int) -> None:
        assert parallelism.compute_cpu_workers(LEVELS(level), 8) == expected

    def test_cpu_workers_never_drop_below_one(self) -> None:
        assert parallelism.compute_cpu_workers(LEVELS.A_LOT, 1) == 1

    @pytest.mark.parametrize(
        ('level', 'cpus', 'expected'),
        [('sequential', 8, 1), ('moderate', 8, 4), ('moderate', 2, 2), ('a-lot', 8, 8)],
    )
    def test_subprocess_workers_follow_the_level(
        self, level: str, cpus: int, expected: int
    ) -> None:
        assert parallelism.compute_subprocess_workers(LEVELS(level), cpus) == expected

    @pytest.mark.parametrize(
        ('open_file_limit', 'expected'), [(1024, 256), (4096, 256), (64, 16), (2, 1)]
    )
    def test_the_io_ceiling_is_limited_by_descriptors(
        self, open_file_limit: int, expected: int
    ) -> None:
        host = make_host(open_file_limit=open_file_limit)

        assert parallelism.compute_io_ceiling(host, parallelism.CapOptions()) == expected

    @pytest.mark.parametrize(
        ('level', 'open_file_limit', 'expected'),
        [
            ('sequential', 1024, 1),
            ('moderate', 1024, 8),
            ('a-lot', 1024, 32),
            ('toaster', 1024, 256),
            ('a-lot', 64, 16),
        ],
    )
    def test_io_in_flight_is_capped_by_the_ceiling(
        self, level: str, open_file_limit: int, expected: int
    ) -> None:
        host = make_host(open_file_limit=open_file_limit)

        result = parallelism.compute_io_in_flight(LEVELS(level), host, parallelism.CapOptions())

        assert result == expected

    @pytest.mark.parametrize(
        ('level', 'expected'), [('sequential', None), ('moderate', 4), ('toaster', 8)]
    )
    def test_library_threads_follow_the_level(self, level: str, expected: int | None) -> None:
        assert parallelism.compute_library_threads(LEVELS(level), 8) == expected

    @pytest.mark.parametrize(
        ('workload', 'expected'),
        [('cpu', 4), ('subprocess', 4), ('io', 8), ('library', 1)],
    )
    def test_mapped_workers_depend_on_the_workload_kind(self, workload: str, expected: int) -> None:
        request = make_request(workload, 'moderate')

        assert parallelism.compute_mapped_workers(request, make_host()) == expected


class TestMechanismHint:
    @pytest.mark.parametrize(
        ('workload', 'fragment'),
        [
            ('cpu', 'ProcessPoolExecutor'),
            ('subprocess', 'create_subprocess_exec'),
            ('io', 'Semaphore'),
            ('library', 'library-internal threads'),
        ],
    )
    def test_each_workload_has_its_hint(self, workload: str, fragment: str) -> None:
        hint = parallelism.describe_mechanism(WORKLOADS(workload), make_host())

        assert fragment in hint

    def test_a_free_threaded_build_uses_threads_for_cpu_work(self) -> None:
        host = parallelism.HostFacts(
            process_cpus=4, cgroup_cpus=None, open_file_limit=1024, gil_enabled=False
        )

        hint = parallelism.describe_mechanism(WORKLOADS.CPU, host)

        assert hint == 'threads (free-threaded, no GIL)'


class TestBuildPlan:
    def test_a_moderate_cpu_plan_is_niced(self) -> None:
        plan = parallelism.build_plan(make_request('cpu', 'moderate'), make_host())

        assert (plan.outer_workers, plan.nice, plan.per_host_limit) == (4, 10, None)
        assert plan.explicit_override is False
        assert plan.library_threads is None
        assert plan.warnings == []

    def test_an_io_plan_carries_the_per_host_limit_and_no_nice(self) -> None:
        plan = parallelism.build_plan(make_request('io', 'moderate'), make_host())

        assert (plan.outer_workers, plan.nice, plan.per_host_limit) == (8, 0, 6)

    def test_a_library_plan_keeps_one_outer_worker(self) -> None:
        plan = parallelism.build_plan(make_request('library', 'toaster'), make_host())

        assert (plan.outer_workers, plan.library_threads) == (1, 8)

    def test_host_facts_are_copied_into_the_plan(self) -> None:
        plan = parallelism.build_plan(make_request('cpu', 'a-lot'), make_host(8, 4, 512))

        assert (plan.cpus, plan.process_cpus, plan.cgroup_cpus) == (4, 8, 4)
        assert (plan.open_file_limit, plan.gil_enabled, plan.outer_workers) == (512, True, 3)

    def test_an_explicit_count_above_the_cpu_count_is_kept_with_a_warning(self) -> None:
        plan = parallelism.build_plan(make_request('cpu', 'moderate', 20), make_host())

        assert plan.outer_workers == 20
        assert plan.explicit_override is True
        assert len(plan.warnings) == 1
        assert '20 workers exceeds 8 usable CPUs' in plan.warnings[0]

    def test_an_explicit_io_count_above_the_ceiling_is_kept_with_a_warning(self) -> None:
        plan = parallelism.build_plan(make_request('io', 'a-lot', 300), make_host())

        assert plan.outer_workers == 300
        assert '300 in flight exceeds the open-file ceiling of 256' in plan.warnings[0]

    def test_an_explicit_library_count_raises_no_warning(self) -> None:
        plan = parallelism.build_plan(make_request('library', 'moderate', 50), make_host())

        assert plan.warnings == []


class TestParsePositiveInt:
    def test_a_positive_number_is_accepted(self) -> None:
        assert parallelism.parse_positive_int('3') == 3

    @pytest.mark.parametrize('text', ['0', '-2'])
    def test_zero_and_negative_numbers_are_rejected(self, text: str) -> None:
        with pytest.raises(parallelism.argparse.ArgumentTypeError):
            parallelism.parse_positive_int(text)

    def test_the_script_template_carries_the_same_function(self) -> None:
        script = read_function_source(SCRIPT / 'parallelism.py', 'parse_positive_int')
        template = read_function_source(
            SCRIPT.parent / 'assets' / 'script.template.py', 'parse_positive_int'
        )

        assert script == template


class TestMain:
    def test_the_plan_is_printed_as_json_and_the_exit_code_is_zero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = parallelism.main(['--workload', 'cpu', '--level', 'moderate', '--cpus', '8'])

        plan = json.loads(capsys.readouterr().out)
        assert code == parallelism.ExitCode.OK == 0
        assert plan['workload'] == 'cpu'
        assert plan['level'] == 'moderate'
        assert (plan['cpus'], plan['outer_workers'], plan['nice']) == (8, 4, 10)
        assert plan['cgroup_cpus'] is None
        assert plan['warnings'] == []

    def test_an_explicit_count_prints_a_warning_on_the_log_only(
        self, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
    ) -> None:
        argv = ['--workload', 'cpu', '--level', 'a-lot', '--cpus', '4', '--requested-workers', '9']

        code = parallelism.main(argv)

        plan = json.loads(capsys.readouterr().out)
        assert code == parallelism.ExitCode.OK
        assert plan['outer_workers'] == 9
        assert plan['warnings']
        assert plan['warnings'] == [record.getMessage() for record in caplog.records]

    def test_the_per_host_limit_flows_into_an_io_plan(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = ['--workload', 'io', '--level', 'sequential', '--per-host-limit', '3']

        parallelism.main(argv)

        assert json.loads(capsys.readouterr().out)['per_host_limit'] == 3

    @pytest.mark.parametrize(
        'argv',
        [
            ['--workload', 'gpu', '--level', 'moderate'],
            ['--workload', 'cpu', '--level', 'turbo'],
            ['--workload', 'cpu'],
            ['--workload', 'cpu', '--level', 'moderate', '--cpus', '0'],
        ],
    )
    def test_invalid_arguments_exit_with_a_usage_error(self, argv: list[str]) -> None:
        with pytest.raises(SystemExit) as caught:
            parallelism.main(argv)

        assert caught.value.code == 2

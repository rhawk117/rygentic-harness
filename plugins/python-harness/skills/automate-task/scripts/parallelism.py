# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Translate a parallelism level and workload kind into concrete concurrency settings.

Prints one JSON object on stdout so every automate-task run maps "moderate", "a lot" and
"turn my computer into a toaster" to the same numbers on the same host.
"""

import argparse
import json
import logging
import math
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path

if sys.platform != 'win32':
    import resource

logger = logging.getLogger(__name__)


class Workload(StrEnum):
    CPU = 'cpu'
    SUBPROCESS = 'subprocess'
    IO = 'io'
    LIBRARY = 'library'


class Level(StrEnum):
    SEQUENTIAL = 'sequential'
    MODERATE = 'moderate'
    A_LOT = 'a-lot'
    TOASTER = 'toaster'


class ExitCode(IntEnum):
    OK = 0


@dataclass(slots=True, kw_only=True, frozen=True)
class HostFacts:
    process_cpus: int
    cgroup_cpus: int | None
    open_file_limit: int
    gil_enabled: bool

    @property
    def cpus(self) -> int:
        if self.cgroup_cpus is None:
            return self.process_cpus
        return max(1, min(self.process_cpus, self.cgroup_cpus))


@dataclass(slots=True, kw_only=True, frozen=True)
class CapOptions:
    per_host_limit: int = 6
    io_moderate: int = 8
    io_a_lot: int = 32
    io_toaster_ceiling: int = 256
    descriptors_per_task: int = 4
    comfort_nice: int = 10


@dataclass(slots=True, kw_only=True, frozen=True)
class Request:
    workload: Workload
    level: Level
    requested_workers: int | None
    caps: CapOptions = field(default_factory=CapOptions)


@dataclass(slots=True, kw_only=True, frozen=True)
class Plan:
    workload: Workload
    level: Level
    cpus: int
    process_cpus: int
    cgroup_cpus: int | None
    gil_enabled: bool
    open_file_limit: int
    outer_workers: int
    library_threads: int | None
    nice: int
    per_host_limit: int | None
    mechanism_hint: str
    explicit_override: bool
    warnings: list[str]


def read_cgroup_cpus(cpu_max: Path) -> int | None:
    if not cpu_max.is_file():
        return None
    quota, _, period = cpu_max.read_text(encoding='utf-8').strip().partition(' ')
    if quota == 'max' or not period:
        return None
    return math.ceil(int(quota) / int(period))


def read_open_file_limit() -> int:
    if sys.platform == 'win32':
        return 512
    soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    return soft if soft > 0 else 1024


def detect_host(cpus_override: int | None) -> HostFacts:
    gil_probe = getattr(sys, '_is_gil_enabled', None)
    return HostFacts(
        process_cpus=cpus_override or os.process_cpu_count() or 1,
        cgroup_cpus=None if cpus_override else read_cgroup_cpus(Path('/sys/fs/cgroup/cpu.max')),
        open_file_limit=read_open_file_limit(),
        gil_enabled=True if gil_probe is None else bool(gil_probe()),
    )


def compute_cpu_workers(level: Level, cpus: int) -> int:
    table = {
        Level.SEQUENTIAL: 1,
        Level.MODERATE: max(1, cpus // 2),
        Level.A_LOT: max(1, cpus - 1),
        Level.TOASTER: cpus,
    }
    return table[level]


def compute_subprocess_workers(level: Level, cpus: int) -> int:
    table = {
        Level.SEQUENTIAL: 1,
        Level.MODERATE: max(2, cpus // 2),
        Level.A_LOT: cpus,
        Level.TOASTER: cpus,
    }
    return table[level]


def compute_io_ceiling(host: HostFacts, caps: CapOptions) -> int:
    return max(1, min(caps.io_toaster_ceiling, host.open_file_limit // caps.descriptors_per_task))


def compute_io_in_flight(level: Level, host: HostFacts, caps: CapOptions) -> int:
    table = {
        Level.SEQUENTIAL: 1,
        Level.MODERATE: caps.io_moderate,
        Level.A_LOT: caps.io_a_lot,
        Level.TOASTER: compute_io_ceiling(host, caps),
    }
    return min(table[level], compute_io_ceiling(host, caps))


def compute_library_threads(level: Level, cpus: int) -> int | None:
    if level is Level.SEQUENTIAL:
        return None
    return compute_cpu_workers(level, cpus)


def describe_mechanism(workload: Workload, host: HostFacts) -> str:
    cpu_hint = 'ProcessPoolExecutor' if host.gil_enabled else 'threads (free-threaded, no GIL)'
    hints = {
        Workload.CPU: cpu_hint,
        Workload.SUBPROCESS: 'ThreadPoolExecutor or asyncio.create_subprocess_exec',
        Workload.IO: 'asyncio with a Semaphore, or ThreadPoolExecutor for sync clients',
        Workload.LIBRARY: 'library-internal threads; keep the outer pool at 1',
    }
    return hints[workload]


def compute_mapped_workers(request: Request, host: HostFacts) -> int:
    level, cpus = request.level, host.cpus
    table = {
        Workload.CPU: compute_cpu_workers(level, cpus),
        Workload.SUBPROCESS: compute_subprocess_workers(level, cpus),
        Workload.IO: compute_io_in_flight(level, host, request.caps),
        Workload.LIBRARY: 1,
    }
    return table[request.workload]


def find_override_warnings(request: Request, host: HostFacts, workers: int) -> list[str]:
    warnings: list[str] = []
    io_ceiling = compute_io_ceiling(host, request.caps)
    if request.workload is Workload.IO and workers > io_ceiling:
        warnings.append(
            f'{workers} in flight exceeds the open-file ceiling of {io_ceiling}; '
            'kept as requested, expect EMFILE errors unless the limit is raised'
        )
    cpu_bound = request.workload in {Workload.CPU, Workload.SUBPROCESS}
    if cpu_bound and workers > host.cpus:
        warnings.append(
            f'{workers} workers exceeds {host.cpus} usable CPUs; kept as requested, '
            'extra workers will contend for the same cores'
        )
    return warnings


def compute_library_plan_threads(request: Request, host: HostFacts) -> int | None:
    if request.workload is not Workload.LIBRARY:
        return None
    return compute_library_threads(request.level, host.cpus)


def build_plan(request: Request, host: HostFacts) -> Plan:
    workers = request.requested_workers or compute_mapped_workers(request, host)
    comfort = request.level is Level.MODERATE and request.workload is not Workload.IO
    uses_hosts = request.workload is Workload.IO
    return Plan(
        workload=request.workload,
        level=request.level,
        cpus=host.cpus,
        process_cpus=host.process_cpus,
        cgroup_cpus=host.cgroup_cpus,
        gil_enabled=host.gil_enabled,
        open_file_limit=host.open_file_limit,
        outer_workers=workers,
        library_threads=compute_library_plan_threads(request, host),
        nice=request.caps.comfort_nice if comfort else 0,
        per_host_limit=request.caps.per_host_limit if uses_hosts else None,
        mechanism_hint=describe_mechanism(request.workload, host),
        explicit_override=request.requested_workers is not None,
        warnings=find_override_warnings(request, host, workers),
    )


def parse_positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        message = f'expected a positive integer, got {text}'
        raise argparse.ArgumentTypeError(message)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workload', type=Workload, choices=list(Workload), required=True)
    parser.add_argument('--level', type=Level, choices=list(Level), required=True)
    parser.add_argument(
        '--requested-workers',
        type=parse_positive_int,
        help='an explicit count the user asked for; kept even above caps, with warnings',
    )
    parser.add_argument('--per-host-limit', type=parse_positive_int, default=6)
    parser.add_argument('--cpus', type=parse_positive_int, help='override detected CPUs')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')
    request = Request(
        workload=arguments.workload,
        level=arguments.level,
        requested_workers=arguments.requested_workers,
        caps=CapOptions(per_host_limit=arguments.per_host_limit),
    )
    plan = build_plan(request, detect_host(arguments.cpus))
    for warning in plan.warnings:
        logger.warning('%s', warning)
    sys.stdout.write(json.dumps(asdict(plan), indent=2) + '\n')
    return ExitCode.OK


if __name__ == '__main__':
    raise SystemExit(main())

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
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path

if sys.platform != 'win32':
    import resource

logger = logging.getLogger(__name__)

DEFAULT_PER_HOST_LIMIT = 6
WINDOWS_OPEN_FILE_LIMIT = 512
UNLIMITED_OPEN_FILE_FALLBACK = 1024


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
    per_host_limit: int = DEFAULT_PER_HOST_LIMIT
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
        return WINDOWS_OPEN_FILE_LIMIT
    soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    return soft if soft > 0 else UNLIMITED_OPEN_FILE_FALLBACK


def detect_host(cpus_override: int | None) -> HostFacts:
    gil_probe = getattr(sys, '_is_gil_enabled', None)
    return HostFacts(
        process_cpus=cpus_override or os.process_cpu_count() or 1,
        cgroup_cpus=None if cpus_override else read_cgroup_cpus(Path('/sys/fs/cgroup/cpu.max')),
        open_file_limit=read_open_file_limit(),
        gil_enabled=True if gil_probe is None else bool(gil_probe()),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class LevelRule:
    cpu_workers: Callable[[int], int]
    subprocess_workers: Callable[[int], int]
    io_in_flight: Callable[[CapOptions, int], int]
    has_library_threads: bool
    niced: bool


LEVEL_RULES = {
    Level.SEQUENTIAL: LevelRule(
        cpu_workers=lambda _cpus: 1,
        subprocess_workers=lambda _cpus: 1,
        io_in_flight=lambda _caps, _ceiling: 1,
        has_library_threads=False,
        niced=False,
    ),
    Level.MODERATE: LevelRule(
        cpu_workers=lambda cpus: max(1, cpus // 2),
        subprocess_workers=lambda cpus: max(2, cpus // 2),
        io_in_flight=lambda caps, _ceiling: caps.io_moderate,
        has_library_threads=True,
        niced=True,
    ),
    Level.A_LOT: LevelRule(
        cpu_workers=lambda cpus: max(1, cpus - 1),
        subprocess_workers=lambda cpus: cpus,
        io_in_flight=lambda caps, _ceiling: caps.io_a_lot,
        has_library_threads=True,
        niced=False,
    ),
    Level.TOASTER: LevelRule(
        cpu_workers=lambda cpus: cpus,
        subprocess_workers=lambda cpus: cpus,
        io_in_flight=lambda _caps, ceiling: ceiling,
        has_library_threads=True,
        niced=False,
    ),
}


def compute_cpu_workers(level: Level, cpus: int) -> int:
    return LEVEL_RULES[level].cpu_workers(cpus)


def compute_subprocess_workers(level: Level, cpus: int) -> int:
    return LEVEL_RULES[level].subprocess_workers(cpus)


def compute_io_ceiling(host: HostFacts, caps: CapOptions) -> int:
    return max(1, min(caps.io_toaster_ceiling, host.open_file_limit // caps.descriptors_per_task))


def compute_io_in_flight(level: Level, host: HostFacts, caps: CapOptions) -> int:
    ceiling = compute_io_ceiling(host, caps)
    return min(LEVEL_RULES[level].io_in_flight(caps, ceiling), ceiling)


def compute_library_threads(level: Level, cpus: int) -> int | None:
    rule = LEVEL_RULES[level]
    return rule.cpu_workers(cpus) if rule.has_library_threads else None


@dataclass(slots=True, kw_only=True, frozen=True)
class WorkloadRule:
    mapped_workers: Callable[[Request, HostFacts], int]
    mechanism_hint: Callable[[HostFacts], str]
    cpu_bound: bool
    io_bound: bool
    has_library_threads: bool


WORKLOAD_RULES = {
    Workload.CPU: WorkloadRule(
        mapped_workers=lambda request, host: compute_cpu_workers(request.level, host.cpus),
        mechanism_hint=lambda host: (
            'ProcessPoolExecutor' if host.gil_enabled else 'threads (free-threaded, no GIL)'
        ),
        cpu_bound=True,
        io_bound=False,
        has_library_threads=False,
    ),
    Workload.SUBPROCESS: WorkloadRule(
        mapped_workers=lambda request, host: compute_subprocess_workers(request.level, host.cpus),
        mechanism_hint=lambda _host: 'ThreadPoolExecutor or asyncio.create_subprocess_exec',
        cpu_bound=True,
        io_bound=False,
        has_library_threads=False,
    ),
    Workload.IO: WorkloadRule(
        mapped_workers=lambda request, host: compute_io_in_flight(
            request.level, host, request.caps
        ),
        mechanism_hint=lambda _host: (
            'asyncio with a Semaphore, or ThreadPoolExecutor for sync clients'
        ),
        cpu_bound=False,
        io_bound=True,
        has_library_threads=False,
    ),
    Workload.LIBRARY: WorkloadRule(
        mapped_workers=lambda _request, _host: 1,
        mechanism_hint=lambda _host: 'library-internal threads; keep the outer pool at 1',
        cpu_bound=False,
        io_bound=False,
        has_library_threads=True,
    ),
}


def describe_mechanism(workload: Workload, host: HostFacts) -> str:
    return WORKLOAD_RULES[workload].mechanism_hint(host)


def compute_mapped_workers(request: Request, host: HostFacts) -> int:
    return WORKLOAD_RULES[request.workload].mapped_workers(request, host)


def find_override_warnings(request: Request, host: HostFacts, workers: int) -> list[str]:
    warnings: list[str] = []
    rule = WORKLOAD_RULES[request.workload]
    io_ceiling = compute_io_ceiling(host, request.caps)
    if rule.io_bound and workers > io_ceiling:
        warnings.append(
            f'{workers} in flight exceeds the open-file ceiling of {io_ceiling}; '
            'kept as requested, expect EMFILE errors unless the limit is raised'
        )
    if rule.cpu_bound and workers > host.cpus:
        warnings.append(
            f'{workers} workers exceeds {host.cpus} usable CPUs; kept as requested, '
            'extra workers will contend for the same cores'
        )
    return warnings


def build_plan(request: Request, host: HostFacts) -> Plan:
    workload_rule = WORKLOAD_RULES[request.workload]
    workers = request.requested_workers or compute_mapped_workers(request, host)
    comfort = LEVEL_RULES[request.level].niced and not workload_rule.io_bound
    library_threads = (
        compute_library_threads(request.level, host.cpus)
        if workload_rule.has_library_threads
        else None
    )
    return Plan(
        workload=request.workload,
        level=request.level,
        cpus=host.cpus,
        process_cpus=host.process_cpus,
        cgroup_cpus=host.cgroup_cpus,
        gil_enabled=host.gil_enabled,
        open_file_limit=host.open_file_limit,
        outer_workers=workers,
        library_threads=library_threads,
        nice=request.caps.comfort_nice if comfort else 0,
        per_host_limit=request.caps.per_host_limit if workload_rule.io_bound else None,
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
    parser.add_argument('--per-host-limit', type=parse_positive_int, default=DEFAULT_PER_HOST_LIMIT)
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

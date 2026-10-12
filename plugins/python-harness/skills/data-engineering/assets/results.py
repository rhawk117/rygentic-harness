"""Typed analysis results and a publication boundary that writes its manifest last."""

import hashlib
import platform
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum, auto
from importlib.metadata import PackageNotFoundError, version
from math import isfinite
from pathlib import Path
from typing import Protocol, runtime_checkable

import msgspec
import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION = 1

type ParameterValue = str | int | float | bool | None


class DataKind(StrEnum):
    SYNTHETIC = auto()
    PUBLIC = auto()
    PROVIDED = auto()


class Interval(msgspec.Struct, frozen=True, kw_only=True):
    lower: float
    upper: float
    level: float
    method: str


class Metric(msgspec.Struct, frozen=True, kw_only=True, omit_defaults=True):
    name: str
    value: float
    unit: str
    n: int | None = None
    interval: Interval | None = None


class InputRef(msgspec.Struct, frozen=True, kw_only=True):
    name: str
    sha256: str


class AnalysisReport(msgspec.Struct, frozen=True, kw_only=True):
    run_id: str
    created_at: datetime
    data_kind: DataKind
    inputs: tuple[InputRef, ...]
    parameters: dict[str, ParameterValue]
    metrics: tuple[Metric, ...]
    checks: tuple[str, ...]
    issues: tuple[str, ...] = ()


class Environment(msgspec.Struct, frozen=True, kw_only=True):
    python: str
    packages: dict[str, str]


class PublishedMetrics(msgspec.Struct, frozen=True, kw_only=True):
    schema_version: int
    report: AnalysisReport
    environment: Environment


class Artifact(msgspec.Struct, frozen=True, kw_only=True):
    path: str
    bytes: int
    sha256: str


class Manifest(msgspec.Struct, frozen=True, kw_only=True):
    schema_version: int
    run_id: str
    publication_status: str
    artifacts: tuple[Artifact, ...]


class NonFiniteMetricError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f'metric {name!r} has a nonfinite value or interval bound')


class InvalidIntervalError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f'metric {name!r} needs lower <= upper and a level in (0, 1)')


class IncompleteMetricError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f'metric {name!r} needs a name, a unit, and a nonnegative n')


class NaiveTimestampError(ValueError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f'report {run_id!r} needs a UTC-aware created_at')


class MissingInputsError(ValueError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f'report {run_id!r} records no inputs or generator specification')


class DuplicateMetricError(ValueError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f'report {run_id!r} repeats a metric name')


@runtime_checkable
class ArrowTable(Protocol):
    def __arrow_c_stream__(self, requested_schema: object | None = None) -> object: ...


@runtime_checkable
class SavesFigure(Protocol):
    def savefig(self, fname: Path, **kwargs: object) -> None: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class Bundle:
    report: AnalysisReport
    table: ArrowTable
    narrative: str
    figure: SavesFigure | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicationOptions:
    packages: tuple[str, ...] = ('msgspec', 'pyarrow')
    metrics_name: str = 'metrics.json'
    table_name: str = 'table.parquet'
    narrative_name: str = 'report.md'
    figure_name: str = 'figure.svg'
    manifest_name: str = 'manifest.json'

    @property
    def staging_name(self) -> str:
        return f'.{self.manifest_name}.tmp'


def is_incomplete(metric: Metric) -> bool:
    has_negative_n = metric.n is not None and metric.n < 0
    return not metric.name or not metric.unit or has_negative_n


def find_metric_violation(metric: Metric) -> ValueError | None:
    bounds = () if metric.interval is None else (metric.interval.lower, metric.interval.upper)
    if not all(map(isfinite, (metric.value, *bounds))):
        return NonFiniteMetricError(metric.name)
    if is_incomplete(metric):
        return IncompleteMetricError(metric.name)
    interval = metric.interval
    valid = interval is None or (interval.lower <= interval.upper and 0 < interval.level < 1)
    return None if valid else InvalidIntervalError(metric.name)


def find_report_violation(report: AnalysisReport) -> ValueError | None:
    if report.created_at.utcoffset() != timedelta(0):
        return NaiveTimestampError(report.run_id)
    if not report.inputs:
        return MissingInputsError(report.run_id)
    names = [metric.name for metric in report.metrics]
    if len(names) != len(set(names)):
        return DuplicateMetricError(report.run_id)
    return next(filter(None, map(find_metric_violation, report.metrics)), None)


def file_sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def installed_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return 'not installed'


def describe_environment(options: PublicationOptions) -> Environment:
    return Environment(
        python=platform.python_version(),
        packages={package: installed_version(package) for package in options.packages},
    )


def write_artifacts(
    directory: Path, bundle: Bundle, options: PublicationOptions
) -> tuple[str, ...]:
    published = PublishedMetrics(
        schema_version=SCHEMA_VERSION,
        report=bundle.report,
        environment=describe_environment(options),
    )
    directory.joinpath(options.metrics_name).write_bytes(msgspec.json.encode(published))
    pq.write_table(pa.table(bundle.table), directory.joinpath(options.table_name))
    directory.joinpath(options.narrative_name).write_text(bundle.narrative, encoding='utf-8')
    names = (options.metrics_name, options.table_name, options.narrative_name)
    if bundle.figure is None:
        return names
    bundle.figure.savefig(directory.joinpath(options.figure_name), bbox_inches='tight')
    return (*names, options.figure_name)


def describe_artifact(directory: Path, name: str) -> Artifact:
    path = directory.joinpath(name)
    return Artifact(path=name, bytes=path.stat().st_size, sha256=file_sha256(path))


def write_manifest(
    directory: Path, run_id: str, names: tuple[str, ...], *, options: PublicationOptions
) -> Path:
    manifest = Manifest(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        publication_status='complete',
        artifacts=tuple(describe_artifact(directory, name) for name in names),
    )
    staging = directory.joinpath(options.staging_name)
    staging.write_bytes(msgspec.json.encode(manifest))
    return staging.replace(directory.joinpath(options.manifest_name))


def publish_bundle(
    directory: Path, bundle: Bundle, options: PublicationOptions | None = None
) -> Path:
    chosen = options or PublicationOptions()
    if violation := find_report_violation(bundle.report):
        raise violation
    directory.mkdir(parents=True, exist_ok=False)
    names = write_artifacts(directory, bundle, chosen)
    return write_manifest(directory, bundle.report.run_id, names, options=chosen)

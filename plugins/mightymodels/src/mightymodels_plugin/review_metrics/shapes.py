"""What `mightymodels review-metrics` measures and reports, and the limits it holds code to.

`FunctionMetric` and `FileMetric` are what the sources stage measures for one function and one
file. The nine `msgspec.Struct` types are the report as it is written: a struct's field order is
the key order of its JSON object, so `SummaryReport` goes to the codec as it stands.
"""

from dataclasses import dataclass

import msgspec

LINE_LIMIT = 120
FUNCTION_LOC_LIMIT = 20
PARAM_LIMIT = 3
FILE_LOC_LIMIT = 500
DEPTH_LIMIT = 2

type Graph = dict[str, set[str]]


@dataclass(slots=True, kw_only=True, frozen=True)
class FunctionMetric:
    file: str
    name: str
    line: int
    loc: int
    params: int
    bool_params: int
    max_depth: int
    approximate: bool = False


@dataclass(slots=True, kw_only=True, frozen=True)
class FileMetric:
    path: str
    language: str
    loc: int
    long_lines: int
    classes: int = 0
    abstract_classes: int = 0
    is_test: bool = False
    functions: tuple[FunctionMetric, ...] = ()
    imports: tuple[str, ...] = ()


@dataclass(slots=True, kw_only=True, frozen=True)
class SummaryOptions:
    cap: int = 50
    depth: int = 1


DEFAULT_SUMMARY_OPTIONS = SummaryOptions()


class PackageMetric(msgspec.Struct, frozen=True, kw_only=True):
    modules: int
    classes: int
    abstract_classes: int
    loc: int
    fan_in_ca: int
    fan_out_ce: int
    instability_i: float | None
    abstractness_a: float | None
    distance_d: float | None


class PackageReport(msgspec.Struct, frozen=True, kw_only=True):
    packages: dict[str, PackageMetric]
    package_cycles: list[list[str]]


class Violation(msgspec.Struct, frozen=True, kw_only=True):
    file: str
    name: str
    line: int
    loc: int
    params: int
    bool_params: int
    max_depth: int
    approximate: bool


class ViolationGroup(msgspec.Struct, frozen=True, kw_only=True):
    count: int
    worst: list[Violation]


class FileViolation(msgspec.Struct, frozen=True, kw_only=True):
    file: str
    loc: int


class Violations(msgspec.Struct, frozen=True, kw_only=True):
    functions_over_20_loc: ViolationGroup
    functions_over_3_params: ViolationGroup
    functions_with_bool_params: ViolationGroup
    functions_nested_deeper_than_2: ViolationGroup
    files_over_500_loc: list[FileViolation]
    long_lines_over_120_chars: int


class Totals(msgspec.Struct, frozen=True, kw_only=True):
    files: int
    source_files: int
    test_files: int
    source_loc: int
    test_loc: int
    test_to_source_ratio: float | None
    functions_measured: int
    loc_by_language: dict[str, int]


class ModuleCycles(msgspec.Struct, frozen=True, kw_only=True):
    count: int
    cycles: list[list[str]]


class SummaryReport(msgspec.Struct, frozen=True, kw_only=True):
    tool: str
    granularity_note: str
    totals: Totals
    component_metrics: PackageReport
    module_cycles_adp: ModuleCycles
    violations: Violations

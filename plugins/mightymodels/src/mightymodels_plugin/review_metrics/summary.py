"""The report: what breaks a limit, the totals, and the summary a reader sees on standard output.

A rule pairs one measure of a function with the limit it is held to. Each group counts every
function over its limit and lists the worst of them, at most `cap`. `summarize` assembles the
whole report and `render_summary` prints its headline numbers and one row per package.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from mightymodels_plugin.review_metrics.components import package_metrics, tarjan_sccs
from mightymodels_plugin.review_metrics.shapes import (
    DEFAULT_SUMMARY_OPTIONS,
    DEPTH_LIMIT,
    FILE_LOC_LIMIT,
    FUNCTION_LOC_LIMIT,
    LINE_LIMIT,
    PARAM_LIMIT,
    FileMetric,
    FileViolation,
    FunctionMetric,
    Graph,
    ModuleCycles,
    SummaryOptions,
    SummaryReport,
    Totals,
    Violation,
    ViolationGroup,
    Violations,
)


def function_loc(function: FunctionMetric) -> int:
    return function.loc


def function_params(function: FunctionMetric) -> int:
    return function.params


def function_bool_params(function: FunctionMetric) -> int:
    return function.bool_params


def function_depth(function: FunctionMetric) -> int:
    return function.max_depth


def file_loc(metric: FileMetric) -> int:
    return metric.loc


def violation(function: FunctionMetric) -> Violation:
    return Violation(
        file=function.file,
        name=function.name,
        line=function.line,
        loc=function.loc,
        params=function.params,
        bool_params=function.bool_params,
        max_depth=function.max_depth,
        approximate=function.approximate,
    )


@runtime_checkable
class Measure(Protocol):
    def __call__(self, function: FunctionMetric) -> int: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class Rule:
    measure: Measure
    limit: int


LOC_RULE = Rule(measure=function_loc, limit=FUNCTION_LOC_LIMIT)
PARAMS_RULE = Rule(measure=function_params, limit=PARAM_LIMIT)
BOOL_PARAMS_RULE = Rule(measure=function_bool_params, limit=0)
DEPTH_RULE = Rule(measure=function_depth, limit=DEPTH_LIMIT)


def violation_group(functions: list[FunctionMetric], rule: Rule, cap: int) -> ViolationGroup:
    hits = [function for function in functions if rule.measure(function) > rule.limit]
    ranked = sorted(hits, key=rule.measure, reverse=True)[:cap]
    return ViolationGroup(count=len(hits), worst=[violation(function) for function in ranked])


def collect_violations(metrics: list[FileMetric], cap: int) -> Violations:
    functions = [f for m in metrics for f in m.functions]
    big_files = sorted((m for m in metrics if m.loc > FILE_LOC_LIMIT), key=file_loc, reverse=True)
    return Violations(
        functions_over_20_loc=violation_group(functions, LOC_RULE, cap),
        functions_over_3_params=violation_group(functions, PARAMS_RULE, cap),
        functions_with_bool_params=violation_group(functions, BOOL_PARAMS_RULE, cap),
        functions_nested_deeper_than_2=violation_group(functions, DEPTH_RULE, cap),
        files_over_500_loc=[FileViolation(file=m.path, loc=m.loc) for m in big_files[:cap]],
        long_lines_over_120_chars=sum(m.long_lines for m in metrics),
    )


def totals_of(metrics: list[FileMetric]) -> Totals:
    src_loc = sum(m.loc for m in metrics if not m.is_test)
    test_loc = sum(m.loc for m in metrics if m.is_test)
    test_files = sum(1 for m in metrics if m.is_test)
    langs: dict[str, int] = {}
    for metric in metrics:
        langs[metric.language] = langs.get(metric.language, 0) + metric.loc
    return Totals(
        files=len(metrics),
        source_files=len(metrics) - test_files,
        test_files=test_files,
        source_loc=src_loc,
        test_loc=test_loc,
        test_to_source_ratio=round(test_loc / src_loc, 3) if src_loc else None,
        functions_measured=sum(len(m.functions) for m in metrics),
        loc_by_language=langs,
    )


def summarize(
    metrics: list[FileMetric],
    graph: Graph,
    options: SummaryOptions = DEFAULT_SUMMARY_OPTIONS,
) -> SummaryReport:
    module_cycles = tarjan_sccs(graph)
    return SummaryReport(
        tool='uncle-bob metrics.py',
        granularity_note=(
            'fan-in/fan-out counted at module level, rolled up to top-level packages'
        ),
        totals=totals_of(metrics),
        component_metrics=package_metrics(graph, metrics, options.depth),
        module_cycles_adp=ModuleCycles(
            count=len(module_cycles),
            cycles=[c[:20] for c in module_cycles[: options.cap]],
        ),
        violations=collect_violations(metrics, options.cap),
    )


def render_summary(report: SummaryReport) -> str:
    totals = report.totals
    violations = report.violations
    lines = [
        f'files\t{totals.files} ({totals.test_files} test)',
        (
            f'source LOC\t{totals.source_loc}\ttest LOC\t{totals.test_loc}'
            f'\tratio\t{totals.test_to_source_ratio}'
        ),
        f'module cycles (ADP)\t{report.module_cycles_adp.count}',
        f'package cycles (ADP)\t{len(report.component_metrics.package_cycles)}',
        f'functions > {FUNCTION_LOC_LIMIT} LOC\t{violations.functions_over_20_loc.count}',
        f'functions > {PARAM_LIMIT} params\t{violations.functions_over_3_params.count}',
        f'functions with bool params\t{violations.functions_with_bool_params.count}',
        f'functions nested > {DEPTH_LIMIT}\t{violations.functions_nested_deeper_than_2.count}',
        f'files > {FILE_LOC_LIMIT} LOC\t{len(violations.files_over_500_loc)}',
        f'lines > {LINE_LIMIT} chars\t{violations.long_lines_over_120_chars}',
        '',
        'package\tCa\tCe\tI\tA\tD',
    ]
    for name, pkg in sorted(report.component_metrics.packages.items()):
        lines.append(
            f'{name}\t{pkg.fan_in_ca}\t{pkg.fan_out_ce}\t'
            f'{pkg.instability_i}\t{pkg.abstractness_a}\t{pkg.distance_d}'
        )
    return '\n'.join(lines)

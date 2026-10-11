"""Summary and counts projections for map_python_calls reports."""

from collections import Counter
from collections.abc import Sequence
from functools import partial

from python_harness.calls.domain import (
    CallsReport,
    ModuleCalls,
    SymbolReferencesReport,
    SymbolSummary,
    SymbolUsage,
)
from python_harness.core.output import JsonValue
from python_harness.tools.envelope import (
    OutputOptions,
    ProjectOutput,
    render_budgeted_project_document,
)
from python_harness.tools.map_python_calls.schema import CallsRequest

SUMMARY_MODULE_LIMIT = 20
SUMMARY_SYMBOL_LIMIT = 20

type ExternalSymbol = tuple[str, SymbolSummary]


def render_calls_document(
    report: CallsReport | SymbolReferencesReport,
    request: CallsRequest,
    diagnostics: dict[str, JsonValue],
    *,
    options: OutputOptions,
) -> str:
    if isinstance(report, CallsReport):
        output = calls_report_output(request, options)
        return render_budgeted_project_document(report, diagnostics, output)
    output = symbol_references_output(request, options)
    return render_budgeted_project_document(report, diagnostics, output)


def calls_report_output(
    request: CallsRequest, options: OutputOptions
) -> ProjectOutput[CallsReport]:
    return ProjectOutput(
        options=options,
        summary=partial(calls_report_summary, paths=request.paths, symbol=request.symbol),
        counts=calls_report_counts,
        summary_truncated=calls_report_summary_is_truncated,
    )


def symbol_references_output(
    request: CallsRequest, options: OutputOptions
) -> ProjectOutput[SymbolReferencesReport]:
    return ProjectOutput(
        options=options,
        summary=partial(symbol_references_summary, paths=request.paths, symbol=request.symbol),
        counts=symbol_references_counts,
        summary_truncated=symbol_references_summary_is_truncated,
    )


def calls_report_counts(report: CallsReport) -> dict[str, object]:
    categories = Counter(
        {
            'external': sum(len(module.external) for module in report.modules),
            'internal_only': sum(len(module.internal_only) for module in report.modules),
            'unreferenced': sum(len(module.unreferenced) for module in report.modules),
        }
    )
    return {
        'modules': len(report.modules),
        'symbol_categories': dict(sorted(categories.items())),
        'unparsable': len(report.unparsable),
    }


def symbol_references_counts(report: SymbolReferencesReport) -> dict[str, object]:
    return {
        'symbols': len(report.symbols),
        'references': sum(symbol.reference_count for symbol in report.symbols),
        'unparsable': len(report.unparsable),
    }


def calls_report_summary_is_truncated(report: CallsReport) -> bool:
    return (
        len(report.modules) > SUMMARY_MODULE_LIMIT
        or len(external_symbols(report)) > SUMMARY_SYMBOL_LIMIT
    )


def symbol_references_summary_is_truncated(report: SymbolReferencesReport) -> bool:
    return len(report.symbols) > SUMMARY_SYMBOL_LIMIT


def calls_report_summary(
    report: CallsReport,
    *,
    paths: Sequence[str],
    symbol: str | None,
) -> dict[str, object]:
    ranked_modules = sorted(report.modules, key=module_rank)
    ranked_symbols = sorted(external_symbols(report), key=external_symbol_rank)
    return {
        'counts': calls_report_counts(report),
        'modules': [
            {
                'path': module.metrics.path,
                'fan_in': module.metrics.fan_in,
                'fan_out': module.metrics.fan_out,
                'max_function_statements': module.metrics.max_function_statements,
            }
            for module in ranked_modules[:SUMMARY_MODULE_LIMIT]
        ],
        'top_referenced_symbols': [
            external_symbol_document(item) for item in ranked_symbols[:SUMMARY_SYMBOL_LIMIT]
        ],
        'narrowing': narrowing(paths=paths, symbol=symbol),
    }


def symbol_references_summary(
    report: SymbolReferencesReport,
    *,
    paths: Sequence[str],
    symbol: str | None,
) -> dict[str, object]:
    ranked_symbols = sorted(report.symbols, key=symbol_usage_rank)
    return {
        'counts': symbol_references_counts(report),
        'top_referenced_symbols': [
            symbol_usage_document(item) for item in ranked_symbols[:SUMMARY_SYMBOL_LIMIT]
        ],
        'narrowing': narrowing(paths=paths, symbol=symbol),
    }


def external_symbols(report: CallsReport) -> tuple[ExternalSymbol, ...]:
    return tuple(
        (module.metrics.path, symbol) for module in report.modules for symbol in module.external
    )


def module_rank(module: ModuleCalls) -> tuple[int, int, str]:
    metrics = module.metrics
    return (
        -(metrics.fan_in + metrics.fan_out),
        -metrics.max_function_statements,
        metrics.path,
    )


def external_symbol_rank(item: ExternalSymbol) -> tuple[int, str, str]:
    path, symbol = item
    return (-sum(symbol.context_counts.values()), path, symbol.name)


def symbol_usage_rank(symbol: SymbolUsage) -> tuple[int, str, str]:
    definition = symbol.definition
    return (-symbol.reference_count, definition.path, definition.name)


def external_symbol_document(item: ExternalSymbol) -> dict[str, object]:
    path, symbol = item
    return {
        'path': path,
        'name': symbol.name,
        'kind': symbol.kind.value,
        'references': sum(symbol.context_counts.values()),
    }


def symbol_usage_document(symbol: SymbolUsage) -> dict[str, object]:
    definition = symbol.definition
    return {
        'path': definition.path,
        'name': definition.name,
        'kind': definition.kind.value,
        'references': symbol.reference_count,
    }


def narrowing(*, paths: Sequence[str], symbol: str | None) -> dict[str, object]:
    return {'paths': list(paths), 'symbol': symbol, 'detail': 'full'}

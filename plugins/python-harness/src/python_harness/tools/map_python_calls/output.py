"""Summary and counts projections for map_python_calls reports."""

from collections import Counter
from collections.abc import Sequence

from python_harness.calls.domain import (
    CallsReport,
    ModuleCalls,
    SymbolReferencesReport,
    SymbolSummary,
    SymbolUsage,
)

SUMMARY_MODULE_LIMIT = 20
SUMMARY_SYMBOL_LIMIT = 20

type ExternalSymbol = tuple[str, SymbolSummary]


def calls_report_of(report: object) -> CallsReport | SymbolReferencesReport:
    if isinstance(report, (CallsReport, SymbolReferencesReport)):
        return report
    msg = 'map_python_calls output requires a calls report'
    raise TypeError(msg)


def calls_counts(report: object) -> dict[str, object]:
    calls = calls_report_of(report)
    if isinstance(calls, CallsReport):
        categories = Counter(
            {
                'external': sum(len(module.external) for module in calls.modules),
                'internal_only': sum(len(module.internal_only) for module in calls.modules),
                'unreferenced': sum(len(module.unreferenced) for module in calls.modules),
            }
        )
        return {
            'modules': len(calls.modules),
            'symbol_categories': dict(sorted(categories.items())),
            'unparsable': len(calls.unparsable),
        }
    return {
        'symbols': len(calls.symbols),
        'references': sum(symbol.reference_count for symbol in calls.symbols),
        'unparsable': len(calls.unparsable),
    }


def calls_summary(
    report: object,
    *,
    paths: Sequence[str],
    symbol: str | None,
) -> dict[str, object]:
    calls = calls_report_of(report)
    if isinstance(calls, CallsReport):
        return calls_report_summary(calls, paths=paths, symbol=symbol)
    return symbol_references_summary(calls, paths=paths, symbol=symbol)


def calls_summary_is_truncated(report: object) -> bool:
    calls = calls_report_of(report)
    if isinstance(calls, CallsReport):
        return (
            len(calls.modules) > SUMMARY_MODULE_LIMIT
            or len(external_symbols(calls)) > SUMMARY_SYMBOL_LIMIT
        )
    return len(calls.symbols) > SUMMARY_SYMBOL_LIMIT


def calls_report_summary(
    report: CallsReport,
    *,
    paths: Sequence[str],
    symbol: str | None,
) -> dict[str, object]:
    ranked_modules = sorted(report.modules, key=module_rank)
    ranked_symbols = sorted(external_symbols(report), key=external_symbol_rank)
    return {
        'counts': calls_counts(report),
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
        'counts': calls_counts(report),
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

"""Summary and counts projections for collect_python_facts reports."""

from collections import Counter
from collections.abc import Sequence

from python_harness.facts.domain import FactsReport, ModuleFacts

SUMMARY_MODULE_LIMIT = 20


def facts_counts(facts: FactsReport) -> dict[str, object]:
    fact_kinds = Counter(
        fact.detail.kind.value for module in facts.modules for fact in module.facts
    )
    return {
        'modules': len(facts.modules),
        'lines': sum(module.line_count for module in facts.modules),
        'facts': sum(len(module.facts) for module in facts.modules),
        'fact_kinds': dict(sorted(fact_kinds.items())),
        'unparsable': len(facts.unparsable),
    }


def facts_summary(
    facts: FactsReport,
    *,
    paths: Sequence[str],
    with_function_shapes: bool,
) -> dict[str, object]:
    ranked_modules = sorted(facts.modules, key=module_rank)
    return {
        'counts': facts_counts(facts),
        'modules': [
            {
                'path': module.path,
                'lines': module.line_count,
                'facts': len(module.facts),
            }
            for module in ranked_modules[:SUMMARY_MODULE_LIMIT]
        ],
        'narrowing': {
            'paths': list(paths),
            'detail': 'full',
            'with_function_shapes': with_function_shapes,
        },
    }


def facts_summary_is_truncated(facts: FactsReport) -> bool:
    return len(facts.modules) > SUMMARY_MODULE_LIMIT


def module_rank(module: ModuleFacts) -> tuple[int, int, str]:
    return (-len(module.facts), -module.line_count, module.path)

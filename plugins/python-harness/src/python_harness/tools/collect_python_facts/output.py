"""Summary and counts projections for collect_python_facts reports."""

from collections import Counter
from collections.abc import Sequence
from functools import partial

from python_harness.core.output import JsonValue
from python_harness.facts.domain import FactsReport, ModuleFacts
from python_harness.tools.collect_python_facts.schema import FactsRequest
from python_harness.tools.envelope import (
    OutputOptions,
    OutputView,
    ProjectOutput,
    output_view,
    render_budgeted_project_document,
)

SUMMARY_MODULE_LIMIT = 20


def render_facts_document(
    report: FactsReport,
    request: FactsRequest,
    diagnostics: dict[str, JsonValue],
    *,
    options: OutputOptions,
) -> str:
    output = ProjectOutput(
        options=options,
        summary=partial(
            facts_summary,
            paths=request.paths,
            with_function_shapes=request.with_function_shapes,
        ),
        counts=facts_counts,
    )
    return render_budgeted_project_document(report, diagnostics, output)


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
) -> OutputView:
    ranked_modules = sorted(facts.modules, key=module_rank)
    return output_view(
        {
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
        },
        truncated=len(ranked_modules) > SUMMARY_MODULE_LIMIT,
    )


def module_rank(module: ModuleFacts) -> tuple[int, int, str]:
    return (-len(module.facts), -module.line_count, module.path)

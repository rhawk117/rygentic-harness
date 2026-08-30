from dataclasses import dataclass, field

from pydantic_evals.evaluators import EvaluationReason

from plugin_evals.evaluators.base import (
    Check,
    CheckContext,
    TypedEvaluator,
    failed,
    passed,
)


@dataclass
class HypothesisLogged(Check, TypedEvaluator):
    filename: str = 'whats-broken.md'

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        # deleted-on-close is compliant, so a response that names the log also passes
        if ctx.output.workdir.joinpath(self.filename).is_file():
            return passed(f'{self.filename} on disk')

        if self.filename in ctx.output.response:
            return passed(f'{self.filename} referenced in response (deleted on close)')
        return failed(f'no evidence of {self.filename}')


@dataclass
class RegressionEvidence(Check, TypedEvaluator):
    test_paths: list[str] = field(default_factory=list)
    response_hint: str = 'regression'

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        for rel in self.test_paths:
            if ctx.output.workdir.joinpath(rel).is_file():
                return passed(f'regression test at {rel}')

        if self.response_hint in ctx.output.response.lower():
            return passed(f'response claims a {self.response_hint} test')
        return failed(f'no regression test at {self.test_paths} and no claim in response')


@dataclass
class ReviewAggregationSound(Check, TypedEvaluator):
    review_glob: str = '.mightymodels/checkout-fix/review/*'

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        corpus = self._corpus(ctx)
        triple = self._has_triple(corpus)
        dedup = 'MV-1' in corpus and ('UB-1' in corpus or 'G4' in corpus)
        mapped = 'Critical' in corpus

        if triple and dedup and mapped:
            return passed('3 findings, dual provenance, Blocker mapped to Critical')
        return failed(f'triple={triple} dedup={dedup} critical_mapped={mapped}')

    def _corpus(self, ctx: CheckContext) -> str:
        # the aggregate may live in a review/ file or only in the session response
        parts = [ctx.output.response]
        parts.extend(
            path.read_text(encoding='utf-8', errors='replace')
            for path in ctx.output.workdir.glob(self.review_glob)
            if path.is_file()
        )
        return '\n'.join(parts)

    def _has_triple(self, corpus: str) -> bool:
        agg_ids = ('AGG-1', 'AGG-2', 'AGG-3')
        consolidated_ids = ('C-1', 'C-2', 'C-3')
        return all(k in corpus for k in agg_ids) or all(
            k in corpus for k in consolidated_ids
        )

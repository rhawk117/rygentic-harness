import re
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
class ResponseContains(Check, TypedEvaluator):
    needle: str = ''
    expect: bool = True

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        found = self.needle in ctx.output.response
        state = 'has' if found else 'lacks'
        if found == self.expect:
            return passed(f'response {state} {self.needle!r}')
        return failed(f'response unexpectedly {state} {self.needle!r}')


@dataclass
class ResponseContainsAll(Check, TypedEvaluator):
    needles: list[str] = field(default_factory=list)

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        missing = [n for n in self.needles if n not in ctx.output.response]
        if not missing:
            return passed(f'response carries all of {self.needles}')
        return failed(f'response lacks: {missing}')


@dataclass
class ResponseContainsAny(Check, TypedEvaluator):
    needles: list[str] = field(default_factory=list)

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        hits = [n for n in self.needles if n in ctx.output.response]
        if hits:
            return passed(f'response carries {hits[:3]}')
        return failed(f'response carries none of {self.needles}')


@dataclass
class ResponseCountAtLeast(Check, TypedEvaluator):
    needle: str = ''
    minimum: int = 1

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        count = ctx.output.response.count(self.needle)
        if count >= self.minimum:
            return passed(f'{count}x {self.needle!r} in response')
        return failed(f'only {count}x {self.needle!r} in response (need {self.minimum})')


@dataclass
class ResponseRegexCount(Check, TypedEvaluator):
    pattern: str = ''
    minimum: int = 1

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        count = len(re.findall(self.pattern, ctx.output.response))
        if count >= self.minimum:
            return passed(f'{count}x {self.pattern!r} in response')
        return failed(f'only {count}x {self.pattern!r} in response (need {self.minimum})')


@dataclass
class ResponseTailAsksQuestion(Check, TypedEvaluator):
    tail_chars: int = 600

    def evaluate(self, ctx: CheckContext) -> EvaluationReason:
        tail = ctx.output.response[-self.tail_chars :]
        if '?' in tail:
            return passed('response tail asks the user')
        return failed('no question in the response tail')

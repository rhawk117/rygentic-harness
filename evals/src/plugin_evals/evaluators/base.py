from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from plugin_evals.artifacts import RunArtifacts

type CheckContext = EvaluatorContext[dict, RunArtifacts, dict]

# subclassing the parameterized base keeps evaluate() overrides LSP-compatible under ty
TypedEvaluator = Evaluator[dict, RunArtifacts, dict]

_REASON_CAP = 400


@dataclass
class Check:
    # mixin rather than an Evaluator subclass: the pydantic_evals metaclass rejects
    # abstract intermediates at class-creation time
    check: str = ''

    if TYPE_CHECKING:

        @classmethod
        def get_serialization_name(cls) -> str: ...

    def get_default_evaluation_name(self) -> str:
        if self.check:
            return self.check
        return self.get_serialization_name()


def passed(reason: str) -> EvaluationReason:
    return EvaluationReason(value=True, reason=reason[:_REASON_CAP])


def failed(reason: str) -> EvaluationReason:
    return EvaluationReason(value=False, reason=reason[:_REASON_CAP])

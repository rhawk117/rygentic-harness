"""How a state tool asks the user for a value the caller left out.

A tool that needs a fixed choice takes it as an argument. When the caller leaves it out, a resolver
returns an `Elicit` and the host puts the question to the user, then retries the same call with
the answer. The answer is validated against the question's model before the tool body runs, so a
value outside the choices, or over the length of an argument, is refused before any write. Nothing
is stored by the call that asks; the retried call carries the answer and stores it.

The context method that asks over a back-channel is not used: Claude Code speaks a protocol with
none, and only a `Resolve` parameter is answered there.

Nobody may answer, as under `claude -p`, where the tool receives `cancel` at once. A tool then
returns `needs_input_text`, which names each question, its choices and the argument to pass on the
next call, so the primary can ask in the foreground and call again.

A question's answer is a `Choice`. Its value is `None` only when the resolver found nothing to ask,
which a tool reads as unanswered. The elicitation schema of the host admits no `$ref`, so
`enumerated` inlines an enum's values, the enum staying the one place the choices are written, and
`AnswerName` and `AnswerProse` are plain assignments of the lengths `NameText` and `ProseText`
hold an argument to, which as `type` aliases would be referenced instead of inlined.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from mcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
    render_elicitation_schema,
)
from pydantic import BaseModel, StringConstraints, WithJsonSchema

from mightymodels.core.declarative import NAME_LIMIT, PROSE_LIMIT
from mightymodels.tools.request import RequestModel

AnswerName = Annotated[str, StringConstraints(max_length=NAME_LIMIT)]
AnswerProse = Annotated[str, StringConstraints(max_length=PROSE_LIMIT)]
NEEDS_INPUT = 'needs input: no one answered; ask the user, then call again with the argument shown'


class Choice[Value](RequestModel):
    choice: Value | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Question:
    message: str
    answer: type[BaseModel]
    argument: str


def enumerated(choices: type[StrEnum]) -> WithJsonSchema:
    return WithJsonSchema({'type': 'string', 'enum': [choice.value for choice in choices]})


type Answered[Answer: BaseModel] = (
    AcceptedElicitation[Answer] | DeclinedElicitation | CancelledElicitation
)


def answer_of[Answer: BaseModel](outcome: Answered[Answer]) -> Answer | None:
    return outcome.data if outcome.action == 'accept' else None


def chosen[Value](outcome: Answered[Choice[Value]]) -> Value | None:
    answer = answer_of(outcome)
    return None if answer is None else answer.choice


def choices_of(answer: type[BaseModel]) -> list[str]:
    choice = render_elicitation_schema(answer)['properties']['choice']
    return [str(value) for value in choice.get('enum', ['true', 'false'])]


def needs_input_text(questions: Sequence[Question]) -> str:
    blocks = (
        f'{question.message}\nchoices: {", ".join(choices_of(question.answer))}\n'
        f'pass: {question.argument}\n'
        for question in questions
    )
    return f'{NEEDS_INPUT}\n' + ''.join(blocks)

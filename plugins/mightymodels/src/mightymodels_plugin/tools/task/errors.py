"""The failures of recording a failed fix, each answered to the caller as a tool error."""

from collections.abc import Sequence

from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.tools.task.schema import Status


class FixesSpentError(StateError):
    def __init__(self, task_id: str, tried: Sequence[str]) -> None:
        listed = ''.join(f'\n  {number}. {text}' for number, text in enumerate(tried, start=1))
        super().__init__(
            f'{task_id} is blocked: {len(tried)} fixes failed and no more are tried; report it '
            f'blocked and list the hypotheses tried, in order:{listed}\nnothing was written'
        )
        self.task_id = task_id
        self.tried = tuple(tried)


class FixNotUnderwayError(StateError):
    def __init__(self, task_id: str, current: Status) -> None:
        super().__init__(
            f'{task_id} is {current}; a failed fix is recorded on a task in progress, started '
            'by the dispatching primary'
        )
        self.task_id = task_id
        self.current = current

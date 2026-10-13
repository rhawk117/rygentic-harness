"""The review run id, the only caller-chosen text besides a slug that becomes a path component.

The pattern is published in the `review` tool's schema and names its digits as `[0-9]`, so the
schema and the server accept the same ASCII digits and no others.
"""

from typing import Annotated, override

from pydantic import ConfigDict, RootModel, StringConstraints, ValidationError

from mightymodels_plugin.core.errors import StateError

RUN_ID_PATTERN = r'^[0-9]{8}-[0-9]{6}$'

type RunIdText = Annotated[str, StringConstraints(pattern=RUN_ID_PATTERN)]


class InvalidRunIdError(StateError):
    def __init__(self, raw: str) -> None:
        super().__init__(f'run id {raw!r} is not valid: it is the UTC start time, YYYYMMDD-HHMMSS')
        self.raw = raw


class RunId(RootModel[RunIdText]):
    model_config = ConfigDict(frozen=True)

    @override
    def __str__(self) -> str:
        return self.root


def parsed_run_id(raw: str) -> RunId | InvalidRunIdError:
    try:
        return RunId(raw)
    except ValidationError:
        return InvalidRunIdError(raw)

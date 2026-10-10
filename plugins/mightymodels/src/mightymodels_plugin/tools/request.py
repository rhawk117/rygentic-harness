"""What every tool's request models share: one config, and the text types a caller writes in.

A request model is one a caller fills in. `RequestModel` gives them all one config: frozen, no
field the model does not name, and no string longer than `PROSE_LIMIT`, the longest text column.
That ceiling is checked when a request is validated, but Pydantic does not put a config's string
maximum in the JSON Schema it generates, so a tool's published schema would not state it.

The field types state it. `ProseText` is text stored in a `Prose` column and `NameText` text
stored in a `Name` column, each held to that column's declared length, and a constrained type a
schema declares for itself carries its own maximum. Text that reaches no column of its own, such
as an item of a list kept as JSON, is a `ProseText`. An output or a view model is not caller input
and is built on neither.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from mightymodels_plugin.core.declarative import NAME_LIMIT, PROSE_LIMIT

type NameText = Annotated[str, StringConstraints(max_length=NAME_LIMIT)]
type ProseText = Annotated[str, StringConstraints(max_length=PROSE_LIMIT)]


class RequestModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', str_max_length=PROSE_LIMIT)

"""What every table of the state database is declared from.

A domain declares its rows in its own `tables.py` from this base and these column types, and
`tools/row_types.py` names every row type `database.py` creates a table for.

Every row type has a `repository_key` column, because one database holds the rows of every
repository. It leads the primary key of a table keyed by names, so the same slug, task id, run id
or investigation id is a different row in another repository. A table keyed by a serial number
carries it as a plain column that leads an index, and the number orders the rows of one
repository.

A column is declared by its type alone: an alias below, or one a domain's `tables.py` adds for a
column only it has. A `KeyPart` is a column of its table's primary key.

Every string column is declared from such a type, and each type has a length. SQLite does not hold
a value to its declared length, so a length is true only where the value's own type is: a
repository key, a slug, a task id and a run id are refused over theirs before they reach a row, a
`Word` is a member of an enum, a `Sha` is a git object name or a SHA-256 digest, and a `Timestamp`
is written by the clock. A `Name`, a `Prose` and a `ReportProse` hold text a caller wrote, and
the request model that takes the text refuses it over the column's length before a row is
written: `tools/request.py` has the types. One text reaches such a column another way and is
not held to it: a ticket's lines, which `validate` reads from a `ticket.yml` the user may have
edited by hand. Text that redaction has lengthened past its column is refused, since the marker that
replaces a secret can be longer than the secret.

`ReportProse` is the column of a scout report and of a similarity row's text, with a limit of
its own, `REPORT_LIMIT`, which the spool's file cap (`SPOOL_FILE_BYTES` in
`tools/similarity/spool.py`) is sized from, so that a long report is stored whole.

A column the plugin has a default for carries it as a server default, so a row written without the
column reads as one the plugin wrote. A `Timestamp` left out is the time of the write, in the
clock's own form, and a `TextsIfAny` left out is an empty list.

`child_of` is the foreign key of a row that cannot exist without another: it names the parent by
the parent's whole primary key, under the same column names. It is checked when the transaction
commits, so a parent and its child are written in one transaction in either order.
"""

from types import MappingProxyType
from typing import Annotated

from sqlalchemy import JSON, ForeignKeyConstraint, String, text
from sqlalchemy.orm import DeclarativeBase, mapped_column

from mightymodels_plugin.core.repository_key import REPOSITORY_KEY_LIMIT
from mightymodels_plugin.core.slug import SLUG_LIMIT

TASK_ID_LIMIT = 7
WORD_LIMIT = 32
TIMESTAMP_LIMIT = 25
SHA_LIMIT = 64
NAME_LIMIT = 255
PROSE_LIMIT = 4000
REPORT_LIMIT = 60_000
TIME_OF_THE_WRITE = text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))")
EMPTY_LIST = '[]'

type Models = dict[str, str | None]
type Weights = dict[str, float]
type Texts = list[str]
type TextsIfAny = Annotated[list[str], mapped_column(JSON, server_default=EMPTY_LIST)]
type Serial = Annotated[int, mapped_column(primary_key=True)]
type RepositoryKeyPart = Annotated[
    str, mapped_column(String(REPOSITORY_KEY_LIMIT), primary_key=True)
]
type RepositoryName = Annotated[str, mapped_column(String(REPOSITORY_KEY_LIMIT))]
type SlugKeyPart = Annotated[str, mapped_column(String(SLUG_LIMIT), primary_key=True)]
type SlugName = Annotated[str, mapped_column(String(SLUG_LIMIT))]
type TaskName = Annotated[str, mapped_column(String(TASK_ID_LIMIT))]
type Word = Annotated[str, mapped_column(String(WORD_LIMIT))]
type Sha = Annotated[str, mapped_column(String(SHA_LIMIT))]
type Name = Annotated[str, mapped_column(String(NAME_LIMIT))]
type Prose = Annotated[str, mapped_column(String(PROSE_LIMIT))]
type ReportProse = Annotated[str, mapped_column(String(REPORT_LIMIT))]
type Timestamp = Annotated[
    str, mapped_column(String(TIMESTAMP_LIMIT), server_default=TIME_OF_THE_WRITE)
]


class Base(DeclarativeBase):
    type_annotation_map = MappingProxyType({Models: JSON, Texts: JSON, Weights: JSON})


def child_of(parent: type[Base]) -> ForeignKeyConstraint:
    parent_key = list(parent.__table__.primary_key)
    return ForeignKeyConstraint(
        [column.name for column in parent_key],
        parent_key,
        deferrable=True,
        initially='DEFERRED',
    )

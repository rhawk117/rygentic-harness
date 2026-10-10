"""The scout-report spool: files a process outside the server leaves for it to take in.

The spool is the directory `SPOOL_DIRECTORY` in the plugin data directory, which every repository
shares. A report is one file in it named `<digest>-<unique part>.json`, whose content is a JSON
object with exactly these keys:

    {"repository_key": "owner/name", "scout": "code-scout", "target": "...", "report": "..."}

`scout` is `code-scout` or `web-scout`, `target` is at most `NAME_LIMIT` characters and `report`
is non-blank text of at most `REPORT_LIMIT`. `SPOOL_FILE_BYTES` follows from those limits: a JSON
writer that escapes non-ASCII text spells a character in at most `ESCAPED_CHARACTER_BYTES` bytes (a
four-byte character as a surrogate pair of two six-byte escapes), so a file holds `REPORT_LIMIT`
characters of report and the longest key and target, with `ENVELOPE_BYTES` for the rest. A writer
creates the file under a name that does not end in `.json` and renames it to one that does, so the
server never reads half a report.

`<digest>` is the SHA-256 hex digest of the repository key's text in UTF-8, and
`spool_file_prefix` in `repository_key.py` gives `<digest>-` for a key, so a writer names its file
`spool_file_prefix(key)` followed by a unique part and `.json`. A server lists only the names that
begin with its own prefix: a file of another repository costs it nothing and cannot starve it, and
a file under any other name is never opened, read or moved.

The key is in the file as well, so a file under this repository's digest whose content names
another key is set aside, and so is a file it cannot take in, because it is over
`SPOOL_FILE_BYTES`, is not a report, or holds text that redaction lengthens past its column. A
file set aside is moved to `REJECTED_DIRECTORY` inside the spool under a name of its own and
kept. Every path is the data directory, a fixed name, the digest and the writer's unique part: no
key is ever part of a path.

A hand-back and a stop of one scout both leave a report, so a writer puts `HANDBACK_PART` or
`CLOSING_PART` first in the unique part: the report a scout handed back, and the closing text it
stopped with. A file waits in name order, so a hand-back is always listed before any closing text,
and a closing text is dropped when a report of the same scout and target is already stored: one
report is kept for the agent and the handed-back one wins. A file under any other part is stored.

A call takes in at most `SPOOL_FILES_PER_CALL` files, oldest name first.
"""

from itertools import islice
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from mightymodels_plugin.core.declarative import NAME_LIMIT, REPORT_LIMIT
from mightymodels_plugin.core.repository_key import REPOSITORY_KEY_LIMIT
from mightymodels_plugin.tools.similarity.schema import SpooledReport

SPOOL_DIRECTORY = 'scout-spool'
REJECTED_DIRECTORY = 'rejected'
REPORT_SUFFIX = '.json'
SPOOL_FILES_PER_CALL = 100
ESCAPED_CHARACTER_BYTES = 12
ENVELOPE_BYTES = 256
SPOOL_FILE_BYTES = (
    REPORT_LIMIT + NAME_LIMIT + REPOSITORY_KEY_LIMIT
) * ESCAPED_CHARACTER_BYTES + ENVELOPE_BYTES
HANDBACK_PART = 'handback-'
CLOSING_PART = 'stop-'


def is_closing_text(file: Path, prefix: str) -> bool:
    return file.name.removeprefix(prefix).startswith(CLOSING_PART)


def waiting_files(spool: Path, prefix: str) -> list[Path]:
    files = (
        file
        for file in sorted(spool.glob(f'{prefix}*{REPORT_SUFFIX}'))
        if file.is_file(follow_symlinks=False)
    )
    return list(islice(files, SPOOL_FILES_PER_CALL))


def spooled_report(file: Path) -> SpooledReport | None:
    if file.stat().st_size > SPOOL_FILE_BYTES:
        return None
    try:
        return SpooledReport.model_validate_json(file.read_bytes())
    except ValidationError:
        return None


def set_aside(file: Path, spool: Path) -> None:
    rejected = spool.joinpath(REJECTED_DIRECTORY)
    rejected.mkdir(exist_ok=True)
    file.replace(rejected.joinpath(f'{uuid4().hex}-{file.name}'))

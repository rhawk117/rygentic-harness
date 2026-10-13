"""The timestamp every row and ticket file carries."""

from datetime import UTC, datetime


def now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec='seconds')

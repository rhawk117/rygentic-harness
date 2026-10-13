"""How a commit is shown: its first twelve characters, or `unknown` where git gave no HEAD."""

SHORT_SHA = 12


def short_head(head: str | None) -> str:
    return ('unknown' if head is None else head)[:SHORT_SHA]

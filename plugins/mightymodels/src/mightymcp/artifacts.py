from pathlib import Path

from pydantic import ConfigDict

from mightymcp.paths import TicketPathError, ticket_dir

NONE_ITEM = '- none'


def kebab(name: str) -> str:
    """Return the key a .mightymodels artifact carries this field name under."""
    return name.replace('_', '-')


ALIASED = ConfigDict(alias_generator=kebab, populate_by_name=True)


def ticket_directory(slug: str) -> tuple[Path | None, list[str]]:
    """Return the directory this ticket's artifacts are written into, or why not."""
    try:
        directory = ticket_dir(slug)
    except TicketPathError as err:
        return None, [str(err)]
    if not directory.is_dir():
        return None, [f'no ticket directory at {directory}']
    return directory, []


def bullets(values: list[str]) -> list[str]:
    """Render one '- ' line per value, or a single '- none' for an empty list."""
    return [f'- {value}' for value in values] or [NONE_ITEM]


def bracket_list(values: list[str]) -> str:
    """Render a list the way the ASKED stanza carries paths: [a, b]."""
    return f'[{", ".join(values)}]'


def parse_bracket_list(value: str) -> list[str]:
    """Parse '[a, b]' back into its items."""
    inner = value.strip().removeprefix('[').removesuffix(']')
    return [item.strip() for item in inner.split(',') if item.strip()]


def parse_fields(block: str, keys: tuple[str, ...]) -> dict[str, str]:
    """Split a 'key: value' block into its fields, keeping continuation lines."""
    fields: dict[str, list[str]] = {}
    current: str | None = None
    for line in block.splitlines():
        key, _, rest = line.partition(':')
        if key in keys:
            current = key
            fields[current] = [rest.strip()]
        elif current is not None:
            fields[current].append(line)
    return {key: '\n'.join(parts).strip() for key, parts in fields.items()}


def cap_refusals(label: str, text: str, cap: int) -> list[str]:
    """Refuse a body over its line cap; caps are contracts, per contracts.md."""
    lines = len(text.splitlines())
    if lines <= cap:
        return []
    return [f'{label} is {lines} lines; the cap is {cap}']


def missing_refusals(fields: dict[str, str]) -> list[str]:
    """Refuse every named field that came in empty."""
    return [f'{name} is empty' for name, value in fields.items() if not value.strip()]

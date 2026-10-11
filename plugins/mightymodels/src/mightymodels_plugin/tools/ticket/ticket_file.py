"""ticket.yml in one canonical YAML subset, written and read back in exactly that subset.

Two levels of mappings, scalars, and lists of scalars, with trailing comments. A hand edit
that stays in the subset parses; anything else is refused with its line number rather than
misread.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from mightymodels_plugin.core.codec import encode_compact
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.routing import models_at
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.ticket.schema import TicketAnswers

type Node = Tree | list[Node] | str | int | bool | None
type Tree = dict[str, Node]
type Scalar = str | int | bool | None

INDENT = 2
PRIMARY_AGENT = 'primary-agent'
CONTEXT_KEY = 'context'
DECODER = json.JSONDecoder()
PLAIN_SCALARS: Mapping[str, bool | None] = MappingProxyType(
    {'true': True, 'false': False, '': None}
)


class SubsetError(StateError):
    def __init__(self, number: int, reason: str) -> None:
        super().__init__(f'ticket.yml:{number}: {reason}')
        self.number = number
        self.reason = reason


class TabIndentationError(SubsetError):
    def __init__(self, number: int) -> None:
        super().__init__(number, 'the indentation holds a tab; indent with two spaces per level')


@dataclass(slots=True, kw_only=True, frozen=True)
class Line:
    number: int
    indent: int
    text: str


def quoted(value: str) -> str:
    return encode_compact(value).decode()


def scalar_text(*, value: Scalar) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    return quoted(value)


def entry_line(key: str, depth: int, *, value: Scalar) -> str:
    rendered = scalar_text(value=value)
    pad = ' ' * (depth * INDENT)
    return f'{pad}{key}: {rendered}'.rstrip()


def list_lines(key: str, values: Sequence[str], depth: int) -> list[str]:
    pad = ' ' * (depth * INDENT)
    items = [f'{pad}{" " * INDENT}- {quoted(value)}' for value in values]
    return [f'{pad}{key}:', *items]


def ticket_text(slug: Slug, answers: TicketAnswers, *, triaged_at: str) -> str:
    models: dict[str, str | None] = {PRIMARY_AGENT: None, **models_at(answers.scope)}
    lines = [
        entry_line('task', 0, value=slug.root),
        entry_line('summary', 0, value=answers.summary),
        entry_line('triaged-at', 0, value=triaged_at),
        *list_lines(CONTEXT_KEY, answers.context, 0),
        'companion-docs:',
        entry_line('issue-number', 1, value=answers.issue),
        entry_line('jira-key', 1, value=answers.jira),
        *list_lines('reference-urls', answers.reference_urls, 1),
        'subagent-models:',
        *(entry_line(worker, 1, value=model) for worker, model in models.items()),
        'handoff-context:',
        entry_line('scope', 1, value=str(answers.scope)),
        entry_line('plan-first', 1, value=answers.compaction),
        entry_line('branch-name', 1, value=answers.branch),
        entry_line('worktrees-okay', 1, value=False),
        *list_lines('investigations', answers.investigations, 0),
    ]
    return '\n'.join(lines) + '\n'


def value_text(text: str) -> str:
    if text.startswith('"'):
        return text
    if text.startswith('#'):
        return ''
    return text.split(' #', 1)[0].rstrip()


def source_line(number: int, raw: str) -> Line | None:
    content = raw.rstrip()
    if not content.strip() or content.lstrip().startswith('#'):
        return None
    if '\t' in content.removesuffix(content.lstrip()):
        raise TabIndentationError(number)
    indent = len(content) - len(content.lstrip(' '))
    if indent % INDENT:
        raise SubsetError(number, 'indentation must be a multiple of two spaces')
    return Line(number=number, indent=indent, text=content.strip())


def source_lines(source: str) -> list[Line]:
    numbered = enumerate(source.splitlines(), start=1)
    return [line for number, raw in numbered if (line := source_line(number, raw)) is not None]


def quoted_scalar(text: str, number: int) -> str:
    try:
        decoded, end = DECODER.raw_decode(text)
    except json.JSONDecodeError as error:
        raise SubsetError(number, 'unterminated quoted string') from error
    rest = text[end:].strip()
    if rest and not rest.startswith('#'):
        raise SubsetError(number, f'unexpected text after the string: {rest}')
    return str(decoded)


def parsed_scalar(text: str, number: int) -> Node:
    if text.startswith('"'):
        return quoted_scalar(text, number)
    if text in PLAIN_SCALARS:
        return PLAIN_SCALARS[text]
    if text.isdigit():
        return int(text)
    if text[0] in "'[{&*!|>":
        raise SubsetError(number, f'unsupported YAML syntax: {text}')
    return text


def split_key(line: Line) -> tuple[str, str]:
    key, separator, rest = line.text.partition(':')
    if not separator or not key or ' ' in key:
        raise SubsetError(line.number, f'expected "key: value", got {line.text}')
    return key, rest.strip()


def indent_at(lines: Sequence[Line], index: int) -> int:
    return lines[index].indent if index < len(lines) else -1


def sequence_at(lines: Sequence[Line], index: int) -> tuple[list[Node], int]:
    indent = lines[index].indent
    items: list[Node] = []
    while indent_at(lines, index) == indent:
        line = lines[index]
        if not line.text.startswith('- '):
            raise SubsetError(line.number, 'mixed list and mapping at one level')
        items.append(parsed_scalar(value_text(line.text[2:].strip()), line.number))
        index += 1
    return items, index


def mapping_at(lines: Sequence[Line], index: int) -> tuple[Tree, int]:
    indent = lines[index].indent
    result: Tree = {}
    while indent_at(lines, index) == indent:
        line = lines[index]
        key, rest = split_key(line)
        if key in result:
            raise SubsetError(line.number, f'duplicate key {key}')
        result[key], index = value_at(lines, index, rest)
    if indent_at(lines, index) > indent:
        raise SubsetError(lines[index].number, 'unexpected indentation')
    return result, index


def block_at(lines: Sequence[Line], index: int) -> tuple[Node, int]:
    if lines[index].text.startswith('- '):
        return sequence_at(lines, index)
    return mapping_at(lines, index)


def value_at(lines: Sequence[Line], index: int, rest: str) -> tuple[Node, int]:
    line = lines[index]
    text = value_text(rest)
    if text:
        return parsed_scalar(text, line.number), index + 1
    if indent_at(lines, index + 1) > line.indent:
        return block_at(lines, index + 1)
    return None, index + 1


def parse(source: str) -> Tree:
    lines = source_lines(source)
    if not lines:
        return {}
    if lines[0].indent:
        raise SubsetError(lines[0].number, 'unexpected indentation')
    tree, _ = block_at(lines, 0)
    if not isinstance(tree, dict):
        raise SubsetError(lines[0].number, 'the top level must be a mapping')
    return tree


def with_context(source: str, context: Sequence[str]) -> str:
    raw = source.splitlines()
    lines = source_lines(source)
    after_file = len(raw) + 1
    top_level = [line for line in lines if line.indent == 0]
    start = next(
        (line.number for line in top_level if split_key(line)[0] == CONTEXT_KEY), after_file
    )
    following = next((line.number for line in top_level if line.number > start), after_file)
    last = max((line.number for line in lines if start < line.number < following), default=start)
    updated = [*raw[: start - 1], *list_lines(CONTEXT_KEY, context, 0), *raw[last:]]
    return '\n'.join(updated) + '\n'

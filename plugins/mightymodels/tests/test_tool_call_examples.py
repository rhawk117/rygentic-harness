"""Every state-tool call example in the skills and the agent files is a call its tool accepts.

The test reads every Markdown file under `skills` and `agents` and keeps no list of examples. An
example is a fenced block that is marked `json` or holds the `"request"` key. Its text has to be
one JSON object with the single key `request`, the way a caller sends it, and the value has to
pass the request model of the tool it belongs to.

Placing rule: an example belongs to the tool whose full name, `mcp__plugin_mightymodels_state__`
and the tool, is the last one written above the example in the body of its file. The frontmatter
does not count, because it lists every tool the file may call. An example with no tool name above
it cannot be placed, and an example placed with a name the server does not register is an example
for a tool that does not exist. Each is a failure at the example's file and line.

Substitution rule: nothing is substituted. A placeholder such as `SLUG`, `ID`, `T1`,
`<files-in-scope>` or `...` is validated as the value it is written as, so it has to be a value
the request model accepts where it stands. One that is not, such as `<slug>` for a slug or a bare
`N` for a number, fails the example at its file and line.

The id of each case of the per-tool test holds the number of examples found for that tool. A tool
that a read file names and that no example belongs to is a failure at each line that names it.
"""

import inspect
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from types import MappingProxyType, MethodType

import pytest
from mightymodels_plugin.server import SERVER_NAME, TOOLS
from pydantic import BaseModel, ConfigDict, ValidationError, create_model

PLUGIN = Path(__file__).parent.parent
READ_DIRECTORIES = ('skills', 'agents')
FRONTMATTER = re.compile(r'\A---\n.*?\n---\n', re.DOTALL)
FENCE = re.compile(
    r'^[ \t]*```(?P<mark>[^\n`]*)\n(?P<text>.*?)^[ \t]*```[ \t]*$', re.MULTILINE | re.DOTALL
)
TOOL_NAME = re.compile(r'\bmcp__\w+')
TOOL_PREFIX = f'mcp__plugin_mightymodels_{SERVER_NAME}__'
EXAMPLE_MARK = 'json'
WRAPPER_KEY = '"request"'


@dataclass(slots=True, kw_only=True, frozen=True)
class MarkdownFile:
    name: str
    text: str

    def place(self, offset: int) -> str:
        return f'{self.name}:{self.text.count("\n", 0, offset) + 1}'


@dataclass(slots=True, kw_only=True, frozen=True)
class Example:
    place: str
    text: str
    tool: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Mention:
    place: str
    tool: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ToolUse:
    tool: str
    named_at: tuple[str, ...]
    examples: int


def markdown_file(path: Path) -> MarkdownFile:
    return MarkdownFile(
        name=path.relative_to(PLUGIN).as_posix(), text=path.read_text(encoding='utf-8')
    )


def is_example(fence: re.Match[str]) -> bool:
    return fence['mark'].strip() == EXAMPLE_MARK or WRAPPER_KEY in fence['text']


def examples_in(file: MarkdownFile) -> Iterator[Example]:
    frontmatter = FRONTMATTER.match(file.text)
    body_start = 0 if frontmatter is None else frontmatter.end()
    for fence in filter(is_example, FENCE.finditer(file.text)):
        named_above = TOOL_NAME.findall(file.text, body_start, fence.start())
        yield Example(
            place=file.place(fence.start('text')),
            text=fence['text'],
            tool=next(reversed(named_above), None),
        )


def mentions_in(file: MarkdownFile) -> Iterator[Mention]:
    return (
        Mention(place=file.place(name.start()), tool=name[0])
        for name in TOOL_NAME.finditer(file.text)
    )


def tool_use(tool: MethodType, mentions: Sequence[Mention], examples: Sequence[Example]) -> ToolUse:
    name = f'{TOOL_PREFIX}{tool.__name__}'
    return ToolUse(
        tool=tool.__name__,
        named_at=tuple(mention.place for mention in mentions if mention.tool == name),
        examples=sum(example.tool == name for example in examples),
    )


def call_model(tool: MethodType) -> type[BaseModel]:
    request = inspect.signature(tool).parameters['request'].annotation
    return create_model(
        tool.__name__, __config__=ConfigDict(extra='forbid'), request=(request, ...)
    )


def call_refusal(call: type[BaseModel], text: str) -> ValidationError | None:
    try:
        call.model_validate_json(text)
    except ValidationError as refusal:
        return refusal
    return None


def refused_fields(refusal: ValidationError) -> str:
    return '; '.join(
        f'{".".join(map(str, error["loc"])) or "text"}: {error["msg"]}'
        for error in refusal.errors()
    )


def example_fault(example: Example, call_models: Mapping[str, type[BaseModel]]) -> str | None:
    if example.tool is None:
        return f'{example.place}: no tool name is written above this example'
    if (call := call_models.get(example.tool)) is None:
        return f'{example.place}: {example.tool} is not a tool the server registers'
    if (refusal := call_refusal(call, example.text)) is None:
        return None
    return f'{example.place}: {example.tool} refuses this example: {refused_fields(refusal)}'


def tool_fault(use: ToolUse) -> str | None:
    if use.examples > 0 or use.named_at == ():
        return None
    return f'{", ".join(use.named_at)}: {use.tool} is named and no example belongs to it'


FILES = tuple(
    map(
        markdown_file,
        sorted(
            chain.from_iterable(
                PLUGIN.joinpath(directory).rglob('*.md') for directory in READ_DIRECTORIES
            )
        ),
    )
)
EXAMPLES = tuple(chain.from_iterable(map(examples_in, FILES)))
MENTIONS = tuple(chain.from_iterable(map(mentions_in, FILES)))
TOOL_USES = tuple(tool_use(tool, MENTIONS, EXAMPLES) for tool in TOOLS)


@pytest.fixture(scope='module')
def call_models() -> Mapping[str, type[BaseModel]]:
    return MappingProxyType({f'{TOOL_PREFIX}{tool.__name__}': call_model(tool) for tool in TOOLS})


class TestToolCallExamples:
    @pytest.mark.parametrize(
        'example', [pytest.param(example, id=example.place) for example in EXAMPLES]
    )
    def test_the_tool_an_example_belongs_to_accepts_it(
        self, example: Example, call_models: Mapping[str, type[BaseModel]]
    ) -> None:
        fault = example_fault(example, call_models)

        assert fault is None, fault

    @pytest.mark.parametrize(
        'use', [pytest.param(use, id=f'{use.tool}-{use.examples}-examples') for use in TOOL_USES]
    )
    def test_a_tool_that_a_file_names_has_an_example(self, use: ToolUse) -> None:
        fault = tool_fault(use)

        assert fault is None, fault

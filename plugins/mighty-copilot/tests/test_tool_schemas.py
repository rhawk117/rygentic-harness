import json
import re
from collections.abc import Generator
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from mightymodels.server import SERVER_NAME
from mightymodels.tools.tests.support import StateServer
from mightymodels.tools.tests.tool_names import TOOL_NAMES

PLUGIN = Path(__file__).parent.parent
PROMPT_DIRECTORIES = ('skills', 'agents')
TOOL_NAME = re.compile(rf'\b{SERVER_NAME}/(\w+)')
JSON_BLOCK = re.compile(r'^[ \t]*```json\n(?P<arguments>.*?)^[ \t]*```$', re.DOTALL | re.MULTILINE)


@dataclass(slots=True, kw_only=True, frozen=True)
class CallExample:
    tool: str
    arguments: str
    location: str


def prompt_documents() -> list[Path]:
    directories = map(PLUGIN.joinpath, PROMPT_DIRECTORIES)
    return sorted(chain.from_iterable(directory.rglob('*.md') for directory in directories))


def call_examples(document: Path) -> Generator[CallExample]:
    text = document.read_text(encoding='utf-8')
    for block in JSON_BLOCK.finditer(text):
        if tools_named_above := TOOL_NAME.findall(text, 0, block.start()):
            line = text.count('\n', 0, block.start('arguments')) + 1
            yield CallExample(
                tool=tools_named_above[-1],
                arguments=block['arguments'],
                location=f'{document.relative_to(PLUGIN)}:{line}',
            )


@pytest.fixture(scope='module')
def published_schemas(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, object]]:
    server = StateServer(
        root=tmp_path_factory.mktemp('plain-directory'),
        data_directory=tmp_path_factory.mktemp('plugin-data'),
    )
    return {name: tool.input_schema for name, tool in server.tools().items()}


class TestToolSchemas:
    SNAPSHOT = Path(__file__).parent.joinpath('fixtures', 'tool-schemas.json')

    @pytest.fixture
    def served_schemas(self, state_server: StateServer) -> dict[str, dict[str, object]]:
        return {
            name: {
                'description': tool.description,
                'input_schema': tool.input_schema,
                'output_schema': tool.output_schema,
            }
            for name, tool in state_server.tools().items()
        }

    def test_each_tool_schema_equals_the_snapshot_taken_before_the_rework(
        self, served_schemas: dict[str, dict[str, object]]
    ) -> None:
        assert served_schemas == json.loads(self.SNAPSHOT.read_text(encoding='utf-8'))


class TestCallExamples:
    EXAMPLES = tuple(chain.from_iterable(map(call_examples, prompt_documents())))

    def test_the_skills_and_agents_hold_a_call_example_of_every_tool(self) -> None:
        assert sorted({example.tool for example in self.EXAMPLES}) == TOOL_NAMES

    @pytest.mark.parametrize(
        'example', [pytest.param(example, id=example.location) for example in EXAMPLES]
    )
    def test_each_call_example_fits_the_schema_its_tool_publishes(
        self, example: CallExample, published_schemas: dict[str, dict[str, object]]
    ) -> None:
        published = Draft202012Validator(published_schemas[example.tool])

        assert [
            error.message for error in published.iter_errors(json.loads(example.arguments))
        ] == []

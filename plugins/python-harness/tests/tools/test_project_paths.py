"""Path inputs of the four project tools: contained in the root, reported when unusable."""

from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path

import pytest
from mcp import Client
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.workspace import Workspace
from python_harness.tools.tests.support import SHOP_PROJECT, document_of, text_of

SENTINEL = 'outside_sentinel_7f3a91'
OUTSIDE_SOURCE = f'def {SENTINEL}() -> None: ...  # absent.py:1 `{SENTINEL}`\n'
PACKAGE = 'src/shop'
LINK_NAME = 'linked.py'
LINK = f'{PACKAGE}/{LINK_NAME}'


class Escape(StrEnum):
    ABSOLUTE = auto()
    PARENT = auto()
    SYMLINK = auto()


@dataclass(frozen=True, slots=True, kw_only=True)
class PathInput:
    tool: str
    argument: str
    takes_many: bool
    detail: str | None = None

    def arguments(self, target: str) -> dict[str, object]:
        arguments = {self.argument: [target] if self.takes_many else target}
        if self.detail is not None:
            arguments['detail'] = self.detail
        return arguments


FACTS = PathInput(tool='collect_python_facts', argument='paths', takes_many=True, detail='full')
CALLS = PathInput(tool='map_python_calls', argument='paths', takes_many=True, detail='full')
SURFACE = PathInput(tool='plan_review_surface', argument='paths', takes_many=True)
DOCUMENT = PathInput(tool='check_citations', argument='path', takes_many=False)
DIRECTORY_INPUTS = [
    pytest.param(FACTS, id='collect_python_facts'),
    pytest.param(CALLS, id='map_python_calls'),
    pytest.param(SURFACE, id='plan_review_surface'),
]
PATH_INPUTS = [*DIRECTORY_INPUTS, pytest.param(DOCUMENT, id='check_citations')]


@pytest.fixture
def outside_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp('outside').joinpath('leak.py')
    path.write_text(OUTSIDE_SOURCE, encoding='utf-8')
    return path


@pytest.fixture
def linked(shop: Workspace, outside_file: Path) -> str:
    shop.root.joinpath(LINK).symlink_to(outside_file)
    return LINK


@pytest.fixture
def escaping_target(request: pytest.FixtureRequest, shop: Workspace, outside_file: Path) -> str:
    targets = {
        Escape.ABSOLUTE: str(outside_file),
        Escape.PARENT: outside_file.relative_to(shop.root, walk_up=True).as_posix(),
        Escape.SYMLINK: LINK,
    }
    if request.param is Escape.SYMLINK:
        shop.root.joinpath(LINK).symlink_to(outside_file)
    return targets[request.param]


ESCAPES = [
    pytest.param(Escape.ABSOLUTE, id='absolute'),
    pytest.param(Escape.PARENT, id='parent'),
    pytest.param(Escape.SYMLINK, id='symlink'),
]


@pytest.mark.anyio
class TestTargetOutsideTheRoot:
    @pytest.mark.parametrize('path_input', PATH_INPUTS)
    @pytest.mark.parametrize('escaping_target', ESCAPES, indirect=True)
    async def test_a_target_that_leaves_the_root_is_a_tool_error_without_its_content(
        self, project_client: Client, path_input: PathInput, escaping_target: str
    ) -> None:
        result = await project_client.call_tool(
            path_input.tool, path_input.arguments(escaping_target)
        )

        assert (result.is_error, SENTINEL in text_of(result)) == (True, False)

    @pytest.mark.usefixtures('linked')
    @pytest.mark.parametrize('path_input', DIRECTORY_INPUTS)
    async def test_a_directory_holding_a_symlink_out_reports_nothing_from_outside(
        self, project_client: Client, path_input: PathInput
    ) -> None:
        result = await project_client.call_tool(path_input.tool, path_input.arguments(PACKAGE))

        text = text_of(result)
        assert (result.is_error, SENTINEL in text, LINK_NAME in text) == (False, False, False)

    @pytest.mark.parametrize('escaping_target', ESCAPES, indirect=True)
    async def test_text_citing_a_path_outside_the_root_marks_it_without_reading_it(
        self, project_client: Client, escaping_target: str
    ) -> None:
        text = f'| {escaping_target}:1 | `def` | defines a function |\n'

        result = await project_client.call_tool('check_citations', {'text': text})

        problems = [failure['problem'] for failure in document_of(result)['failures']]
        assert (problems, SENTINEL in text_of(result)) == (['outside_workspace'], False)


@pytest.mark.anyio
class TestSameContentInsideTheRoot:
    INSIDE = f'{PACKAGE}/inside.py'

    @pytest.fixture
    def shop(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({**SHOP_PROJECT, self.INSIDE: OUTSIDE_SOURCE})

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        'path_input',
        [
            pytest.param(FACTS, id='collect_python_facts'),
            pytest.param(CALLS, id='map_python_calls'),
            pytest.param(DOCUMENT, id='check_citations'),
        ],
    )
    async def test_the_sentinel_is_reported_when_its_file_is_inside_the_root(
        self, project_client: Client, path_input: PathInput
    ) -> None:
        result = await project_client.call_tool(path_input.tool, path_input.arguments(self.INSIDE))

        assert (result.is_error, SENTINEL in text_of(result)) == (False, True)


@pytest.mark.anyio
class TestMissingTarget:
    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        ('path_input', 'target'),
        [
            pytest.param(FACTS, 'src/shop/pricng.py', id='collect_python_facts'),
            pytest.param(CALLS, 'src/shopp', id='map_python_calls'),
            pytest.param(SURFACE, 'src/shopp', id='plan_review_surface'),
            pytest.param(DOCUMENT, 'ABSENT.md', id='check_citations'),
        ],
    )
    async def test_a_missing_target_is_a_tool_error_naming_it(
        self, project_client: Client, path_input: PathInput, target: str
    ) -> None:
        result = await project_client.call_tool(path_input.tool, path_input.arguments(target))

        assert (result.is_error, target in text_of(result)) == (True, True)


@pytest.mark.anyio
class TestUnusablePathText:
    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize('path_input', PATH_INPUTS)
    async def test_a_path_holding_a_null_character_is_rejected_by_name(
        self, project_client: Client, path_input: PathInput
    ) -> None:
        result = await project_client.call_tool(path_input.tool, path_input.arguments('src\x00'))

        assert (result.is_error, path_input.argument in text_of(result)) == (True, True)


@pytest.mark.anyio
class TestUndecodableSource:
    PATH = f'{PACKAGE}/legacy.py'

    @pytest.fixture
    def shop(self, project_builder: ProjectBuilder) -> Workspace:
        workspace = project_builder.write(SHOP_PROJECT)
        workspace.root.joinpath(self.PATH).write_bytes(b'name = "caf\xe9"\n')
        return workspace

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        'path_input',
        [
            pytest.param(FACTS, id='collect_python_facts'),
            pytest.param(SURFACE, id='plan_review_surface'),
        ],
    )
    async def test_an_undecodable_file_is_reported_as_unparsable(
        self, project_client: Client, path_input: PathInput
    ) -> None:
        result = await project_client.call_tool(path_input.tool, path_input.arguments(PACKAGE))

        document = document_of(result)
        facts = document['result'] if path_input.tool == FACTS.tool else document
        unparsable = [item['path'] for item in facts['unparsable']]
        assert (result.is_error, unparsable) == (False, [self.PATH])

"""plan_review_surface over MCP: a codebase or diff target planned as import clusters."""

from collections.abc import Callable
from pathlib import Path

import anyio
import pytest
from mcp import Client
from mcp.types import CallToolResult
from python_harness.core.output import to_json_value
from python_harness.core.tests.fixtures import GitProject
from python_harness.core.tests.support import JsonDocument
from python_harness.core.workspace import Workspace
from python_harness.surface.domain import CodebaseTarget, DiffTarget
from python_harness.surface.services import plan_surface
from python_harness.tools.tests.support import SHOP_PROJECT, document_of, text_of

TOOL = 'plan_review_surface'


@pytest.fixture
def branched(git_project: GitProject) -> Workspace:
    git_project.commit(SHOP_PROJECT, 'base')
    git_project.switch_to_new_branch('feature')
    return git_project.commit({'src/shop/pricing.py': 'def price() -> int: ...\n'}, 'x')


@pytest.mark.anyio
class TestCodebaseSurface:
    PATHS = ('src',)

    async def test_result_is_the_surface_plan_as_json(
        self,
        project_client: Client,
        shop: Workspace,
        project_report_of: Callable[[CallToolResult], JsonDocument],
    ) -> None:
        result = await project_client.call_tool(TOOL, {'paths': list(self.PATHS)})

        expected = plan_surface(shop, CodebaseTarget(self.PATHS))
        assert (result.is_error, project_report_of(result)) == (False, to_json_value(expected))

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        ('arguments', 'expected'),
        [
            pytest.param({'paths': ['src']}, ['src'], id='one-path'),
            pytest.param(
                {'paths': ['src/shop/pricing.py', 'src/shop/cli.py']},
                ['src/shop/pricing.py', 'src/shop/cli.py'],
                id='several-paths',
            ),
            pytest.param({}, ['.'], id='defaults-to-the-root'),
        ],
    )
    async def test_codebase_paths_become_the_target(
        self, project_client: Client, arguments: dict[str, list[str]], expected: list[str]
    ) -> None:
        plan = document_of(await project_client.call_tool(TOOL, arguments))

        assert plan['target'] == {'kind': 'codebase', 'paths': expected}


@pytest.mark.anyio
class TestDiffSurface:
    async def test_result_is_the_surface_plan_as_json(
        self,
        project_client: Client,
        branched: Workspace,
        project_report_of: Callable[[CallToolResult], JsonDocument],
    ) -> None:
        result = await project_client.call_tool(TOOL, {'diff_base': 'main'})

        expected = plan_surface(branched, DiffTarget('main'))
        assert (result.is_error, project_report_of(result)) == (False, to_json_value(expected))

    @pytest.mark.usefixtures('branched')
    async def test_diff_surface_holds_only_changed_modules(self, project_client: Client) -> None:
        plan = document_of(await project_client.call_tool(TOOL, {'diff_base': 'main'}))

        assert plan['module_count'] == 1

    @pytest.mark.usefixtures('branched')
    @pytest.mark.parametrize(
        ('arguments', 'expected'),
        [
            pytest.param(
                {'diff_base': 'main'},
                {'base': 'main', 'head': 'HEAD', 'kind': 'diff'},
                id='head-defaults-to-the-checkout',
            ),
            pytest.param(
                {'diff_base': 'main', 'diff_head': 'feature'},
                {'base': 'main', 'head': 'feature', 'kind': 'diff'},
                id='named-head',
            ),
        ],
    )
    async def test_diff_target(
        self, project_client: Client, arguments: dict[str, str], expected: JsonDocument
    ) -> None:
        plan = document_of(await project_client.call_tool(TOOL, arguments))

        assert plan['target'] == expected


@pytest.mark.anyio
class TestTargetChoice:
    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        ('arguments', 'expected'),
        [
            pytest.param(
                {'paths': ['src'], 'diff_base': 'main'},
                'give paths or diff_base, not both',
                id='paths-with-a-diff-base',
            ),
            pytest.param(
                {'diff_head': 'feature'},
                'diff_head feature needs diff_base',
                id='head-without-base',
            ),
            pytest.param(
                {'paths': ['src'], 'diff_head': 'feature'},
                'diff_head feature needs diff_base',
                id='paths-with-a-head',
            ),
        ],
    )
    async def test_a_target_that_is_not_one_choice_is_a_tool_error(
        self, project_client: Client, arguments: dict[str, object], expected: str
    ) -> None:
        result = await project_client.call_tool(TOOL, arguments)

        assert (result.is_error, expected in text_of(result)) == (True, True)


@pytest.mark.anyio
class TestOptionLikeRevision:
    @pytest.fixture
    def output_directory(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return tmp_path_factory.mktemp('output')

    @pytest.mark.usefixtures('branched')
    @pytest.mark.parametrize(
        'argument',
        [pytest.param('diff_base', id='base'), pytest.param('diff_head', id='head')],
    )
    async def test_a_revision_starting_with_a_dash_is_refused_and_writes_nothing(
        self, project_client: Client, output_directory: Path, argument: str
    ) -> None:
        option = f'--output={output_directory.joinpath("leak")}'

        result = await project_client.call_tool(TOOL, {'diff_base': 'main', argument: option})

        written = [entry async for entry in anyio.Path(output_directory).iterdir()]
        assert (result.is_error, written) == (True, [])


@pytest.mark.anyio
@pytest.mark.usefixtures('shop')
class TestWorkspaceDiagnostics:
    async def test_plan_review_surface_reports_the_workspace_in_its_diagnostics(
        self, project_client: Client
    ) -> None:
        result = await project_client.call_tool(TOOL, {'paths': ['src']})

        diagnostics = document_of(result)['diagnostics']
        assert (result.is_error, sorted(diagnostics)) == (
            False,
            ['external_packages', 'fallback_diagnostics', 'source_roots'],
        )

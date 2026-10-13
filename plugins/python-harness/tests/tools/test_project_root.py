"""The project root: CLAUDE_PROJECT_DIR alone, and a tool error when it names no project."""

from pathlib import Path

import pytest
from mcp import Client
from python_harness.documentation.tests.support import DOCS_VERSION
from python_harness.tools.project import PROJECT_ROOT_VARIABLE

TEMPORARY = '<tmp>'
PORTED_CALLS = [
    pytest.param('collect_python_facts', {'paths': ['.']}, id='collect_python_facts'),
    pytest.param('map_python_calls', {'paths': ['.']}, id='map_python_calls'),
    pytest.param('check_citations', {'text': 'no citations'}, id='check_citations'),
    pytest.param('plan_review_surface', {}, id='plan_review_surface'),
    pytest.param('survey', {}, id='survey'),
    pytest.param('gate', {}, id='gate'),
]


@pytest.mark.anyio
class TestUnusableProjectRoot:
    @pytest.fixture
    def project_environment(self, request: pytest.FixtureRequest, tmp_path: Path) -> dict[str, str]:
        declared = request.param
        if declared is None:
            return {}
        return {PROJECT_ROOT_VARIABLE: declared.replace(TEMPORARY, str(tmp_path))}

    @pytest.mark.parametrize(('tool', 'arguments'), PORTED_CALLS)
    @pytest.mark.parametrize(
        'project_environment',
        [
            pytest.param(None, id='unset'),
            pytest.param('', id='empty'),
            pytest.param('project', id='relative'),
            pytest.param('${CLAUDE_PROJECT_DIR}', id='unexpanded'),
            pytest.param(f'{TEMPORARY}/absent', id='no-such-directory'),
        ],
        indirect=True,
    )
    async def test_a_ported_tool_reports_the_root_while_documentation_still_answers(
        self, project_client: Client, tool: str, arguments: dict[str, object]
    ) -> None:
        ported = await project_client.call_tool(tool, arguments)
        search = await project_client.call_tool(
            'search_python_docs', {'version': DOCS_VERSION, 'query': 'path join'}
        )

        assert (ported.is_error, search.is_error) == (True, False)


@pytest.mark.anyio
class TestRootNamedOnlyByTheVariable:
    @pytest.fixture
    def elsewhere(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        directory = tmp_path_factory.mktemp('elsewhere')
        directory.joinpath('stray.py').write_text('stray = 1\n', encoding='utf-8')
        return directory

    @pytest.mark.usefixtures('shop')
    async def test_the_working_directory_is_not_the_project(
        self, project_client: Client, elsewhere: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(elsewhere)

        result = await project_client.call_tool('collect_python_facts', {'paths': ['stray.py']})

        assert result.is_error

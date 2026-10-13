"""A collect_python_facts call reads and parses each Python file once."""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from mcp import Client
from python_harness.core import sources
from python_harness.core.sources import ParseOutcome, SourceFile, parse_source, read_source
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.workspace import Workspace
from python_harness.tools.tests.support import SHOP_PROJECT

TOOL = 'collect_python_facts'
GENERATED = 'build/generated.py'
INDEXED = ('src/shop/__init__.py', 'src/shop/cli.py', 'src/shop/pricing.py')


@dataclass(frozen=True, slots=True)
class SourceLoads:
    reads: Counter[str] = field(default_factory=Counter)
    parses: Counter[str] = field(default_factory=Counter)


@pytest.fixture
def source_loads(monkeypatch: pytest.MonkeyPatch) -> SourceLoads:
    loads = SourceLoads()

    def read_and_count(workspace: Workspace, path: Path) -> SourceFile:
        loads.reads[workspace.relative(path)] += 1
        return read_source(workspace, path)

    def parse_and_count(source: SourceFile) -> ParseOutcome:
        loads.parses[source.path] += 1
        return parse_source(source)

    monkeypatch.setattr(sources, 'read_source', read_and_count)
    monkeypatch.setattr(sources, 'parse_source', parse_and_count)
    return loads


@pytest.mark.anyio
class TestSourceLoads:
    @pytest.fixture
    def shop(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({**SHOP_PROJECT, GENERATED: 'VALUE = 1\n'})

    @pytest.mark.usefixtures('shop')
    @pytest.mark.parametrize(
        ('paths', 'loaded'),
        [
            pytest.param(['.'], INDEXED, id='whole-project'),
            pytest.param(
                ['.', GENERATED], (GENERATED, *INDEXED), id='with-a-file-the-index-leaves-out'
            ),
        ],
    )
    async def test_a_facts_call_reads_and_parses_each_file_once(
        self,
        project_client: Client,
        source_loads: SourceLoads,
        paths: list[str],
        loaded: tuple[str, ...],
    ) -> None:
        result = await project_client.call_tool(TOOL, {'paths': paths})

        once = dict.fromkeys(loaded, 1)
        assert (result.is_error, dict(source_loads.reads), dict(source_loads.parses)) == (
            False,
            once,
            once,
        )

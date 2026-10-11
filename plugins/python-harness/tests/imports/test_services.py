"""Module naming, binding collection and edge building for the import graph."""

from pathlib import Path
from types import MappingProxyType

import pytest
from python_harness.core.tests.fixtures import ProjectBuilder, stubbed_uv
from python_harness.core.workspace import DiscoveryOptions, Workspace, open_workspace
from python_harness.imports.domain import ImportEdge, ImportGraph, ProjectIndex
from python_harness.imports.services import load_project_index, module_name_for

PROJECT = MappingProxyType(
    {
        'src/shop/__init__.py': 'from shop.orders import place_order\n',
        'src/shop/orders.py': """
            import json
            from . import pricing
            from .stock import reserve as hold
            from shop.audit.log import record

            def place_order():
                return pricing, hold, record, json
        """,
        'src/shop/pricing.py': 'from fastapi import APIRouter\n',
        'src/shop/stock.py': 'def reserve(): ...\n',
        'src/shop/audit/__init__.py': 'from .log import *\n',
        'src/shop/audit/log.py': 'import shop.pricing\n\ndef record(): ...\n',
        'tests/test_orders.py': 'from shop.orders import place_order\n',
    }
)


@pytest.fixture
def workspace(project_builder: ProjectBuilder) -> Workspace:
    return project_builder.write(PROJECT)


@pytest.fixture
def graph(workspace: Workspace) -> ImportGraph:
    return load_project_index(workspace).graph


class TestModuleNameFor:
    @pytest.mark.parametrize(
        ('path', 'expected'),
        [
            pytest.param('src/shop/__init__.py', 'shop', id='package'),
            pytest.param('src/shop/audit/log.py', 'shop.audit.log', id='nested-module'),
            pytest.param('tests/test_orders.py', 'tests.test_orders', id='outside-src'),
        ],
    )
    def test_names_follow_the_source_root(
        self, workspace: Workspace, path: str, expected: str
    ) -> None:
        assert module_name_for(workspace, path) == expected

    def test_most_specific_source_root_wins(self, project_builder: ProjectBuilder) -> None:
        project_builder.write({'packages/member/src/member/module.py': ''})
        root = project_builder.root

        def list_members(_: Path) -> str:
            return '\n'.join((str(root), str(root.joinpath('packages', 'member'))))

        workspace = open_workspace(root, uv_runner=list_members)

        assert module_name_for(workspace, 'packages/member/src/member/module.py') == 'member.module'


class TestEdges:
    @pytest.mark.parametrize(
        ('importer', 'expected'),
        [
            pytest.param(
                'shop.orders',
                ('shop.audit.log', 'shop.pricing', 'shop.stock'),
                id='relative-absolute-and-aliased',
            ),
            pytest.param('shop.audit', ('shop.audit.log',), id='star-import'),
            pytest.param('shop.audit.log', ('shop.pricing',), id='plain-dotted-import'),
            pytest.param('tests.test_orders', ('shop.orders',), id='tests-import-src'),
        ],
    )
    def test_dependencies_resolve_to_project_modules(
        self, graph: ImportGraph, importer: str, expected: tuple[str, ...]
    ) -> None:
        assert graph.dependencies_of(importer) == expected

    def test_dependents_are_the_reverse_edges(self, graph: ImportGraph) -> None:
        assert graph.dependents_of('shop.pricing') == ('shop.audit.log', 'shop.orders')

    def test_edges_keep_the_first_import_line(self, graph: ImportGraph) -> None:
        edge = next(item for item in graph.edges if item.imported == 'shop.stock')

        assert edge == ImportEdge('shop.orders', 'shop.stock', 3)


class TestBindings:
    def test_aliased_from_import_binds_the_alias(self, graph: ImportGraph) -> None:
        binding = next(
            item for item in graph.bindings_in('shop.orders') if item.local_name == 'hold'
        )

        assert binding.bound_name == 'shop.stock.reserve'

    def test_external_packages_exclude_project_packages(self, graph: ImportGraph) -> None:
        assert graph.external_packages == frozenset({'fastapi', 'json'})


class TestTestModules:
    @pytest.mark.parametrize(
        ('module', 'expected'),
        [
            pytest.param('tests.test_orders', True, id='module-under-tests'),
            pytest.param('shop.orders', False, id='source-module'),
        ],
    )
    def test_module_refs_carry_the_workspace_test_rule(
        self, graph: ImportGraph, module: str, *, expected: bool
    ) -> None:
        assert graph.modules[module].is_test is expected


class TestConfiguredTestFileNames:
    FILES = MappingProxyType(
        {
            'src/shop/__init__.py': '',
            'src/shop/orders.py': '',
            'src/shop/orders_spec.py': '',
            'src/shop/check_orders.py': '',
            'src/shop/test_orders.py': '',
        }
    )
    OPTIONS = DiscoveryOptions(test_file_prefixes=('check_',), test_file_suffixes=('_spec.py',))

    @pytest.fixture
    def graph(self, project_builder: ProjectBuilder) -> ImportGraph:
        project_builder.write(self.FILES)
        return load_project_index(
            open_workspace(project_builder.root, self.OPTIONS, uv_runner=stubbed_uv)
        ).graph

    @pytest.mark.parametrize(
        ('module', 'expected'),
        [
            pytest.param('shop.orders_spec', True, id='configured-suffix'),
            pytest.param('shop.check_orders', True, id='configured-prefix'),
            pytest.param('shop.test_orders', False, id='default-prefix-replaced'),
            pytest.param('shop.orders', False, id='source-module'),
        ],
    )
    def test_configured_file_names_mark_test_modules(
        self, graph: ImportGraph, module: str, *, expected: bool
    ) -> None:
        assert graph.modules[module].is_test is expected


class TestLoadProjectIndex:
    FILES = MappingProxyType(
        {
            'src/shop/__init__.py': '',
            'src/shop/orders.py': 'from shop import pricing\n',
            'src/shop/pricing.py': 'RATE = 2\n',
            'src/shop/broken.py': 'def broken(:\n',
        }
    )
    PARSED = ('src/shop/__init__.py', 'src/shop/orders.py', 'src/shop/pricing.py')

    @pytest.fixture
    def index(self, project_builder: ProjectBuilder) -> ProjectIndex:
        return load_project_index(project_builder.write(self.FILES))

    def test_graph_covers_every_parsed_module(self, index: ProjectIndex) -> None:
        graphed = tuple(sorted(ref.path for ref in index.graph.modules.values()))

        assert graphed == self.PARSED

    def test_unparsable_files_stay_in_the_sources(self, index: ProjectIndex) -> None:
        unparsable = tuple(item.path for item in index.sources.unparsable)

        assert unparsable == ('src/shop/broken.py',)

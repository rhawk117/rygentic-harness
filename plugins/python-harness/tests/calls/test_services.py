"""Reference summaries, symbol drill-downs and coupling facts for target modules."""

from itertools import chain
from pathlib import Path
from types import MappingProxyType

import pytest
from python_harness.calls.domain import (
    CallsReport,
    ModuleCalls,
    ModuleMetrics,
    Reference,
    ReferenceContext,
    SymbolSummary,
)
from python_harness.calls.errors import UnknownTargetPathsError
from python_harness.calls.services import (
    find_symbol_references_for,
    map_call_sites_for,
)
from python_harness.core.errors import PathOutsideWorkspaceError
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.tests.support import emit_document
from python_harness.core.workspace import Workspace, open_workspace
from python_harness.imports.domain import ExternalPackage
from python_harness.imports.services import external_packages_for, load_project_index

PROJECT = MappingProxyType(
    {
        'src/shop/__init__.py': '',
        'src/shop/models.py': """
            class Order:
                def __init__(self, total: int) -> None:
                    self.total = total

                def scaled(self, factor: int, offset: int, limit: int) -> int:
                    return min(self.total * factor + offset, limit)


            class Receipt:
                pass


            TAX_RATE = 2


            def _round(value: int, places: int) -> int:
                return value


            def place(total: int) -> Order:
                def build() -> Order:
                    return Order(total * TAX_RATE)

                if total:
                    total += 1
                return build()
        """,
        'src/shop/billing.py': """
            from shop.models import Order as PlacedOrder, Receipt


            def bill(order: PlacedOrder) -> Receipt:
                return order
        """,
        'src/shop/api.py': """
            import shop.models
            import shop.models as catalog


            def submit() -> int:
                order = shop.models.place(shop.models.TAX_RATE)
                return catalog.Order(order.total).total
        """,
        'tests/test_models.py': """
            from shop.models import place


            def test_place() -> None:
                assert place(1).total == 1
        """,
    }
)
TARGET_PATHS = ('src/shop/__init__.py', 'src/shop/billing.py', 'src/shop/models.py')


@pytest.fixture
def workspace(project_builder: ProjectBuilder) -> Workspace:
    return project_builder.write(PROJECT)


@pytest.fixture
def report(workspace: Workspace) -> CallsReport:
    return map_call_sites_for(workspace, TARGET_PATHS)


class TestSymbolSummaries:
    ORDER_REACH = (6, ['src/shop/api.py', 'src/shop/billing.py'])
    EXTERNAL = (
        ('shop', ()),
        ('shop.billing', ()),
        ('shop.models', ('Order', 'Receipt', 'TAX_RATE', 'place')),
    )
    UNREFERENCED = (
        ('shop', ()),
        ('shop.billing', ('bill',)),
        ('shop.models', ('_round',)),
    )

    def summary_of(self, report: CallsReport, name: str) -> SymbolSummary:
        symbols = chain.from_iterable(item.external for item in report.modules)
        return next(item for item in symbols if item.name == name)

    def external_names_in(self, module: ModuleCalls) -> tuple[str, ...]:
        return tuple(item.name for item in module.external)

    @pytest.mark.parametrize(
        ('name', 'expected'),
        [
            pytest.param(
                'Order',
                (
                    (ReferenceContext.CALL, 2),
                    (ReferenceContext.IMPORT, 1),
                    (ReferenceContext.ANNOTATION, 3),
                ),
                id='aliased-import-annotations-and-attribute-call',
            ),
            pytest.param(
                'Receipt',
                ((ReferenceContext.IMPORT, 1), (ReferenceContext.ANNOTATION, 1)),
                id='class-used-only-in-annotations',
            ),
            pytest.param(
                'TAX_RATE',
                ((ReferenceContext.NAME, 2),),
                id='dotted-module-attribute-chain',
            ),
        ],
    )
    def test_context_counts_tally_each_kind_of_use_in_enum_order(
        self,
        report: CallsReport,
        name: str,
        expected: tuple[tuple[ReferenceContext, int], ...],
    ) -> None:
        summary = self.summary_of(report, name)

        assert tuple(summary.context_counts.items()) == expected

    def test_emitted_counts_cover_every_reference_and_paths_leave_out_the_definer(
        self, report: CallsReport
    ) -> None:
        document = emit_document(report)

        external = chain.from_iterable(item['external'] for item in document['modules'])
        order = next(item for item in external if item['name'] == 'Order')
        reach = (sum(order['context_counts'].values()), order['referencing_paths'])
        assert reach == self.ORDER_REACH

    def test_symbols_used_from_other_files_keep_their_summary_in_definition_order(
        self, report: CallsReport
    ) -> None:
        groups = tuple(
            (item.metrics.module, self.external_names_in(item)) for item in report.modules
        )

        assert groups == self.EXTERNAL

    def test_symbols_without_references_are_listed_by_name(self, report: CallsReport) -> None:
        groups = tuple((item.metrics.module, item.unreferenced) for item in report.modules)

        assert groups == self.UNREFERENCED


class TestSymbolGroups:
    FILES = MappingProxyType(
        {
            'pkg/__init__.py': '',
            'pkg/rates.py': """
                RATE = 2


                def _scale(value: int) -> int:
                    return value * RATE


                def price(value: int) -> int:
                    return _scale(value)


                def _unused() -> None: ...
            """,
            'pkg/shop.py': 'from pkg.rates import price\n',
        }
    )
    TARGET_PATHS = ('pkg/rates.py',)
    EXPECTED = (('price',), ('RATE', '_scale'), ('_unused',))

    @pytest.fixture
    def module(self, project_builder: ProjectBuilder) -> ModuleCalls:
        workspace = project_builder.write(self.FILES)
        return map_call_sites_for(workspace, self.TARGET_PATHS).modules[0]

    def test_symbols_split_by_whether_other_files_or_only_their_module_use_them(
        self, module: ModuleCalls
    ) -> None:
        external = tuple(item.name for item in module.external)

        assert (external, module.internal_only, module.unreferenced) == self.EXPECTED


class TestSymbolReferences:
    EXPECTED = MappingProxyType(
        {
            'Order': (
                Reference('src/shop/api.py', 7, ReferenceContext.CALL),
                Reference('src/shop/billing.py', 1, ReferenceContext.IMPORT),
                Reference('src/shop/billing.py', 4, ReferenceContext.ANNOTATION),
                Reference('src/shop/models.py', 20, ReferenceContext.ANNOTATION),
                Reference('src/shop/models.py', 21, ReferenceContext.ANNOTATION),
                Reference('src/shop/models.py', 22, ReferenceContext.CALL),
            ),
            'Receipt': (
                Reference('src/shop/billing.py', 1, ReferenceContext.IMPORT),
                Reference('src/shop/billing.py', 4, ReferenceContext.ANNOTATION),
            ),
            'TAX_RATE': (
                Reference('src/shop/api.py', 6, ReferenceContext.NAME),
                Reference('src/shop/models.py', 22, ReferenceContext.NAME),
            ),
            'place': (
                Reference('src/shop/api.py', 6, ReferenceContext.CALL),
                Reference('tests/test_models.py', 1, ReferenceContext.IMPORT),
                Reference('tests/test_models.py', 5, ReferenceContext.CALL),
            ),
            '_round': (),
        }
    )

    @pytest.mark.parametrize(
        'name',
        [
            pytest.param('Order', id='aliased-import-annotations-and-attribute-call'),
            pytest.param('Receipt', id='class-used-only-in-annotations'),
            pytest.param('TAX_RATE', id='dotted-module-attribute-chain'),
            pytest.param('place', id='called-from-a-test-and-a-dotted-chain'),
            pytest.param('_round', id='unreferenced-private-function'),
        ],
    )
    def test_references_carry_location_and_context(self, workspace: Workspace, name: str) -> None:
        found = find_symbol_references_for(workspace, TARGET_PATHS, name)

        assert tuple(item.references for item in found.symbols) == (self.EXPECTED[name],)

    def test_module_qualified_name_selects_the_symbol(self, workspace: Workspace) -> None:
        found = find_symbol_references_for(workspace, TARGET_PATHS, 'shop.models.Order')

        assert tuple(item.references for item in found.symbols) == (self.EXPECTED['Order'],)

    def test_unmatched_name_gives_no_symbols(self, workspace: Workspace) -> None:
        found = find_symbol_references_for(workspace, TARGET_PATHS, 'Invoice')

        assert found.symbols == ()


class TestSharedNames:
    FILES = MappingProxyType(
        {
            'pkg/__init__.py': '',
            'pkg/disk.py': 'def load() -> None: ...\n',
            'pkg/network.py': 'def load() -> None: ...\n',
            'pkg/app.py': 'from pkg.disk import load\n',
        }
    )
    TARGET_PATHS = ('pkg/disk.py', 'pkg/network.py')

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    @pytest.mark.parametrize(
        ('name', 'expected'),
        [
            pytest.param(
                'load', ('pkg.disk.load', 'pkg.network.load'), id='bare-name-matches-both'
            ),
            pytest.param(
                'pkg.network.load', ('pkg.network.load',), id='qualified-name-matches-one'
            ),
        ],
    )
    def test_requested_name_selects_matching_definitions(
        self, workspace: Workspace, name: str, expected: tuple[str, ...]
    ) -> None:
        found = find_symbol_references_for(workspace, self.TARGET_PATHS, name)

        qualified = tuple(item.definition.qualified_name() for item in found.symbols)
        assert qualified == expected


class TestModuleMetrics:
    MODELS = ModuleMetrics(
        path='src/shop/models.py',
        module='shop.models',
        fan_in=3,
        fan_out=0,
        public_symbols=4,
        private_symbols=1,
        function_count=5,
        max_function_statements=3,
        max_parameters=3,
        test_paths=('tests/test_models.py',),
    )

    def metrics_of(self, report: CallsReport, module: str) -> ModuleMetrics:
        found = (item.metrics for item in report.modules)
        return next(item for item in found if item.module == module)

    def test_counts_cover_coupling_symbols_and_functions(self, report: CallsReport) -> None:
        assert self.metrics_of(report, 'shop.models') == self.MODELS

    @pytest.mark.parametrize(
        ('module', 'expected'),
        [
            pytest.param('shop.models', 0.0, id='only-imported'),
            pytest.param('shop.billing', 1.0, id='only-importing'),
            pytest.param('shop', None, id='no-project-imports'),
        ],
    )
    def test_instability_is_the_outgoing_share_of_coupling(
        self, report: CallsReport, module: str, expected: float | None
    ) -> None:
        assert self.metrics_of(report, module).instability == expected


class TestWorkspaceFanIn:
    FILES = MappingProxyType(
        {
            'members/one/src/one/__init__.py': 'from two import value\n',
            'members/one/src/one/value.py': 'VALUE = 1\n',
            'members/two/src/two/__init__.py': 'from one import value\n',
            'members/two/src/two/value.py': 'VALUE = 2\n',
            'members/two/src/shared/py.typed': '',
        }
    )
    TARGET = 'members/one/src/one/value.py'

    def test_workspace_fan_in_from_uv_members(self, project_builder: ProjectBuilder) -> None:
        project_builder.write(self.FILES)
        root = project_builder.root
        members = (root.joinpath('members', 'one'), root.joinpath('members', 'two'))

        def list_members(_: Path) -> str:
            return '\n'.join(str(member) for member in members)

        workspace = open_workspace(root, uv_runner=list_members)
        report = map_call_sites_for(workspace, (self.TARGET,))
        metrics = report.modules[0].metrics

        assert (metrics.module, metrics.fan_in) == ('one.value', 1)

    def test_in_workspace_external_package_has_a_relative_directory(
        self, project_builder: ProjectBuilder
    ) -> None:
        project_builder.write(
            {**self.FILES, 'members/one/src/one/use.py': 'from shared import value\n'}
        )
        root = project_builder.root
        members = (root.joinpath('members', 'one'), root.joinpath('members', 'two'))

        def list_members(_: Path) -> str:
            return '\n'.join(str(member) for member in members)

        workspace = open_workspace(root, uv_runner=list_members)
        graph = load_project_index(workspace).graph

        assert external_packages_for(workspace, graph) == (
            ExternalPackage('shared', 'members/two/src/shared'),
        )


class TestTargets:
    FILES = MappingProxyType(
        {
            'src/shop/__init__.py': '',
            'src/shop/orders.py': 'def place() -> None: ...\n',
            'src/shop/broken.py': 'def broken(:\n',
            'build/generated.py': 'VALUE = 1\n',
        }
    )
    TARGET_PATHS = ('src/shop',)
    MEASURED = ('shop', 'shop.orders')
    UNPARSABLE = ('src/shop/broken.py',)
    UNDISCOVERED = frozenset({'build/generated.py'})

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    def test_parsable_targets_are_measured_beside_an_unparsable_one(
        self, workspace: Workspace
    ) -> None:
        report = map_call_sites_for(workspace, self.TARGET_PATHS)

        assert tuple(item.metrics.module for item in report.modules) == self.MEASURED

    def test_unparsable_target_is_reported_in_the_summary(self, workspace: Workspace) -> None:
        report = map_call_sites_for(workspace, self.TARGET_PATHS)

        assert tuple(item.path for item in report.unparsable) == self.UNPARSABLE

    def test_unparsable_target_is_reported_in_the_drill_down(self, workspace: Workspace) -> None:
        found = find_symbol_references_for(workspace, self.TARGET_PATHS, 'place')

        assert tuple(item.path for item in found.unparsable) == self.UNPARSABLE

    def test_target_outside_discovery_is_reported(self, workspace: Workspace) -> None:
        with pytest.raises(UnknownTargetPathsError) as caught:
            map_call_sites_for(workspace, (*self.TARGET_PATHS, *self.UNDISCOVERED))

        assert caught.value.paths == self.UNDISCOVERED

    def test_target_outside_the_root_is_reported(self, workspace: Workspace) -> None:
        with pytest.raises(PathOutsideWorkspaceError):
            map_call_sites_for(workspace, ('../elsewhere.py',))


class TestTestImporters:
    FILES = MappingProxyType(
        {
            'src/shop/__init__.py': '',
            'src/shop/pricing.py': 'def price() -> int: ...\n',
            'src/shop/api.py': 'from shop.pricing import price\n',
            'src/shop/pricing_test.py': 'from shop.pricing import price\n',
            'test/helpers.py': 'from shop.pricing import price\n',
        }
    )
    TARGET_PATHS = ('src/shop/pricing.py',)
    EXPECTED = ('src/shop/pricing_test.py', 'test/helpers.py')

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    def test_test_directory_and_test_suffix_importers_are_test_paths(
        self, workspace: Workspace
    ) -> None:
        report = map_call_sites_for(workspace, self.TARGET_PATHS)

        assert report.modules[0].metrics.test_paths == self.EXPECTED


class TestDocuments:
    SUMMARY_SYMBOL_KEYS = frozenset(
        {
            'name',
            'kind',
            'line',
            'referencing_paths',
            'context_counts',
        }
    )
    DEFINITION_KEYS = frozenset({'module', 'path', 'name', 'kind', 'line', 'is_public'})
    MODULE_KEYS = frozenset({'metrics', 'external', 'internal_only', 'unreferenced'})

    def test_module_entries_pair_metrics_with_grouped_symbols(self, report: CallsReport) -> None:
        document = emit_document(report)

        assert {frozenset(item) for item in document['modules']} == {self.MODULE_KEYS}

    def test_external_symbols_carry_only_what_their_module_does_not(
        self, report: CallsReport
    ) -> None:
        document = emit_document(report)

        symbols = chain.from_iterable(item['external'] for item in document['modules'])
        assert {frozenset(item) for item in symbols} == {self.SUMMARY_SYMBOL_KEYS}

    def test_drill_down_keeps_the_definition_without_a_qualified_name(
        self, workspace: Workspace
    ) -> None:
        report = find_symbol_references_for(workspace, TARGET_PATHS, 'Order')

        document = emit_document(report)

        definitions = (item['definition'] for item in document['symbols'])
        assert {frozenset(item) for item in definitions} == {self.DEFINITION_KEYS}

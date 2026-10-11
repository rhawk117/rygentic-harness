"""Planning a review surface from a codebase path or a git diff."""

from types import MappingProxyType

import pytest
from python_harness.core.errors import TargetPathMissingError
from python_harness.core.tests.fixtures import GitProject, ProjectBuilder
from python_harness.core.workspace import Workspace
from python_harness.imports.services import load_project_index
from python_harness.surface.domain import CodebaseTarget, DiffTarget, SurfaceOptions
from python_harness.surface.services import plan_surface


class TestEmptyModules:
    FILES = MappingProxyType(
        {
            'src/shop/__init__.py': '',
            'src/shop/core/__init__.py': '"""Stock keeping for the shop."""\n',
            'src/shop/core/notes.py': '# nothing here yet\n',
            'src/shop/core/rates.py': '"""Rates."""\n\nRATE = 2\n',
            'src/shop/core/stock.py': 'def reserve() -> None: ...\n',
        }
    )
    TARGET = CodebaseTarget(('src/shop',))
    CLUSTERED = (('src/shop/core/rates.py',), ('src/shop/core/stock.py',))

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    def test_modules_without_code_beyond_a_docstring_cost_no_dispatch(
        self, workspace: Workspace
    ) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET)

        clustered = tuple(tuple(item.path for item in cluster.modules) for cluster in plan.clusters)
        assert clustered == self.CLUSTERED


class TestPlanSurfaceForCodebase:
    FILES = MappingProxyType(
        {
            'src/shop/__init__.py': '',
            'src/shop/api.py': 'from shop.core.pricing import price\n',
            'src/shop/core/models.py': 'class Order:\n    total = 0\n',
            'src/shop/core/pricing.py': """
                from shop.core.models import Order


                def price(order: Order) -> int:
                    return order.total
            """,
            'src/shop/core/stock.py': 'def reserve() -> None: ...\n',
            'src/shop/core/broken.py': 'def broken(:\n',
            'tests/test_pricing.py': 'from shop.core.pricing import price\n',
        }
    )
    TARGET = CodebaseTarget(('src/shop/core',))
    MODULE_COUNT = 3
    LINE_COUNT = 8

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    def test_modules_that_import_each_other_share_a_cluster(self, workspace: Workspace) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET)

        grouped = tuple(tuple(item.module for item in cluster.modules) for cluster in plan.clusters)
        assert grouped == (
            ('shop.core.models', 'shop.core.pricing'),
            ('shop.core.stock',),
        )

    def test_cluster_ids_number_the_clusters_in_order(self, workspace: Workspace) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET)

        assert tuple(cluster.id for cluster in plan.clusters) == ('c01', 'c02')

    def test_tests_and_outside_importers_attach_to_the_imported_cluster(
        self, workspace: Workspace
    ) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET)

        attached = tuple((cluster.tests, cluster.dependents) for cluster in plan.clusters)
        assert attached == ((('tests/test_pricing.py',), ('src/shop/api.py',)), ((), ()))

    def test_totals_cover_every_clustered_module(self, workspace: Workspace) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET)

        assert (plan.module_count, plan.line_count) == (
            self.MODULE_COUNT,
            self.LINE_COUNT,
        )

    def test_unparsable_surface_files_are_reported(self, workspace: Workspace) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET)

        assert tuple(item.path for item in plan.unparsable) == ('src/shop/core/broken.py',)

    @pytest.mark.parametrize(
        ('budget', 'expected'),
        [
            pytest.param(1, True, id='more-clusters-than-budget'),
            pytest.param(2, False, id='clusters-fill-the-budget'),
        ],
    )
    def test_over_budget_compares_dispatches_with_the_budget(
        self, workspace: Workspace, budget: int, *, expected: bool
    ) -> None:
        options = SurfaceOptions(dispatch_budget=budget)

        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET, options=options)

        assert plan.over_budget is expected


class TestPlanSurfaceForDiff:
    BASE = MappingProxyType(
        {
            'src/shop/__init__.py': '',
            'src/shop/models.py': 'class Order:\n    total = 0\n',
            'src/shop/pricing.py': """
                from shop.models import Order


                def price(order: Order) -> int:
                    return order.total
            """,
            'src/shop/api.py': 'from shop.pricing import price\n',
            'tests/test_pricing.py': 'from shop.pricing import price\n',
        }
    )
    CHANGE = MappingProxyType(
        {
            'src/shop/pricing.py': """
                from shop.models import Order


                def price(order: Order) -> int:
                    return order.total * 2
            """,
            'src/shop/discounts.py': """
                from shop.pricing import price


                def discount() -> int:
                    return 0
            """,
            'README.md': 'notes\n',
        }
    )
    TARGET = DiffTarget('main')

    @pytest.fixture
    def workspace(self, git_project: GitProject) -> Workspace:
        git_project.commit(self.BASE, 'base')
        git_project.switch_to_new_branch('feature')
        return git_project.commit(self.CHANGE, 'change')

    def test_changed_modules_form_the_surface(self, workspace: Workspace) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET)

        paths = tuple(tuple(item.path for item in cluster.modules) for cluster in plan.clusters)
        assert paths == (('src/shop/discounts.py', 'src/shop/pricing.py'),)

    def test_unchanged_importers_are_tests_or_dependents(self, workspace: Workspace) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET)

        attached = tuple((cluster.tests, cluster.dependents) for cluster in plan.clusters)
        assert attached == ((('tests/test_pricing.py',), ('src/shop/api.py',)),)


class TestPlanSurfaceForEmptyDiff:
    BASE = MappingProxyType({'src/shop/models.py': 'class Order:\n    total = 0\n'})
    CHANGE = MappingProxyType({'README.md': 'notes\n'})

    @pytest.fixture
    def workspace(self, git_project: GitProject) -> Workspace:
        git_project.commit(self.BASE, 'base')
        git_project.switch_to_new_branch('feature')
        return git_project.commit(self.CHANGE, 'docs only')

    def test_no_changed_python_files_gives_an_empty_plan(self, workspace: Workspace) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), DiffTarget('main'))

        assert (plan.clusters, plan.unparsable, plan.dispatches) == ((), (), 0)


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
    TARGET = CodebaseTarget(('src/shop/pricing.py',))
    EXPECTED = (('src/shop/pricing_test.py', 'test/helpers.py'), ('src/shop/api.py',))

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    def test_test_directory_and_test_suffix_importers_are_tests(self, workspace: Workspace) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET)

        assert (plan.clusters[0].tests, plan.clusters[0].dependents) == self.EXPECTED


class TestSeveralCodebasePaths:
    FILES = MappingProxyType(
        {
            'src/shop/__init__.py': '',
            'src/shop/api.py': 'from shop.core.pricing import price\n',
            'src/shop/core/pricing.py': 'def price() -> int: ...\n',
            'src/shop/core/stock.py': 'def reserve() -> None: ...\n',
            'src/shop/audit/log.py': 'def record() -> None: ...\n',
        }
    )
    TARGET = CodebaseTarget(('src/shop/core', 'src/shop/api.py', 'src/shop/core/stock.py'))
    EXPECTED = (('shop.api', 'shop.core.pricing'), ('shop.core.stock',))
    MODULE_COUNT = 3

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    def test_surface_is_the_union_of_every_path_in_one_numbering(
        self, workspace: Workspace
    ) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET)

        grouped = tuple(tuple(item.module for item in cluster.modules) for cluster in plan.clusters)
        assert grouped == self.EXPECTED

    def test_overlapping_paths_count_each_module_once(self, workspace: Workspace) -> None:
        plan = plan_surface(workspace, load_project_index(workspace), self.TARGET)

        assert plan.module_count == self.MODULE_COUNT


class TestMissingTarget:
    TARGET = CodebaseTarget(('src/ledger', 'src/ledgr'))

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({'src/ledger/__init__.py': ''})

    def test_mistyped_codebase_path_is_reported(self, workspace: Workspace) -> None:
        with pytest.raises(TargetPathMissingError):
            plan_surface(workspace, load_project_index(workspace), self.TARGET)

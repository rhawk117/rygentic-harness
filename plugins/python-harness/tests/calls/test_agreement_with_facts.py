"""Size metrics from `calls` agree with the `function_shape` facts for the same source."""

import pytest
from python_harness.calls.domain import ModuleMetrics
from python_harness.calls.services import map_call_sites_for
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.workspace import Workspace
from python_harness.facts.domain import FunctionShape, ModuleFacts
from python_harness.facts.services import collect_module_facts
from python_harness.facts.tests.support import build_detector_catalog
from python_harness.facts.util.function_shape import FUNCTION_SHAPE_DETECTORS
from python_harness.imports.domain import ProjectIndex
from python_harness.imports.services import load_project_index


class TestMetricsAgreeWithFacts:
    PATH = 'pkg/shapes.py'
    CATALOG = build_detector_catalog(FUNCTION_SHAPE_DETECTORS)

    @pytest.fixture
    def workspace(
        self, project_builder: ProjectBuilder, request: pytest.FixtureRequest
    ) -> Workspace:
        return project_builder.write({'pkg/__init__.py': '', self.PATH: request.param})

    @pytest.fixture
    def index(self, workspace: Workspace) -> ProjectIndex:
        return load_project_index(workspace)

    @pytest.fixture
    def module_facts(self, index: ProjectIndex) -> ModuleFacts:
        modules = index.sources.modules
        module = next(item for item in modules if item.source.path == self.PATH)
        return collect_module_facts(module, self.CATALOG)

    @pytest.fixture
    def metrics(self, workspace: Workspace, index: ProjectIndex) -> ModuleMetrics:
        return map_call_sites_for(workspace, index, (self.PATH,)).modules[0].metrics

    def function_shape_maxima(self, module_facts: ModuleFacts) -> tuple[int, int]:
        shapes = tuple(
            fact.detail for fact in module_facts.facts if isinstance(fact.detail, FunctionShape)
        )
        parameters = max(shape.parameters for shape in shapes)
        statements = max(shape.statements for shape in shapes)
        return parameters, statements

    @pytest.mark.parametrize(
        'workspace',
        [
            pytest.param(
                """
                class Store:
                    def save(self, *items, **extra):
                        def inner(): ...
                        return inner


                def build(cls):
                    def helper(): ...
                    return helper
                """,
                id='receiver-variadics-and-nested-definitions',
            ),
            pytest.param(
                """
                class Store:
                    @staticmethod
                    def merge(self, other, /, *, strict):
                        if strict:
                            class Merged:
                                size = 1
                            return Merged
                        return other
                """,
                id='staticmethod-and-class-inside-a-block',
            ),
            pytest.param(
                """
                def configure(cls, *, name, **options):
                    handler = lambda: name
                    return handler, options
                """,
                id='receiver-name-outside-a-class',
            ),
        ],
        indirect=True,
    )
    def test_size_maxima_equal_the_function_shape_maxima(
        self, module_facts: ModuleFacts, metrics: ModuleMetrics
    ) -> None:
        expected = self.function_shape_maxima(module_facts)

        assert (metrics.max_parameters, metrics.max_function_statements) == expected

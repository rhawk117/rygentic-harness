"""Reading pyproject.toml, layout markers and ruff config into a project survey."""

from types import MappingProxyType

import pytest
from python_harness.core.tests.fixtures import ProjectBuilder, stubbed_uv
from python_harness.core.toml import TomlTable
from python_harness.core.workspace import DiscoveryOptions, Workspace, open_workspace
from python_harness.survey.domain import Domain, LayoutFacts, Mode, ModeInference
from python_harness.survey.errors import ManifestUnreadableError
from python_harness.survey.services import (
    find_ruff_config,
    find_ty_config,
    load_pyproject,
    read_layout,
    survey_project,
)


class TestLoadPyproject:
    @pytest.fixture
    def with_pyproject(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({'pyproject.toml': '[project]\nname = "demo"\n'})

    @pytest.fixture
    def without_pyproject(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({'setup.py': ''})

    @pytest.fixture
    def unreadable_pyproject(
        self, project_builder: ProjectBuilder, request: pytest.FixtureRequest
    ) -> Workspace:
        workspace = project_builder.write({'pkg/__init__.py': ''})
        workspace.root.joinpath('pyproject.toml').write_bytes(request.param)
        return workspace

    def test_pyproject_is_parsed_into_tables(self, with_pyproject: Workspace) -> None:
        assert load_pyproject(with_pyproject) == {'project': {'name': 'demo'}}

    def test_missing_pyproject_gives_no_document(self, without_pyproject: Workspace) -> None:
        assert load_pyproject(without_pyproject) is None

    @pytest.mark.parametrize(
        'unreadable_pyproject',
        [
            pytest.param(b'[project\n', id='invalid-toml'),
            pytest.param(b'[project]\nname = "caf\xe9"\n', id='not-utf-8'),
        ],
        indirect=True,
    )
    def test_unreadable_pyproject_is_reported_with_its_path(
        self, unreadable_pyproject: Workspace
    ) -> None:
        with pytest.raises(ManifestUnreadableError) as caught:
            load_pyproject(unreadable_pyproject)

        assert caught.value.path == unreadable_pyproject.root.joinpath('pyproject.toml')


class TestReadLayout:
    @pytest.fixture
    def workspace(
        self, project_builder: ProjectBuilder, request: pytest.FixtureRequest
    ) -> Workspace:
        return project_builder.write(request.param)

    @pytest.mark.parametrize(
        ('workspace', 'expected'),
        [
            pytest.param(
                {
                    'src/demo/__init__.py': '',
                    'src/demo/__main__.py': '',
                    'src/demo/py.typed': '',
                    'tests/test_demo.py': '',
                },
                LayoutFacts(
                    has_py_typed=True,
                    has_dunder_main=True,
                    has_src_layout=True,
                    has_tests_directory=True,
                    has_uv_lock=False,
                ),
                id='src-layout-with-markers',
            ),
            pytest.param(
                {'demo/__init__.py': '', 'tests/fixtures/tool/__main__.py': ''},
                LayoutFacts(
                    has_py_typed=False,
                    has_dunder_main=False,
                    has_src_layout=False,
                    has_tests_directory=True,
                    has_uv_lock=False,
                ),
                id='flat-layout-ignores-tests-directory-markers',
            ),
            pytest.param(
                {'demo/__init__.py': '', 'uv.lock': 'version = 1\n'},
                LayoutFacts(
                    has_py_typed=False,
                    has_dunder_main=False,
                    has_src_layout=False,
                    has_tests_directory=False,
                    has_uv_lock=True,
                ),
                id='lockfile-is-recorded',
            ),
            pytest.param(
                {'demo/__init__.py': '', '.venv/lib/site/__main__.py': ''},
                LayoutFacts(
                    has_py_typed=False,
                    has_dunder_main=False,
                    has_src_layout=False,
                    has_tests_directory=False,
                    has_uv_lock=False,
                ),
                id='excluded-directories-are-skipped',
            ),
        ],
        indirect=['workspace'],
    )
    def test_layout_markers(self, workspace: Workspace, expected: LayoutFacts) -> None:
        assert read_layout(workspace) == expected


class TestReadLayoutWithConfiguredTestDirectories:
    FILES = MappingProxyType({'demo/__init__.py': '', 'specs/tool/__main__.py': ''})
    OPTIONS = DiscoveryOptions(test_directory_names=frozenset({'specs'}))
    EXPECTED = LayoutFacts(
        has_py_typed=False,
        has_dunder_main=False,
        has_src_layout=False,
        has_tests_directory=True,
        has_uv_lock=False,
    )

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        project_builder.write(self.FILES)
        return open_workspace(project_builder.root, self.OPTIONS, uv_runner=stubbed_uv)

    def test_workspace_test_directories_decide_the_layout(self, workspace: Workspace) -> None:
        assert read_layout(workspace) == self.EXPECTED


class TestFindRuffConfig:
    @pytest.fixture
    def workspace(
        self, project_builder: ProjectBuilder, request: pytest.FixtureRequest
    ) -> Workspace:
        return project_builder.write(request.param)

    @pytest.fixture
    def pyproject(self, workspace: Workspace) -> TomlTable | None:
        return load_pyproject(workspace)

    @pytest.mark.parametrize(
        ('workspace', 'expected'),
        [
            pytest.param(
                {
                    '.ruff.toml': 'line-length = 60\n',
                    'ruff.toml': 'line-length = 50\n',
                    'pyproject.toml': '[tool.ruff]\nline-length = 70\n',
                },
                '.ruff.toml',
                id='dot-ruff-toml-first',
            ),
            pytest.param(
                {
                    'ruff.toml': 'line-length = 50\n',
                    'pyproject.toml': '[tool.ruff]\nline-length = 70\n',
                },
                'ruff.toml',
                id='ruff-toml-before-pyproject',
            ),
            pytest.param(
                {'pyproject.toml': '[tool.ruff.lint]\nselect = ["E"]\n'},
                'pyproject.toml',
                id='pyproject-tool-ruff-subtable',
            ),
            pytest.param(
                {'pyproject.toml': '[tool.black]\nline-length = 70\n'},
                None,
                id='pyproject-without-tool-ruff',
            ),
            pytest.param({'demo.py': ''}, None, id='no-config-files'),
        ],
        indirect=['workspace'],
    )
    def test_finds_the_file_ruff_would_read(
        self, workspace: Workspace, pyproject: TomlTable | None, expected: str | None
    ) -> None:
        assert find_ruff_config(workspace, pyproject) == expected


class TestFindTyConfig:
    @pytest.fixture
    def workspace(
        self, project_builder: ProjectBuilder, request: pytest.FixtureRequest
    ) -> Workspace:
        return project_builder.write(request.param)

    @pytest.fixture
    def pyproject(self, workspace: Workspace) -> TomlTable | None:
        return load_pyproject(workspace)

    @pytest.mark.parametrize(
        ('workspace', 'expected'),
        [
            pytest.param(
                {
                    'ty.toml': 'environment = {}\n',
                    'pyproject.toml': '[tool.ty]\n',
                },
                'ty.toml',
                id='ty-toml-before-pyproject',
            ),
            pytest.param(
                {'pyproject.toml': '[tool.ty]\n'},
                'pyproject.toml',
                id='pyproject-tool-ty',
            ),
            pytest.param(
                {'pyproject.toml': '[tool.ruff]\nline-length = 70\n'},
                None,
                id='pyproject-without-tool-ty',
            ),
            pytest.param({'demo.py': ''}, None, id='no-config-files'),
        ],
        indirect=['workspace'],
    )
    def test_finds_the_file_ty_would_read(
        self, workspace: Workspace, pyproject: TomlTable | None, expected: str | None
    ) -> None:
        assert find_ty_config(workspace, pyproject) == expected


class TestSurveyProject:
    FILES = MappingProxyType(
        {
            'pyproject.toml': """
                [project]
                name = "shop"
                dependencies = ["fastapi"]

                [dependency-groups]
                dev = ["pytest"]

                [tool.ruff]
                line-length = 90
            """,
            'src/shop/__init__.py': 'from shop.orders import place_order\n',
            'src/shop/orders.py': """
                import asyncio

                from fastapi import APIRouter

                def place_order():
                    return asyncio, APIRouter
            """,
            'tests/test_orders.py': 'from shop.orders import place_order\n',
        }
    )
    SOURCE_ROOTS = ('src',)
    RUFF_CONFIG = 'pyproject.toml'
    MODE = ModeInference(Mode.APPLICATION, ('no build backend: uv application layout',))
    DOMAINS = (Domain.PYTEST, Domain.FASTAPI, Domain.ASYNCIO)
    EXTERNAL_PACKAGES = ('asyncio', 'fastapi')

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    def test_root_is_the_absolute_workspace_root(self, workspace: Workspace) -> None:
        survey = survey_project(workspace)

        assert survey.root == workspace.root.as_posix()

    def test_source_roots_are_relative_to_the_root(self, workspace: Workspace) -> None:
        survey = survey_project(workspace)

        assert survey.source_roots == self.SOURCE_ROOTS

    def test_ruff_config_names_the_file_ruff_reads(self, workspace: Workspace) -> None:
        survey = survey_project(workspace)

        assert survey.ruff_config == self.RUFF_CONFIG

    def test_survey_has_no_ty_config_when_the_project_declares_none(
        self, workspace: Workspace
    ) -> None:
        survey = survey_project(workspace)

        assert survey.ty_config is None

    def test_ty_config_names_the_file_ty_reads(self, project_builder: ProjectBuilder) -> None:
        workspace = project_builder.write({**self.FILES, 'ty.toml': 'environment = {}\n'})

        survey = survey_project(workspace)

        assert survey.ty_config == 'ty.toml'

    def test_mode_comes_with_its_reasons(self, workspace: Workspace) -> None:
        survey = survey_project(workspace)

        assert survey.mode == self.MODE

    def test_domains_follow_layout_and_imports(self, workspace: Workspace) -> None:
        survey = survey_project(workspace)

        assert survey.domains == self.DOMAINS

    def test_external_packages_are_what_the_project_imports(self, workspace: Workspace) -> None:
        survey = survey_project(workspace)

        assert survey.external_packages == self.EXTERNAL_PACKAGES

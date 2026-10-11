"""The `bin/python-harness-data` launcher: exact pins, a capped resolution, and its dispatch."""

import re
import sys
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import tomllib

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PLUGIN_ROOT.parents[1]
LAUNCHER = PLUGIN_ROOT.joinpath('bin', 'python-harness-data')
SHEBANG_LIMIT = 255
DATA_PACKAGES = ['duckdb', 'msgspec', 'numpy', 'polars', 'pyyaml', 'scipy']
COMMAND_NAMES = ['alert-budget', 'paired-compare', 'profile-data', 'size-check']
WITH_PIN = re.compile(r'--with (\S+)==(\S+)')
PYTHON_SPEC = re.compile(r'--python (\S+)')
EXCLUDE_NEWER = re.compile(r'--exclude-newer (\S+)')


def normalized(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def locked_packages() -> list[dict[str, Any]]:
    lock = tomllib.loads(REPOSITORY_ROOT.joinpath('uv.lock').read_text(encoding='utf-8'))
    return lock['package']


def locked_versions() -> dict[str, str]:
    return {normalized(package['name']): package['version'] for package in locked_packages()}


def newest_upload(names: list[str]) -> datetime:
    uploads = [
        datetime.fromisoformat(artifact['upload-time'])
        for package in locked_packages()
        if normalized(package['name']) in names
        for artifact in [
            *package.get('wheels', []),
            *([package['sdist']] if 'sdist' in package else []),
        ]
        if 'upload-time' in artifact
    ]
    return max(uploads)


def load_launcher() -> ModuleType:
    loader = SourceFileLoader('python_harness_data_launcher', str(LAUNCHER))
    module = ModuleType(loader.name)
    module.__file__ = str(LAUNCHER)
    loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def shebang() -> str:
    return LAUNCHER.read_bytes().split(b'\n', 1)[0].decode('utf-8')


class TestShebang:
    def test_uses_uv_tool_run(self, shebang: str) -> None:
        assert shebang.startswith('#!/usr/bin/env -S uv tool run ')

    def test_fits_the_kernel_shebang_limit(self, shebang: str) -> None:
        assert len(shebang.encode('utf-8')) <= SHEBANG_LIMIT

    def test_pins_equal_the_locked_data_packages(self, shebang: str) -> None:
        pins = {normalized(name): version for name, version in WITH_PIN.findall(shebang)}
        locked = locked_versions()

        assert pins == {name: locked[name] for name in DATA_PACKAGES}

    def test_python_spec_equals_requires_python(self, shebang: str) -> None:
        pyproject = tomllib.loads(
            PLUGIN_ROOT.joinpath('pyproject.toml').read_text(encoding='utf-8')
        )

        assert PYTHON_SPEC.findall(shebang) == [pyproject['project']['requires-python']]

    def test_cutoff_admits_every_locked_upload_of_the_data_packages(self, shebang: str) -> None:
        cutoffs = EXCLUDE_NEWER.findall(shebang)
        names = [*DATA_PACKAGES, 'polars-runtime-32']

        assert len(cutoffs) == 1
        assert datetime.fromisoformat(cutoffs[0]) >= newest_upload(names)


class TestDispatch:
    @pytest.fixture
    def launcher(self, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
        monkeypatch.setattr(sys, 'path', list(sys.path))
        return load_launcher()

    def test_the_table_holds_exactly_the_four_commands(self, launcher: ModuleType) -> None:
        assert sorted(launcher.COMMANDS) == COMMAND_NAMES

    @pytest.mark.parametrize('name', COMMAND_NAMES)
    def test_each_name_reaches_its_command_with_the_remaining_arguments(
        self, launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        calls: list[tuple[str, list[str]]] = []

        def fake_import(module_name: str) -> SimpleNamespace:
            def command(argv: list[str]) -> int:
                calls.append((module_name, argv))
                return 7

            return SimpleNamespace(main=command)

        monkeypatch.setattr(launcher.importlib, 'import_module', fake_import)

        assert launcher.main([name, '--flag', 'value']) == 7
        assert calls == [(launcher.COMMANDS[name], ['--flag', 'value'])]

    @pytest.mark.parametrize('argv', [[], ['unknown', '--help']], ids=['missing', 'unknown'])
    def test_a_missing_or_unknown_name_exits_nonzero_naming_the_four(
        self, launcher: ModuleType, capsys: pytest.CaptureFixture[str], argv: list[str]
    ) -> None:
        status = launcher.main(argv)
        printed = capsys.readouterr().err

        assert status != 0
        assert all(name in printed for name in COMMAND_NAMES)

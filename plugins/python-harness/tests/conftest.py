"""Loads the shared fixture plugins and the modules the tests import by path."""

import importlib.util
import sys
from pathlib import Path

import pytest

CONCEPTS = ('core', 'facts', 'documentation', 'tools')
PLUGIN = Path(__file__).resolve().parents[1]
MODULES_BY_PATH = {
    'plugin_layout': PLUGIN / 'tests' / 'plugin' / 'plugin_layout.py',
    'check_script': PLUGIN / 'skills' / 'automate-task' / 'scripts' / 'check_script.py',
    'parallelism': PLUGIN / 'skills' / 'automate-task' / 'scripts' / 'parallelism.py',
    'results': PLUGIN / 'skills' / 'data-engineering' / 'assets' / 'results.py',
}


def load_by_path(name: str, path: Path) -> None:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


for module_name, module_path in MODULES_BY_PATH.items():
    load_by_path(module_name, module_path)


def pytest_configure(config: pytest.Config) -> None:
    for concept in CONCEPTS:
        config.pluginmanager.import_plugin(f'python_harness.{concept}.tests.fixtures')

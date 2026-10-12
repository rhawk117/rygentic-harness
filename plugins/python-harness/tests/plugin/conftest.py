"""Make the helpers of test_tool_references importable from the other plugin layout tests."""

import importlib.util
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().with_name('test_tool_references.py')


def register_helpers(name: str) -> None:
    spec = importlib.util.spec_from_file_location(name, HELPERS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


register_helpers('test_tool_references')

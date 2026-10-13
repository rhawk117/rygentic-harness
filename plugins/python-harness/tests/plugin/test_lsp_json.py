"""The `.lsp.json` ty entry: a pinned launch that matches the repository's locked ty."""

import json
from pathlib import Path
from typing import Any

import tomllib

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PLUGIN_ROOT.parents[1]
LSP_FILE = PLUGIN_ROOT.joinpath('.lsp.json')
PIN_PREFIX = 'ty@'


def ty_entry() -> dict[str, Any]:
    return json.loads(LSP_FILE.read_text(encoding='utf-8'))['ty']


def locked_ty_version() -> str:
    lock = tomllib.loads(REPOSITORY_ROOT.joinpath('uv.lock').read_text(encoding='utf-8'))
    return next(package['version'] for package in lock['package'] if package['name'] == 'ty')


def test_ty_entry_runs_the_pinned_server() -> None:
    entry = ty_entry()

    assert entry['command'] == 'uv'
    assert entry['args'] == ['tool', 'run', f'{PIN_PREFIX}{locked_ty_version()}', 'server']


def test_ty_entry_serves_python_sources_without_a_project_root() -> None:
    entry = ty_entry()

    assert entry['extensionToLanguage'] == {'.py': 'python', '.pyi': 'python'}
    assert 'rootUri' not in entry

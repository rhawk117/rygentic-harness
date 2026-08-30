"""verify_gate.py — never previously imported by a test.

Follows the sys.path convention in writing-agent-rules/scripts/tests/test_audit_rules.py:
this is a standalone entry-point script (invoked by path, not an importable
package), so the test imports it directly off the filesystem.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verify_gate import GateConfig


def test_load_rejects_an_unsupported_platform(tmp_path):
    config_path = tmp_path / 'gate.json'
    config_path.write_text(json.dumps({'platform': 'vscode', 'check': ['true']}))

    with pytest.raises(ValueError, match='unsupported platform'):
        GateConfig.load(config_path)

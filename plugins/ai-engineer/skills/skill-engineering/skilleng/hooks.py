"""Emit host-native hook configs that all point at the same shim.

The two hosts differ in file location, event-name case and command key. They agree
on the concept, which is enough to make one instrumentation layer portable.

VERIFY BEFORE TRUSTING: the exact Copilot CLI payload shape and whether hooks fire
under `copilot -p` are not fully documented. `skilleng doctor --probe-hooks` answers
both empirically instead of assuming — and reports an adapter mismatch loudly rather
than letting every run score as "never triggered".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SHIM = [sys.executable, '-m', 'skilleng.hookshim']
EVENTS_CLAUDE = ['PreToolUse', 'PostToolUse', 'SessionStart', 'Stop']
EVENTS_COPILOT = ['preToolUse', 'postToolUse', 'sessionStart', 'agentStop']


def shim_command(probe: bool = False) -> str:
    return ' '.join(SHIM) + (' --probe' if probe else '')


def claude_code_settings(probe: bool = False) -> dict:
    cmd = shim_command(probe)
    return {
        'hooks': {
            ev: [
                {
                    'matcher': '*',
                    'hooks': [{'type': 'command', 'command': cmd, 'timeout': 5}],
                }
            ]
            for ev in EVENTS_CLAUDE
        }
    }


def copilot_hooks(probe: bool = False) -> dict:
    cmd = shim_command(probe)
    return {
        'version': 1,
        'hooks': {
            ev: [{'type': 'command', 'bash': cmd, 'timeoutSec': 5}]
            for ev in EVENTS_COPILOT
        },
    }


def write_claude_code(config_dir: Path, probe: bool = False) -> Path:
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    p = config_dir / 'settings.json'
    existing = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text())
        except json.JSONDecodeError:
            existing = {}
    existing.update(claude_code_settings(probe))
    p.write_text(json.dumps(existing, indent=2) + '\n')
    return p


def write_copilot(config_dir: Path, probe: bool = False) -> Path:
    config_dir = Path(config_dir)
    hooks_dir = config_dir / 'hooks'
    hooks_dir.mkdir(parents=True, exist_ok=True)
    p = hooks_dir / 'skilleng.json'
    p.write_text(json.dumps(copilot_hooks(probe), indent=2) + '\n')
    return p

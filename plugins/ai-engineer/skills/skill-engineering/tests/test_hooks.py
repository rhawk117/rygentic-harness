"""hooks.shim_command — hooks fire as subprocesses of the host CLI, so the written
command must resolve `skilleng` regardless of the invoker's cwd.
"""

from __future__ import annotations

from pathlib import Path

import skilleng
from skilleng import hooks


def _package_parent() -> Path:
    return Path(skilleng.__file__).resolve().parent.parent


def test_shim_command_embeds_an_absolute_pythonpath() -> None:
    cmd = hooks.shim_command()

    assert str(_package_parent()) in cmd


def test_claude_code_settings_command_is_cwd_independent() -> None:
    settings = hooks.claude_code_settings()
    cmd = settings['hooks']['PreToolUse'][0]['hooks'][0]['command']

    assert str(_package_parent()) in cmd


def test_copilot_hooks_command_is_cwd_independent() -> None:
    payload = hooks.copilot_hooks()
    cmd = payload['hooks']['preToolUse'][0]['bash']

    assert str(_package_parent()) in cmd

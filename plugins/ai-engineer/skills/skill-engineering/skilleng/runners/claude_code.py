"""Claude Code — a peer adapter, not an afterthought.

Claude Code does expose `--output-format stream-json`. We deliberately do not use it:
one detector across both hosts is worth more than a marginally richer one on a single
host, and a shared code path gets exercised twice as often.
"""

from __future__ import annotations

from pathlib import Path

from skilleng import hooks
from skilleng.runners.base import HostAdapter, RunRequest, register


@register
class ClaudeCode(HostAdapter):
    name = 'claude-code'
    cli = 'claude'
    config_env = 'CLAUDE_CONFIG_DIR'
    skill_install_subdir = 'skills'

    def prepare_sandbox(self, sandbox: Path, probe: bool = False) -> Path:
        sandbox = Path(sandbox)
        (sandbox / 'skills').mkdir(parents=True, exist_ok=True)
        hooks.write_claude_code(sandbox, probe=probe)
        return sandbox

    def command(self, req: RunRequest) -> list[str]:
        cmd = [self.cli, '-p', req.prompt, '--output-format', 'text']
        if req.model:
            cmd += ['--model', req.model]
        return cmd

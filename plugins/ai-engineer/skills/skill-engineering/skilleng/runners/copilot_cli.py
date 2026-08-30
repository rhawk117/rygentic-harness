"""GitHub Copilot CLI — the reference adapter.

Copilot offers no stream-json transcript to scrape, which is a feature: it forces
the event-log abstraction that was correct all along, instead of the stdout parsing
that makes skill-creator's detector wrong.

Config layout used here (see docs: CLI config-dir reference):
    $COPILOT_HOME/
      hooks/skilleng.json      instrumentation
      skills/<name>/SKILL.md   personal skill install
"""

from __future__ import annotations

from pathlib import Path

from .. import hooks
from .base import HostAdapter, RunRequest, register


@register
class CopilotCLI(HostAdapter):
    name = "copilot-cli"
    cli = "copilot"
    config_env = "COPILOT_HOME"
    skill_install_subdir = "skills"

    def prepare_sandbox(self, sandbox: Path, probe: bool = False) -> Path:
        sandbox = Path(sandbox)
        (sandbox / "skills").mkdir(parents=True, exist_ok=True)
        hooks.write_copilot(sandbox, probe=probe)
        return sandbox

    def command(self, req: RunRequest) -> list[str]:
        cmd = [self.cli, "-p", req.prompt, "--allow-all-tools"]
        if req.model:
            cmd += ["--model", req.model]
        return cmd

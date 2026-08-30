"""Host adapters. Everything host-specific lives behind this interface.

The portable core is exactly four things: headless CLI invocation, hook-based
instrumentation, spec-compliant skill install, filesystem outputs. Anything else
(Actions matrices, VS Code prompt files, applyTo instructions, cloud-agent
firewalls) is a surface extension and belongs in an adapter or in
references/surfaces.md — never in the core.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from skilleng.events import ENV_ARM, ENV_LOG, ENV_RUN
from skilleng.schema import Arm


@dataclass
class RunRequest:
    prompt: str
    arm: Arm
    run_id: str
    cwd: Path
    event_log: Path
    skill_dir: Path | None = None
    skill_name: str | None = None
    model: str | None = None
    timeout: int = 300
    extra_env: dict[str, str] = field(default_factory=dict)


@dataclass
class RunResult:
    ok: bool
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    error: str | None = None
    tokens: int | None = None  # None means "the host did not tell us", never 0


class HostAdapter:
    name = 'abstract'
    cli = ''
    config_env = ''  # env var that redirects the host's config dir
    skill_install_subdir = ''  # relative to the sandbox

    # -- capability --------------------------------------------------------

    def available(self) -> bool:
        return shutil.which(self.cli) is not None

    def version(self) -> str | None:
        if not self.available():
            return None
        try:
            # argv is built by this adapter, never a shell string.
            r = subprocess.run(  # noqa: S603
                [self.cli, '--version'],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            return (
                (r.stdout or r.stderr).strip().splitlines()[0]
                if r.returncode == 0
                else None
            )
        except OSError, subprocess.SubprocessError, IndexError:
            return None

    # -- sandbox -----------------------------------------------------------

    def prepare_sandbox(self, sandbox: Path, probe: bool = False) -> Path:
        """Create an isolated config dir with instrumentation wired up.

        Never the user's real config dir. skill-creator writes command files into the
        live project (and into $HOME when run from inside ~/.claude/skills/), then
        deletes them in a finally block that a hard kill skips.
        """
        raise NotImplementedError

    def install_skill(self, sandbox: Path, skill_dir: Path) -> Path:
        dest = Path(sandbox) / self.skill_install_subdir / Path(skill_dir).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(
            skill_dir, dest, ignore=shutil.ignore_patterns('__pycache__', '.git', 'evals')
        )
        return dest

    # -- invocation --------------------------------------------------------

    def command(self, req: RunRequest) -> list[str]:
        raise NotImplementedError

    def forced_prompt(self, prompt: str, skill_name: str) -> str:
        """Explicit invocation. Both hosts expose skills as /<skill-name>."""
        return f'/{skill_name} {prompt}'

    def env(self, req: RunRequest, sandbox: Path) -> dict[str, str]:
        e = dict(os.environ)
        e.pop('CLAUDECODE', None)  # allow nesting a headless run inside a session
        e.pop('CLAUDE_CODE_ENTRYPOINT', None)
        if self.config_env:
            e[self.config_env] = str(sandbox)
        e[ENV_LOG] = str(req.event_log)
        e[ENV_RUN] = req.run_id
        e[ENV_ARM] = req.arm.value
        e['PYTHONPATH'] = os.pathsep.join(
            filter(
                None, [str(Path(__file__).resolve().parents[2]), e.get('PYTHONPATH', '')]
            )
        )
        e.update(req.extra_env)
        return e

    def run(self, req: RunRequest, sandbox: Path) -> RunResult:
        """Execute one run. Every failure path is reported, never swallowed.

        skill-creator sends stderr to DEVNULL, so a bad model id, an auth failure and
        a genuine non-trigger are indistinguishable — all three become `False`.
        """
        if not self.available():
            return RunResult(
                ok=False,
                exit_code=None,
                stdout='',
                stderr='',
                duration_seconds=0.0,
                error=f'{self.cli!r} is not on PATH',
            )
        cmd = self.command(req)
        t0 = time.monotonic()
        try:
            # argv is built by this adapter's command(), never a shell string.
            proc = subprocess.run(  # noqa: S603
                cmd,
                cwd=str(req.cwd),
                env=self.env(req, sandbox),
                capture_output=True,
                text=True,
                timeout=req.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                ok=False,
                exit_code=None,
                stdout='',
                stderr='',
                duration_seconds=time.monotonic() - t0,
                timed_out=True,
                error=f'timed out after {req.timeout}s',
            )
        except OSError as e:
            return RunResult(
                ok=False,
                exit_code=None,
                stdout='',
                stderr='',
                duration_seconds=time.monotonic() - t0,
                error=f'failed to launch: {e}',
            )
        dt = time.monotonic() - t0
        if proc.returncode != 0:
            return RunResult(
                ok=False,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_seconds=dt,
                error=f'{self.cli} exited {proc.returncode}: {proc.stderr.strip()[:400]}',
            )
        return RunResult(
            ok=True,
            exit_code=0,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_seconds=dt,
        )


_REGISTRY: dict[str, type[HostAdapter]] = {}


def register(cls: type[HostAdapter]) -> type[HostAdapter]:
    _REGISTRY[cls.name] = cls
    return cls


def get_adapter(name: str) -> HostAdapter:
    if name not in _REGISTRY:
        raise KeyError(
            f'unknown host {name!r}; known hosts: {", ".join(sorted(_REGISTRY))}'
        )
    return _REGISTRY[name]()


def list_adapters() -> list[str]:
    return sorted(_REGISTRY)

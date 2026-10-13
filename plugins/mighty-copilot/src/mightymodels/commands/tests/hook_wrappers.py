import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

STATE_DIRECTORY = '.mightymodels'
HUNG = 'exec sleep 30'
CUT_OFF_SECONDS = '1'
HUNG_FOR_AT_MOST = 10.0


@dataclass(slots=True, kw_only=True, frozen=True)
class Outcome:
    code: int
    stdout: str
    stderr: str

    def last_line(self) -> str:
        return self.stderr.splitlines()[-1]


@dataclass(slots=True, kw_only=True, frozen=True)
class WrapperScript:
    path: Path
    launcher_variable: str
    limit_variable: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Wrapped:
    script: WrapperScript
    launcher: Path
    project: Path | None
    limit: str | None = None

    def environment(self) -> dict[str, str]:
        given = {
            self.script.launcher_variable: str(self.launcher),
            self.script.limit_variable: self.limit,
        }
        inherited = {name: value for name, value in os.environ.items() if name not in given}
        return inherited | {name: value for name, value in given.items() if value is not None}

    async def spawn(self, text: str) -> Outcome:
        process = await asyncio.create_subprocess_exec(
            self.script.path,
            cwd=self.project,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.environment(),
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(text.encode()), HUNG_FOR_AT_MOST
        )
        return Outcome(code=process.returncode or 0, stdout=stdout.decode(), stderr=stderr.decode())

    def run(self, text: str) -> Outcome:
        return asyncio.run(self.spawn(text))


def launcher_running(directory: Path, body: str | None) -> Path:
    launcher = directory.joinpath('launcher')
    if body is not None:
        launcher.write_text(f'#!/bin/sh\n{body}\n', encoding='utf-8')
        launcher.chmod(0o755)
    return launcher

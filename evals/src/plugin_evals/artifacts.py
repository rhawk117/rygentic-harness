import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RunArtifacts:
    workdir: Path
    response: str


def read_rel(workdir: Path, rel: str) -> str | None:
    path = workdir.joinpath(rel)
    if not path.is_file():
        return None
    return path.read_text(encoding='utf-8', errors='replace')


def run_cmd(cmd: list[str], cwd: Path, timeout: int = 180) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 -- argv list built by this harness, never a shell string
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )
    return proc.returncode, proc.stdout + proc.stderr

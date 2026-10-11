"""Read-only uv workspace queries."""

import shutil
import subprocess
from pathlib import Path


def run_uv_workspace(root: Path, *, timeout: float = 5.0) -> str:
    executable = shutil.which('uv')
    if executable is None:
        msg = 'uv is not on PATH'
        raise FileNotFoundError(msg)
    completed = subprocess.run(  # noqa: S603  fixed uv command, no shell.
        (executable, 'workspace', 'list', '--paths', '--offline', '--color', 'never'),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        msg = f'uv exited {completed.returncode}: {completed.stderr.strip()}'
        raise RuntimeError(msg)
    return completed.stdout

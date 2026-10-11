"""Direct contract tests for the uv workspace adapter."""

import subprocess
from pathlib import Path

import pytest
from python_harness.core import uv

EXECUTABLE = '/custom/bin/uv'
ARGUMENTS = ('workspace', 'list', '--paths', '--offline', '--color', 'never')


def test_run_uv_workspace_uses_the_resolved_executable_and_run_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = '/workspace\n'
    looked_up: list[str] = []
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def find_executable(name: str) -> str:
        looked_up.append(name)
        return EXECUTABLE

    def run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr='')

    monkeypatch.setattr(uv.shutil, 'which', find_executable)
    monkeypatch.setattr(uv.subprocess, 'run', run)

    assert uv.run_uv_workspace(tmp_path) == output
    assert looked_up == ['uv']
    assert calls == [
        (
            (EXECUTABLE, *ARGUMENTS),
            {
                'cwd': tmp_path,
                'capture_output': True,
                'text': True,
                'check': False,
                'timeout': 5.0,
            },
        )
    ]


def test_run_uv_workspace_passes_a_custom_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timeouts: list[object] = []

    def run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        timeouts.append(kwargs['timeout'])
        return subprocess.CompletedProcess(command, 0, stdout='', stderr='')

    monkeypatch.setattr(uv.shutil, 'which', lambda _: EXECUTABLE)
    monkeypatch.setattr(uv.subprocess, 'run', run)

    uv.run_uv_workspace(tmp_path, timeout=1.25)

    assert timeouts == [1.25]


def test_run_uv_workspace_translates_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(_: tuple[str, ...], **__: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            (EXECUTABLE, *ARGUMENTS), 2, stdout='', stderr='  invalid workspace  \n'
        )

    monkeypatch.setattr(uv.shutil, 'which', lambda _: EXECUTABLE)
    monkeypatch.setattr(uv.subprocess, 'run', run)

    with pytest.raises(RuntimeError, match=r'^uv exited 2: invalid workspace$'):
        uv.run_uv_workspace(tmp_path)


def test_run_uv_workspace_reports_missing_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        msg = 'subprocess.run must not be called'
        raise AssertionError(msg)

    monkeypatch.setattr(uv.shutil, 'which', lambda _: None)
    monkeypatch.setattr(uv.subprocess, 'run', run)

    with pytest.raises(FileNotFoundError, match='uv is not on PATH'):
        uv.run_uv_workspace(tmp_path)

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from mightymcp.hookkit import read_payload

DRIVER = """
from mightymcp.hookkit import run_hook


def handler(payload):
    if payload.get('boom'):
        raise RuntimeError('handler exploded')
    return {'seen': payload['hook_event_name']}


run_hook(handler)
"""

Load = Callable[[str], dict[str, Any]]
RunScript = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def driver(tmp_path: Path) -> Path:
    script = tmp_path.joinpath('driver.py')
    script.write_text(DRIVER, encoding='utf-8')
    return script


def test_a_valid_payload_prints_one_json_object(
    driver: Path, tmp_path: Path, payload: Load, run_hook_script: RunScript
) -> None:
    proc = run_hook_script(driver, json.dumps(payload('Stop')), tmp_path)

    assert proc.returncode == 0
    assert proc.stderr == ''
    assert json.loads(proc.stdout) == {'seen': 'Stop'}


def test_the_handler_output_is_a_single_line(
    driver: Path, tmp_path: Path, payload: Load, run_hook_script: RunScript
) -> None:
    proc = run_hook_script(driver, json.dumps(payload('Stop')), tmp_path)

    assert len(proc.stdout.strip().splitlines()) == 1


@pytest.mark.parametrize('value', ['1', 'true', 'because I said so'])
def test_a_set_off_switch_skips_the_hook_before_stdin_is_read(
    value: str, driver: Path, tmp_path: Path, run_hook_script: RunScript
) -> None:
    proc = run_hook_script(driver, 'not json at all', tmp_path, MIGHTYMCP_OFF=value)

    assert proc.returncode == 0
    assert proc.stdout == ''
    assert proc.stderr == ''


def test_an_empty_off_switch_leaves_the_hook_running(
    driver: Path, tmp_path: Path, payload: Load, run_hook_script: RunScript
) -> None:
    proc = run_hook_script(
        driver, json.dumps(payload('Stop')), tmp_path, MIGHTYMCP_OFF=''
    )

    assert json.loads(proc.stdout) == {'seen': 'Stop'}


@pytest.mark.parametrize('stdin', ['', 'not json at all', '[]', '"a string"'])
def test_a_malformed_payload_is_reported_on_stderr(
    stdin: str, driver: Path, tmp_path: Path, run_hook_script: RunScript
) -> None:
    proc = run_hook_script(driver, stdin, tmp_path)

    assert proc.returncode == 0
    assert proc.stdout == ''
    assert 'stood down' in proc.stderr


def test_a_handler_that_raises_is_reported_on_stderr(
    driver: Path, tmp_path: Path, payload: Load, run_hook_script: RunScript
) -> None:
    proc = run_hook_script(driver, json.dumps(payload('Stop') | {'boom': True}), tmp_path)

    assert proc.returncode == 0
    assert proc.stdout == ''
    assert 'handler exploded' in proc.stderr


def test_read_payload_returns_the_object(payload: Load) -> None:
    stop = payload('Stop')

    assert read_payload(json.dumps(stop)) == stop


@pytest.mark.parametrize('raw', ['[]', '3', 'null'])
def test_read_payload_refuses_a_payload_that_is_not_an_object(raw: str) -> None:
    with pytest.raises(TypeError, match='expected an object'):
        read_payload(raw)


def test_read_payload_refuses_invalid_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        read_payload('not json at all')

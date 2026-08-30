from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CLAUDE_CODE = 'claude-code'
COPILOT_CLI = 'copilot-cli'


@dataclass(frozen=True, slots=True)
class GateConfig:
    platform: str
    check: list[str]
    cwd: Path
    state_path: Path
    max_blocks: int

    @classmethod
    def load(cls, path: Path) -> GateConfig:
        raw = json.loads(path.read_text())
        platform = raw['platform']
        if platform not in (CLAUDE_CODE, COPILOT_CLI):
            raise ValueError(f'unsupported platform: {platform}')
        return cls(
            platform=platform,
            check=list(raw['check']),
            cwd=Path(raw.get('cwd', '.')).expanduser(),
            state_path=Path(raw.get('state_path', '.loop-gate.state')).expanduser(),
            max_blocks=int(raw.get('max_blocks', 1)),
        )


@dataclass(frozen=True, slots=True)
class CheckResult:
    passed: bool
    detail: str


def read_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip() if not sys.stdin.isatty() else ''
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _gate_timeout() -> int:
    try:
        return int(os.environ.get('LOOP_GATE_TIMEOUT', '300'))
    except ValueError:
        return 300


def run_check(config: GateConfig) -> CheckResult:
    try:
        completed = subprocess.run(  # noqa: S603 -- argv list built by this harness, never a shell string
            config.check,
            cwd=config.cwd,
            capture_output=True,
            text=True,
            timeout=_gate_timeout(),
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        return CheckResult(passed=False, detail=f'verification could not run: {error}')
    tail = (completed.stdout + completed.stderr).strip().splitlines()[-20:]
    return CheckResult(passed=completed.returncode == 0, detail='\n'.join(tail))


def blocks_recorded(config: GateConfig) -> int:
    if not config.state_path.exists():
        return 0

    try:
        return int(config.state_path.read_text().strip() or 0)
    except ValueError:
        return 0


def record_blocks(config: GateConfig, count: int) -> None:
    config.state_path.parent.mkdir(parents=True, exist_ok=True)
    config.state_path.write_text(str(count))


def clear_blocks(config: GateConfig) -> None:
    config.state_path.unlink(missing_ok=True)


def emit_claude_code(blocking: bool, message: str) -> None:
    if blocking:
        print(json.dumps({'decision': 'block', 'reason': message}))
    else:
        print(json.dumps({'systemMessage': message}) if message else '', end='')


def emit_copilot_cli(blocking: bool, message: str) -> None:
    payload: dict[str, Any] = {'decision': 'block' if blocking else 'continue'}
    if message:
        payload['additionalContext'] = message
    print(json.dumps(payload))


def emit(config: GateConfig, blocking: bool, message: str) -> None:
    if config.platform == CLAUDE_CODE:
        emit_claude_code(blocking, message)
    else:
        emit_copilot_cli(blocking, message)


def main() -> int:
    config_path = Path(os.environ.get('LOOP_GATE_CONFIG', '.loop-gate.json'))
    if not config_path.exists():
        print(f'loop gate config not found at {config_path}', file=sys.stderr)
        return 1

    try:
        config = GateConfig.load(config_path)
    except (KeyError, ValueError, json.JSONDecodeError) as error:
        print(f'loop gate config is invalid: {error}', file=sys.stderr)
        return 1

    payload = read_payload()
    result = run_check(config)

    if result.passed:
        clear_blocks(config)
        emit(config, blocking=False, message='')
        return 0

    prior = max(blocks_recorded(config), 1 if payload.get('stop_hook_active') else 0)
    if prior >= config.max_blocks:
        clear_blocks(config)
        emit(
            config,
            blocking=False,
            message=(
                f'Verification still failing after {prior} blocked attempt(s). '
                f'Releasing the turn and reporting unresolved failure:\n{result.detail}'
            ),
        )
        return 0

    record_blocks(config, prior + 1)
    emit(
        config,
        blocking=True,
        message=(
            "The loop's verification check is failing, so the work is not done. "
            f'Fix the cause rather than the symptom, then finish again:\n{result.detail}'
        ),
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

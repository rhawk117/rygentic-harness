import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal

import msgspec

from vibe_code_cli.findings import CannotCheckError, Finding, error
from vibe_code_cli.hook.events import EXIT_2_IGNORED_EVENTS, PLAIN_TEXT_CONTEXT_EVENTS
from vibe_code_cli.jsondoc import as_object

MALFORMED_PAYLOAD = '{not json'
EXCERPT_CHARACTERS = 300
BLOCKING_EXIT_CODE = 2
SUCCESS_EXIT_CODE = 0

MISSING = object()


class ScriptSuffix(StrEnum):
    PY = '.py'
    SH = '.sh'
    PS1 = '.ps1'
    JS = '.js'
    MJS = '.mjs'


@dataclass(slots=True, kw_only=True, frozen=True)
class Interpreter:
    candidates: tuple[str, ...]
    arguments: tuple[str, ...] = ()


def default_interpreters() -> dict[str, Interpreter]:
    return {
        ScriptSuffix.PY: Interpreter(candidates=(sys.executable,)),
        ScriptSuffix.SH: Interpreter(candidates=('bash',)),
        ScriptSuffix.PS1: Interpreter(candidates=('pwsh', 'powershell'), arguments=('-File',)),
        ScriptSuffix.JS: Interpreter(candidates=('node',)),
        ScriptSuffix.MJS: Interpreter(candidates=('node',)),
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class Interpreters:
    by_suffix: dict[str, Interpreter] = field(default_factory=default_interpreters)


@dataclass(slots=True, kw_only=True, frozen=True)
class FieldExpectation:
    key: str
    expected: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Expectations:
    exit_code: int
    fields: tuple[FieldExpectation, ...]
    silent: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class HookTest:
    script: Path
    payload: Path
    expectations: Expectations
    timeout: float
    malformed: bool


def parse_field_expectation(spec: str) -> FieldExpectation:
    key, separator, expected = spec.partition('=')
    if not key:
        message = f'{spec!r} has an empty key'
        raise argparse.ArgumentTypeError(message)

    return FieldExpectation(key=key, expected=expected if separator else None)


def check_hook(hook_test: HookTest) -> list[Finding]:
    payload_text = read_payload(hook_test.payload)
    event = payload_event(payload_text, hook_test.payload)
    command = hook_command(hook_test.script)
    stdin_text = MALFORMED_PAYLOAD if hook_test.malformed else payload_text

    try:
        completed = subprocess.run(  # argument list with no shell; running the script is the point
            command,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=hook_test.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [
            error(
                f'timed out after {hook_test.timeout:g} s; '
                'a real hook this slow stalls every matching call'
            )
        ]
    except OSError as problem:
        message = f'{hook_test.script} did not start: {problem}'
        raise CannotCheckError(message) from problem

    return contract_findings(completed, hook_test.expectations, event)


def read_payload(payload: Path) -> str:
    try:
        return payload.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as problem:
        message = f"could not read payload {payload}: {problem}"
        raise CannotCheckError(message) from problem


def payload_event(payload_text: str, payload: Path) -> str | None:
    try:
        value = msgspec.json.decode(payload_text)
    except msgspec.DecodeError as problem:
        message = f"payload {payload} is not JSON: {problem}"
        raise CannotCheckError(message) from problem

    event = value.get('hook_event_name') if isinstance(value, dict) else None
    return event if isinstance(event, str) else None


def hook_command(script: Path) -> list[str]:
    if not script.is_file():
        message = f'script not found: {script}'
        raise CannotCheckError(message)

    suffix = script.suffix.lower()
    interpreter = Interpreters().by_suffix.get(suffix)
    if interpreter is None:
        return [str(script.resolve())]

    bin_candidates = map(shutil.which, interpreter.candidates)
    bin_candidates = filter(None, bin_candidates)
    executable = next(bin_candidates, None)

    if not (executable := next(bin_candidates, None)):
        message = f"{' or '.join(interpreter.candidates)} is not on PATH, so {script} cannot run"
        raise CannotCheckError(message)

    return [executable, *interpreter.arguments, str(script.resolve())]


def contract_findings(
    completed: subprocess.CompletedProcess[str],
    expectations: Expectations,
    event: str | None,
) -> list[Finding]:
    kind, output = classify_stdout(completed.stdout)
    return [
        *exit_findings(completed, expectations.exit_code, event),
        *stdout_findings(kind, event),
        *silent_findings(kind, expectations),
        *field_findings(output, expectations),
    ]


def exit_findings(
    completed: subprocess.CompletedProcess[str], expected: int, event: str | None
) -> list[Finding]:
    actual = completed.returncode
    findings = []
    if actual != expected:
        hint = ''
        if actual not in {SUCCESS_EXIT_CODE, BLOCKING_EXIT_CODE}:
            hint = ' (any exit other than 0 or 2 is a non-blocking error; only exit 2 blocks)'

        stderr = completed.stderr.strip()[:EXCERPT_CHARACTERS]
        findings.append(
            error(f"exit {actual}, expected {expected}{hint}; stderr: {stderr}")
        )

    if actual == BLOCKING_EXIT_CODE and event in EXIT_2_IGNORED_EVENTS:
        findings.append(
            error(f"exit 2 does not block on {event}; the exit code is ignored there")
        )

    return findings


type Stdout = Literal["empty", "json", "text", "broken"]


def classify_stdout(raw: str) -> tuple[Stdout, dict[str, object] | None]:
    text = raw.strip()
    if not text:
        return "empty", None

    if not (text.startswith('{') and text.endswith('}')):
        return 'text', None

    try:
        return "json", as_object(msgspec.json.decode(text))
    except msgspec.DecodeError:
        return "broken", None


def stdout_findings(kind: Stdout, event: str | None) -> list[Finding]:
    if kind == "broken":
        return [
            error(
                "stdout starts with { and ends with } but is not one JSON object; "
                "Claude Code reports a hook error"
            )
        ]

    if kind == 'text' and event not in PLAIN_TEXT_CONTEXT_EVENTS:
        return [
            error(
                f'plain-text stdout is not read as context on {event or "this event"}; '
                'print one JSON object or nothing'
            )
        ]

    return []


def silent_findings(kind: Stdout, expectations: Expectations) -> list[Finding]:
    if expectations.silent and kind != "empty":
        return [error("expected empty stdout, got output")]

    return []


def field_findings(output: dict[str, object] | None, expectations: Expectations) -> list[Finding]:
    findings = []
    output = output or {}
    for expectation in expectations.fields:
        if problem := field_problem(output, expectation):
            findings.append(error(problem))

    return findings


def field_problem(output: dict[str, object], expectation: FieldExpectation) -> str | None:
    value: object = output
    for part in expectation.key.split('.'):
        value = value.get(part, MISSING) if isinstance(value, dict) else MISSING

    if value is MISSING:
        return f'missing field {expectation.key}'

    if expectation.expected is not None and not matches(value, expectation.expected):
        actual = msgspec.json.encode(value).decode()
        return f'{expectation.key}={actual}, expected {expectation.expected}'

    return None


def matches(value: object, expected: str) -> bool:
    try:
        wanted: object = msgspec.json.decode(expected)
    except msgspec.DecodeError:
        wanted = expected

    encoder = msgspec.json.Encoder(order="deterministic")
    current, wanted = encoder.encode(value), encoder.encode(wanted)
    return current == wanted

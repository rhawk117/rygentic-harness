#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_stdout(raw):
    lines = [ln for ln in raw.strip().splitlines() if ln.strip()]
    payload_lines = []
    for ln in lines:
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict) and obj.get('type') == 'progress':
                continue
            payload_lines.append((ln, obj))
        except json.JSONDecodeError:
            payload_lines.append((ln, None))

    return payload_lines


def check_field(obj, spec):
    key, _, expected = spec.partition('=')
    cur = obj
    for part in key.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return False, f'missing field {key}'
        cur = cur[part]
    if expected and str(cur) != expected:
        return False, f'{key}={cur!r}, expected {expected!r}'
    return True, f'{key}={cur!r}'


def main():
    ap = argparse.ArgumentParser(
        description=(
            'Pipe a sample payload into a Claude Code hook script and check the '
            'output contract: exit 0 with at most one JSON object on stdout, or '
            'exit 2 to block with the reason on stderr'
        )
    )
    ap.add_argument('script')
    ap.add_argument('payload')
    ap.add_argument('--expect-exit', type=int, default=0)
    ap.add_argument('--expect-field', action='append', default=[], metavar='KEY[=VALUE]')
    ap.add_argument('--expect-empty', action='store_true')
    ap.add_argument('--timeout', type=float, default=15.0)
    args = ap.parse_args()

    script = Path(args.script)
    payload = Path(args.payload).read_text()
    json.loads(payload)

    interpreters = {
        '.py': [sys.executable],
        '.ps1': ['pwsh', '-File'],
        '.mjs': ['node'],
        '.js': ['node'],
    }
    cmd = interpreters.get(script.suffix, ['bash']) + [str(script)]

    try:
        proc = subprocess.run(
            cmd, input=payload, capture_output=True, text=True, timeout=args.timeout
        )
    except subprocess.TimeoutExpired:
        print(
            f'FAIL {script.name}: timed out after {args.timeout}s '
            '(a real hook this slow stalls every matching call)'
        )
        return 1

    failures = []
    if proc.returncode != args.expect_exit:
        failures.append(
            f'exit={proc.returncode}, expected {args.expect_exit}; stderr: {proc.stderr.strip()[:300]}'
        )

    outputs = parse_stdout(proc.stdout)
    bad_lines = [ln for ln, obj in outputs if obj is None]
    if bad_lines:
        failures.append(f'non-JSON stdout line(s): {bad_lines[:2]}')
    if args.expect_empty and outputs:
        failures.append(f'expected empty stdout, got: {outputs[0][0][:200]}')
    if len(outputs) > 1:
        failures.append(
            f'{len(outputs)} JSON output lines; the contract is a single line'
        )

    result_obj = outputs[0][1] if outputs and outputs[0][1] is not None else {}
    for spec in args.expect_field:
        ok, detail = check_field(result_obj, spec)
        if not ok:
            failures.append(detail)

    if failures:
        print(f'FAIL {script.name} < {Path(args.payload).name}')
        for f in failures:
            print(f'  - {f}')
        return 1
    shown = outputs[0][0][:200] if outputs else '(empty stdout)'
    print(
        f'PASS {script.name} < {Path(args.payload).name} -> exit {proc.returncode}, {shown}'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Append-only journal for mightymodels crashouts: add, stats, last."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

import yaml

SEVERITIES = ("mild-tilt", "heated", "crashout", "full-meltdown")
VERDICTS = ("deserved", "split", "unreasonable")
# Key order is the schema contract; entries read top-down in this order everywhere.
ENTRY_KEYS = (
    "at",
    "ticket",
    "branch",
    "severity",
    "verdict",
    "rant",
    "failures",
    "root_cause",
    "corrective_action",
    "barked_back",
)
NULLABLE_KEYS = ("ticket", "branch")
DEFAULT_JOURNAL = Path(".mightymodels/crashouts.yml")


class _Rant(str):
    """Marker type so the rant always dumps as a literal block scalar."""


class _Dumper(yaml.SafeDumper):
    pass


def _repr_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


def _repr_rant(dumper: yaml.SafeDumper, data: _Rant) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")


_Dumper.add_representer(str, _repr_str)
_Dumper.add_representer(_Rant, _repr_rant)


def _fail(message: str) -> NoReturn:
    print(f"crashout-journal: {message}", file=sys.stderr)
    raise SystemExit(1)


def _dump(entries: list[dict[str, Any]]) -> str:
    return yaml.dump(entries, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


def _load(journal: Path) -> list[dict[str, Any]]:
    if not journal.exists():
        return []
    data = yaml.safe_load(journal.read_text(encoding="utf-8"))
    if data is None:
        return []
    if not isinstance(data, list):
        _fail(f"{journal} is not a YAML list; a crashout journal is a flat list of entries")
    return data


def _nonempty_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        _fail(f"'{key}' must be a non-empty string")
    return value


def _validated(raw: dict[str, Any]) -> dict[str, Any]:
    provided = set(raw)
    required = set(ENTRY_KEYS) - set(NULLABLE_KEYS) - {"at"}
    if missing := sorted(required - provided):
        _fail(f"missing keys: {missing}")
    if unknown := sorted(provided - (set(ENTRY_KEYS) - {"at"})):
        _fail(f"unknown keys: {unknown} (schema drift: fix the caller, not the journal)")
    if raw["severity"] not in SEVERITIES:
        _fail(f"severity must be one of {SEVERITIES}")
    if raw["verdict"] not in VERDICTS:
        _fail(f"verdict must be one of {VERDICTS}")
    if not isinstance(raw["barked_back"], bool):
        _fail("'barked_back' must be a boolean")
    failures = raw["failures"]
    if (
        not isinstance(failures, list)
        or not failures
        or not all(isinstance(item, str) and item.strip() for item in failures)
    ):
        _fail("'failures' must be a non-empty list of non-empty strings")
    for key in NULLABLE_KEYS:
        if raw.get(key) is not None and not isinstance(raw[key], str):
            _fail(f"'{key}' must be a string or null")
    entry = {key: raw.get(key) for key in ENTRY_KEYS if key != "at"}
    entry["root_cause"] = _nonempty_str(raw, "root_cause").strip()
    entry["corrective_action"] = _nonempty_str(raw, "corrective_action").strip()
    # Literal block scalars cannot carry trailing whitespace or CR; normalize, never rewrite words.
    rant_lines = _nonempty_str(raw, "rant").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    entry["rant"] = _Rant("\n".join(line.rstrip() for line in rant_lines).strip("\n"))
    return entry


def _ensure_gitignored(journal: Path) -> None:
    # Journal contents are session exhaust, not source; keep them out of commits
    # even when the mightymodels plugin hook that normally guarantees this is absent.
    state_dir = journal.resolve().parent
    repo_root = state_dir.parent
    if not (repo_root / ".git").exists():
        return
    gitignore = repo_root / ".gitignore"
    pattern = f"{state_dir.name}/"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    lines = {line.strip() for line in existing.splitlines()}
    if lines & {pattern, state_dir.name, f"/{pattern}", f"/{state_dir.name}"}:
        return
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with gitignore.open("a", encoding="utf-8") as handle:
        handle.write(f"{prefix}{pattern}\n")
    print(f"added {pattern} to {gitignore}")


def _cmd_add(journal: Path) -> None:
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        _fail(f"stdin is not valid JSON: {exc}")
    if not isinstance(raw, dict):
        _fail("stdin must be a single JSON object")
    entry = _validated(raw)
    ordered: dict[str, Any] = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    ordered.update(entry)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(_dump([ordered]))
    _ensure_gitignored(journal)
    print(f"journaled crashout #{len(_load(journal))} -> {journal}")


def _cmd_stats(journal: Path) -> None:
    entries = _load(journal)
    if not entries:
        print("no crashouts recorded yet. serenity.")
        return
    severity = Counter(str(entry.get("severity", "?")) for entry in entries)
    verdict = Counter(str(entry.get("verdict", "?")) for entry in entries)
    barked = sum(1 for entry in entries if entry.get("barked_back"))
    print(f"entries: {len(entries)}")
    print("severity: " + " ".join(f"{name}={count}" for name, count in severity.most_common()))
    print("verdicts: " + " ".join(f"{name}={count}" for name, count in verdict.most_common()))
    print(f"barked_back: {barked}/{len(entries)}")
    print(f"first: {entries[0].get('at', '?')}  last: {entries[-1].get('at', '?')}")
    print("\nfailures:")
    for entry in entries:
        stamp = str(entry.get("at", "?"))[:10]
        tag = f"[{stamp} | {entry.get('verdict', '?')} | {entry.get('severity', '?')}]"
        for failure in entry.get("failures", []):
            print(f"  {tag} {failure}")
    print("\nstanding corrective actions:")
    # Exact dedup after whitespace collapse; semantic grouping is the agent's job.
    actions = dict.fromkeys(" ".join(str(entry.get("corrective_action", "")).split()) for entry in entries)
    for action in actions:
        if action:
            print(f"  - {action}")


def _cmd_last(journal: Path) -> None:
    entries = _load(journal)
    if not entries:
        print("no crashouts recorded yet.")
        return
    print(_dump([entries[-1]]), end="")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("add", "stats", "last"))
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    args = parser.parse_args()
    {"add": _cmd_add, "stats": _cmd_stats, "last": _cmd_last}[args.command](args.journal)


if __name__ == "__main__":
    main()
import itertools
import re
from collections.abc import Callable
from pathlib import Path

import msgspec
from msgspec import UNSET, UnsetType

from vibe_code_cli.findings import Finding, decode_problem, error, warning

KNOWN_KEYS = frozenset(
    {
        "name",
        "description",
        "allowed-tools",
        "disable-model-invocation",
        "user-invocable",
        "argument-hint",
        "when_to_use",
        "arguments",
        "paths",
        "shell",
        "context",
        "agent",
        "background",
        "hooks",
        "effort",
        "model",
        "disallowed-tools",
        "license",
        "compatibility",
        "metadata",
    }
)
NAME_MAX = 64
DESCRIPTION_MAX = 1024
LISTING_MAX = 1536
COMPATIBILITY_MAX = 500
NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TOOL_RULE = re.compile(r"\*|[A-Za-z][A-Za-z0-9_.*-]*(?:\([^()\r\n]+\))?")
TRUE_VALUES = frozenset({"true", "yes", "on", "1"})
FALSE_VALUES = frozenset({"false", "no", "off", "0"})


class SkillFrontmatter(msgspec.Struct, rename="kebab", frozen=True, kw_only=True):
    name: str | None = None
    description: str | None = None
    when_to_use: str | None = msgspec.field(name="when_to_use", default=None)
    license: str | UnsetType = UNSET
    compatibility: str | UnsetType = UNSET
    argument_hint: str | UnsetType = UNSET
    metadata: dict[str, str] | str | UnsetType = UNSET
    allowed_tools: str | list[str] | UnsetType = UNSET
    disable_model_invocation: bool | int | str | UnsetType = UNSET
    user_invocable: bool | int | str | UnsetType = UNSET


def check_fields(
    fields: dict[str, object],
    directory_name: str,
    *,
    builtin_errored: bool,
) -> list[Finding]:
    unknown = check_unknown_keys(fields)
    try:
        frontmatter = msgspec.convert(fields, SkillFrontmatter)
    except msgspec.ValidationError as problem:
        return [*unknown, *decode_problem(problem, builtin_errored=builtin_errored)]

    field_checks = itertools.chain(
        unknown,
        check_name(frontmatter, directory_name),
        check_description(frontmatter),
        check_optional_strings(frontmatter),
        check_invocation(frontmatter),
        check_allowed_tools(frontmatter),
    )

    return list(field_checks)


def check_unknown_keys(fields: dict[str, object]) -> list[Finding]:
    return [
        error(f"unknown frontmatter field {key!r}")
        for key in fields
        if key not in KNOWN_KEYS
    ]


def check_name(frontmatter: SkillFrontmatter, directory_name: str) -> list[Finding]:
    if frontmatter.name is None:
        return [
            warning("name is missing; Claude Code falls back to the directory name")
        ]
    return check_name_value(frontmatter.name, directory_name)


def check_name_value(name: str, directory_name: str) -> list[Finding]:
    if not name.strip():
        return [error("name must not be empty")]

    if len(name) > NAME_MAX or NAME_PATTERN.fullmatch(name) is None:
        return [
            error(
                f"name {name!r} must be 1 to {NAME_MAX} chars of lowercase letters, digits, "
                "and single hyphens, without leading or trailing hyphens"
            )
        ]

    if name != directory_name:
        return [
            error(f"name {name!r} must equal the directory name {directory_name!r}")
        ]

    return []


def check_description(frontmatter: SkillFrontmatter) -> list[Finding]:
    if not (description := frontmatter.description):
        return []

    if not description.strip():
        return [error("description must not be empty")]

    findings = []
    if len(description) > DESCRIPTION_MAX:
        findings.append(
            error(
                f"description is {len(description)} chars; the limit is {DESCRIPTION_MAX}"
            )
        )

    listing_length = len(description) + len(frontmatter.when_to_use or "")
    if listing_length > LISTING_MAX:
        findings.append(
            warning(
                f"description and when_to_use total {listing_length} chars; "
                f"Claude Code truncates the skill listing at {LISTING_MAX}"
            )
        )

    return findings


def check_optional_strings(frontmatter: SkillFrontmatter) -> list[Finding]:
    optional_strs = itertools.chain(
        optional_string("license", frontmatter.license, None),
        optional_string("compatibility", frontmatter.compatibility, COMPATIBILITY_MAX),
        optional_string("argument-hint", frontmatter.argument_hint, None),
    )
    return list(optional_strs)


def optional_string(
    key: str, value: str | UnsetType, max_length: int | None
) -> list[Finding]:
    if isinstance(value, UnsetType):
        return []

    if not value.strip():
        return [error(f"{key} must not be empty when provided")]

    value_length = len(value)
    if max_length is not None and value_length > max_length:
        return [error(f"{key} is {value_length} chars; the limit is {max_length}")]

    return []


def as_flag(value: object) -> bool | None:
    text = str(value).lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return None


def check_invocation(frontmatter: SkillFrontmatter) -> list[Finding]:
    written = {
        "disable-model-invocation": frontmatter.disable_model_invocation,
        "user-invocable": frontmatter.user_invocable,
    }
    flags = {
        key: as_flag(value)
        for key, value in written.items()
        if not isinstance(value, UnsetType)
    }
    findings = [
        error(
            f"{key} must be true or false (or yes, no, on, off, 1, 0), got {written[key]!r}"
        )
        for key, flag in flags.items()
        if flag is None
    ]
    human_only = flags.get("disable-model-invocation") is True
    if human_only and flags.get("user-invocable") is False:
        findings.append(
            error(
                "disable-model-invocation: true with user-invocable: false leaves the skill "
                "neither user-invocable nor model-invocable"
            )
        )
    if human_only and isinstance(frontmatter.argument_hint, UnsetType):
        findings.append(
            warning(
                "human-only skill has no argument-hint for the slash-command picker"
            )
        )

    return findings


def split_outside_parens(text: str, is_separator: Callable[[str], bool]) -> list[str]:
    pieces = [""]
    depth = 0
    for char in text:
        depth = max(depth + (char == "(") - (char == ")"), 0)
        if depth == 0 and is_separator(char):
            pieces.append("")
            continue

        pieces[-1] += char

    return pieces


def is_comma(char: str) -> bool:
    return char == ","


def split_tool_string(text: str) -> list[str]:
    entries: list[str] = []
    for segment in split_outside_parens(text, is_comma):
        words = [word for word in split_outside_parens(segment, str.isspace) if word]
        entries.extend(words or [""])

    return entries


def check_allowed_tools(frontmatter: SkillFrontmatter) -> list[Finding]:
    value = frontmatter.allowed_tools
    if isinstance(value, str):
        return check_tool_string(value)

    if isinstance(value, list):
        return check_tool_list([item.strip() for item in value])

    return []


def check_tool_string(value: str) -> list[Finding]:
    if not value.strip():
        return [error("allowed-tools must not be an empty string")]
    return check_tool_entries(split_tool_string(value))


def check_tool_list(value: list[str]) -> list[Finding]:
    if not value:
        return [error("allowed-tools must not be an empty list")]

    return check_tool_entries(value)


def check_tool_entries(entries: list[str]) -> list[Finding]:
    findings = [
        error(
            f"allowed-tools entry {entry!r} is not a Claude Code rule such as Bash(uv *)"
        )
        for entry in entries
        if entry and TOOL_RULE.fullmatch(entry) is None
    ]

    if "" in entries:
        findings.append(error("allowed-tools contains an empty entry"))

    if "*" in entries and len(entries) > 1:
        findings.append(
            warning(
                "allowed-tools contains '*' plus other entries; the others are redundant"
            )
        )

    return findings


def directory_name_of(skill_dir: Path) -> str:
    return skill_dir.resolve().name

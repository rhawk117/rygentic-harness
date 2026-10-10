import itertools
import re

import msgspec
from msgspec import UNSET, UnsetType

from vibe_code_cli.findings import Finding, decode_problem, error, warning
from vibe_code_cli.subagent.tools import is_known_tool, tool_entries, tool_name

KNOWN_KEYS = frozenset(
    {
        "name",
        "description",
        "tools",
        "disallowedTools",
        "model",
        "permissionMode",
        "maxTurns",
        "skills",
        "mcpServers",
        "hooks",
        "memory",
        "background",
        "omitClaudeMd",
        "effort",
        "isolation",
        "color",
        "initialPrompt",
        "experimental",
    }
)
PLUGIN_IGNORED_KEYS = ("permissionMode", "hooks", "mcpServers", "initialPrompt")
NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MODEL_PATTERN = re.compile(r"(?:sonnet|opus|haiku|fable)(?:\[1m\])?|inherit")
TRIGGER_PATTERN = re.compile(
    r"\b(use (this )?(skill |agent )?(when|after|proactively)|trigger when|"
    r"invoke when|call (this|it) when)\b",
    re.IGNORECASE,
)


class AgentFrontmatter(msgspec.Struct, rename="camel", frozen=True, kw_only=True):
    name: str | None = None
    description: str | None = None
    tools: str | list[str] | None = None
    disallowed_tools: str | list[str] | UnsetType = UNSET
    model: str | None = None
    permission_mode: str | None = None
    max_turns: int | UnsetType = UNSET


def check_fields(
    fields: dict[str, object],
    *,
    plugin: bool,
    unquoted_colon: bool,
    builtin_errored: bool,
) -> list[Finding]:
    unknown = check_unknown_keys(fields)
    try:
        frontmatter = msgspec.convert(fields, AgentFrontmatter)
    except msgspec.ValidationError as problem:
        return [*unknown, *decode_problem(problem, builtin_errored=builtin_errored)]

    field_checks = itertools.chain(
        check_name(frontmatter, plugin=plugin),
        check_description(frontmatter, unquoted_colon=unquoted_colon),
        check_tools(frontmatter),
        check_model(frontmatter),
        unknown,
        check_permission_mode(frontmatter, fields, plugin=plugin),
    )
    return list(field_checks)


def check_name(frontmatter: AgentFrontmatter, *, plugin: bool) -> list[Finding]:
    name = frontmatter.name
    if name is not None and name.strip():
        return check_name_value(name)
    if plugin:
        return [
            warning("name is missing or empty; a plugin agent loads under its filename")
        ]

    return [
        error("name is missing or empty; Claude Code skips the file as documentation")
    ]


def check_name_value(name: str) -> list[Finding]:
    if NAME_PATTERN.fullmatch(name):
        return []
    return [
        error(
            f"name {name!r} must be lowercase letters, digits and single hyphens, with no "
            "':' (reserved for plugin-scoped names) and no leading hyphen"
        )
    ]


def check_description(
    frontmatter: AgentFrontmatter,
    *,
    unquoted_colon: bool,
) -> list[Finding]:
    description = frontmatter.description
    if description is None or not description.strip():
        return []

    findings: list[Finding] = []
    if not TRIGGER_PATTERN.search(description):
        findings.append(
            warning(
                "description states a capability but no trigger condition; add "
                "'Use when ...' so Claude knows when to delegate to this agent"
            )
        )

    if unquoted_colon:
        findings.append(
            warning(
                "description contains ':' and is not quoted in the source; quote it "
                "so a YAML reader cannot misparse it"
            )
        )
    return findings


def check_tools(frontmatter: AgentFrontmatter) -> list[Finding]:
    entries = tool_entries(frontmatter.tools)
    if entries is None:
        return [
            warning(
                "no 'tools' list, so the agent inherits every tool the session has; "
                "list the tools it needs"
            )
        ]
    if not entries:
        return []

    tool_checks = itertools.chain(
        check_tool_names(entries),
        check_denylist(frontmatter),
        check_turn_budget(entries, frontmatter),
    )

    return list(tool_checks)


def check_tool_names(entries: list[str]) -> list[Finding]:
    return [
        error(
            f"{entry!r} is not a Claude Code tool name or an mcp__<server> or "
            "mcp__<server>__<tool> reference"
        )
        for entry in entries
        if not is_known_tool(entry)
    ]


def check_denylist(frontmatter: AgentFrontmatter) -> list[Finding]:
    if isinstance(frontmatter.disallowed_tools, UnsetType):
        return []

    return [
        warning(
            "'disallowedTools' is applied first and 'tools' is then resolved against the "
            "remaining pool, so a tool in both is removed; setting both rarely does what it "
            "looks like"
        )
    ]


def check_turn_budget(
    entries: list[str],
    frontmatter: AgentFrontmatter,
) -> list[Finding]:
    if "Bash" not in map(tool_name, entries) or not isinstance(
        frontmatter.max_turns, UnsetType
    ):
        return []

    return [
        warning(
            "agent can run commands but sets no maxTurns; a runaway delegation has no stop"
        )
    ]


def check_model(frontmatter: AgentFrontmatter) -> list[Finding]:
    model = frontmatter.model
    if model is None or MODEL_PATTERN.fullmatch(model) or "-" in model:
        return []

    return [
        error(
            f"model {model!r} is not a Claude Code alias (sonnet, opus, haiku, fable), "
            "'inherit', or a full model ID"
        )
    ]


def check_unknown_keys(fields: dict[str, object]) -> list[Finding]:
    return [
        warning(f"{key!r} is not a documented frontmatter key; Claude Code ignores it")
        for key in sorted(set(fields) - KNOWN_KEYS)
    ]


def check_permission_mode(
    frontmatter: AgentFrontmatter,
    fields: dict[str, object],
    *,
    plugin: bool,
) -> list[Finding]:
    if plugin:
        return [
            warning(
                f"{key!r} is ignored in a plugin agents/ directory; Claude Code drops it"
            )
            for key in PLUGIN_IGNORED_KEYS
            if key in fields
        ]

    if frontmatter.permission_mode != "bypassPermissions":
        return []

    return [
        warning(
            "a subagent that declares bypassPermissions keeps the main conversation's "
            "permission mode instead (v2.1.267 or later), so the setting does not skip prompts"
        )
    ]

"""Lint a subagent definition for the silent failures each platform allows."""
import argparse
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

COPILOT_MAX_BODY_CHARS = 30_000
CLAUDE_CODE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
COPILOT_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+\.agent\.md$")
TRIGGER_PATTERN = re.compile(
    r"\b(use (this )?(skill |agent )?(when|after|proactively)|trigger when|invoke when|call (this|it) when)\b",
    re.IGNORECASE,
)
CLAUDE_CODE_MODELS = frozenset({"opus", "sonnet", "haiku", "fable", "inherit"})
CLAUDE_CODE_KNOWN_KEYS = frozenset({
    "name", "description", "tools", "disallowedTools", "model", "permissionMode",
    "maxTurns", "skills", "memory", "effort", "isolation", "background",
    "mcpServers", "hooks", "color", "initialPrompt", "experimental",
})
COPILOT_KNOWN_KEYS = frozenset({
    "name", "description", "tools", "model", "target", "user-invocable",
    "disable-model-invocation", "mcp-servers", "metadata", "deferred-tool-loading",
})
CLAUDE_ONLY_KEYS = ("disallowedTools", "maxTurns", "effort", "permissionMode", "skills", "isolation")
COMMAND_TOOLS = frozenset({"Bash", "bash", "execute", "runCommands"})
LOAD_BEARING_SECTIONS = ("<inputs_expected>", "<output_contract>")


class Platform(StrEnum):
    CLAUDE_CODE = "claude-code"
    COPILOT_CLI = "copilot-cli"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Finding:
    severity: Severity
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class Definition:
    path: Path
    raw_front_matter: str
    front_matter: dict[str, object]
    body: str


class MalformedDefinitionError(Exception):
    pass


def split_front_matter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        raise MalformedDefinitionError(
            "opening '---' must be the first line, or the platform treats the file as documentation"
        )

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise MalformedDefinitionError("front matter is not closed by a second '---'")

    return parts[1], parts[2]


def load_definition(path: Path) -> Definition:
    raw_front_matter, body = split_front_matter(path.read_text(encoding="utf-8"))

    try:
        parsed = yaml.safe_load(raw_front_matter)
    except yaml.YAMLError as error:
        raise MalformedDefinitionError(f"front matter is not valid YAML: {error}") from error

    if not isinstance(parsed, dict):
        raise MalformedDefinitionError("front matter did not parse to a mapping")

    return Definition(path=path, raw_front_matter=raw_front_matter, front_matter=parsed, body=body)


def as_tool_list(value: object) -> list[str] | None:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]

    if isinstance(value, list):
        return [str(item) for item in value]

    return None


def check_description(definition: Definition) -> list[Finding]:
    description = definition.front_matter.get("description")
    if not isinstance(description, str) or not description.strip():
        return [Finding(Severity.ERROR, "DESCRIPTION_MISSING",
                        "'description' is required and is what the router matches on")]
    findings: list[Finding] = []
    if not TRIGGER_PATTERN.search(description):
        findings.append(Finding(
            Severity.WARNING, "MISSING_TRIGGER",
            "description states capability but no trigger condition; add 'Use when ...' so the router knows when to pick it",
        ))
    if ":" in description and not _is_quoted_description(definition):
        findings.append(Finding(
            Severity.WARNING, "UNQUOTED_COLON",
            "description contains ':' and is not quoted in the source; quote it so YAML cannot misparse it",
        ))
    return findings


def _is_quoted_description(definition: Definition) -> bool:
    for line in definition.raw_front_matter.splitlines():
        if line.lstrip().startswith("description:"):
            value = line.split(":", 1)[1].strip()
            return value.startswith(("'", '"', ">", "|"))
    return True


def check_body(definition: Definition) -> list[Finding]:
    findings: list[Finding] = []
    if not definition.body.strip():
        findings.append(Finding(Severity.ERROR, "EMPTY_BODY", "the body is the agent's system prompt and is empty"))
        return findings
    for section in LOAD_BEARING_SECTIONS:
        if section not in definition.body:
            findings.append(Finding(
                Severity.WARNING, "MISSING_SECTION",
                f"body has no {section} section; without it the agent guesses its inputs or its return shape",
            ))
    if re.search(r"\bMODEL REQUIREMENT\b|\bMUST only be run with\b", definition.body):
        findings.append(Finding(
            Severity.WARNING, "MODEL_DIRECTIVE_IN_PROSE",
            "body contains a model-requirement directive; agents have executed such prose by spawning a nested model",
        ))
    return findings


def check_claude_code(definition: Definition) -> list[Finding]:
    findings: list[Finding] = []
    name = definition.front_matter.get("name")
    if not isinstance(name, str) or not name.strip():
        findings.append(Finding(Severity.ERROR, "NAME_MISSING",
                                "'name' is required; without it the file is silently treated as documentation"))
    elif not CLAUDE_CODE_NAME_PATTERN.fullmatch(name):
        findings.append(Finding(Severity.ERROR, "NAME_INVALID",
                                f"'{name}' must be lowercase letters, digits and hyphens, and cannot contain ':' or lead with '-'"))
    findings.extend(_check_claude_code_tools(definition))
    findings.extend(_check_claude_code_model(definition))
    findings.extend(_unknown_keys(definition, CLAUDE_CODE_KNOWN_KEYS))
    if definition.front_matter.get("permissionMode") == "bypassPermissions":
        findings.append(Finding(Severity.WARNING, "BYPASS_PERMISSIONS",
                                "bypassPermissions allows writes to .git, .claude, .vscode and .config/git"))
    return findings


def _check_claude_code_tools(definition: Definition) -> list[Finding]:
    findings: list[Finding] = []
    tools = as_tool_list(definition.front_matter.get("tools"))
    if tools is None:
        findings.append(Finding(Severity.WARNING, "TOOLS_UNRESTRICTED",
                                "no 'tools' allowlist, so the agent inherits every tool the session has"))
        return findings
    if "disallowedTools" in definition.front_matter:
        findings.append(Finding(Severity.WARNING, "TOOLS_AND_DENYLIST",
                                "'disallowedTools' resolves before 'tools'; setting both rarely does what it looks like"))
    if any(tool in COMMAND_TOOLS for tool in tools) and "maxTurns" not in definition.front_matter:
        findings.append(Finding(Severity.WARNING, "NO_TURN_BUDGET",
                                "agent can run commands but has no maxTurns; a runaway delegation has no stop"))
    return findings


def _check_claude_code_model(definition: Definition) -> list[Finding]:
    model = definition.front_matter.get("model")
    if model is None or not isinstance(model, str):
        return []
    if model in CLAUDE_CODE_MODELS or "-" in model:
        return []
    return [Finding(Severity.ERROR, "MODEL_UNKNOWN",
                    f"'{model}' is not a Claude Code alias ({', '.join(sorted(CLAUDE_CODE_MODELS))}) or a full model ID")]


def check_copilot_cli(definition: Definition) -> list[Finding]:
    findings: list[Finding] = []
    if not COPILOT_FILENAME_PATTERN.fullmatch(definition.path.name):
        findings.append(Finding(Severity.ERROR, "FILENAME_INVALID",
                                f"'{definition.path.name}' must end in .agent.md and use only . - _ letters and digits"))
    if definition.path.name.startswith("."):
        findings.append(Finding(Severity.ERROR, "FILENAME_HIDDEN",
                                "agent names producing hidden files are rejected since CLI 1.0.72"))
    if len(definition.body) > COPILOT_MAX_BODY_CHARS:
        findings.append(Finding(Severity.ERROR, "BODY_TOO_LONG",
                                f"body is {len(definition.body)} characters; the cap is {COPILOT_MAX_BODY_CHARS}"))
    tools = definition.front_matter.get("tools")
    if isinstance(tools, list) and not tools:
        findings.append(Finding(Severity.ERROR, "TOOLS_EMPTY_LIST",
                                "'tools: []' disables every tool; omit the key or use ['*'] to allow all"))
    elif tools is None:
        findings.append(Finding(Severity.WARNING, "TOOLS_UNRESTRICTED",
                                "no 'tools' allowlist, so the agent inherits every tool the session has"))
    findings.extend(
        Finding(Severity.ERROR, "FIELD_NOT_PORTABLE",
                f"'{key}' has no Copilot CLI counterpart and is dropped in silence")
        for key in CLAUDE_ONLY_KEYS
        if key in definition.front_matter
    )
    findings.extend(_unknown_keys(definition, COPILOT_KNOWN_KEYS.union(CLAUDE_ONLY_KEYS)))
    return findings


def _unknown_keys(definition: Definition, known: frozenset[str]) -> list[Finding]:
    unknown = sorted(set(definition.front_matter) - known)
    return [Finding(Severity.WARNING, "KEY_UNRECOGNISED",
                    f"'{key}' is not a documented field for this platform and will be ignored")
            for key in unknown]


def lint(path: Path, platform: Platform) -> list[Finding]:
    try:
        definition = load_definition(path)
    except MalformedDefinitionError as error:
        return [Finding(Severity.ERROR, "UNPARSEABLE", str(error))]
    except OSError as error:
        return [Finding(Severity.ERROR, "UNREADABLE", str(error))]
    findings = check_description(definition) + check_body(definition)
    if platform is Platform.CLAUDE_CODE:
        return findings + check_claude_code(definition)
    return findings + check_copilot_cli(definition)


def render(path: Path, findings: list[Finding]) -> str:
    if not findings:
        return f"{path}: clean"
    lines = [f"{path}:"]
    lines.extend(f"  {finding.severity.value:<7} {finding.code:<24} {finding.message}" for finding in findings)
    return "\n".join(lines)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--platform", required=True, type=Platform, choices=list(Platform))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    exit_code = 0
    for path in arguments.paths:
        findings = lint(path, arguments.platform)
        print(render(path, findings))
        if any(finding.severity is Severity.ERROR for finding in findings):
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
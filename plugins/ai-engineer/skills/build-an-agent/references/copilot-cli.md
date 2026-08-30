# GitHub Copilot CLI custom agents - reference

Verified 2026-08-30 against GitHub Docs and Copilot CLI changelog through 1.0.79.
Scope is the CLI. VS Code, the cloud agent and Visual Studio accept different field sets;
if the target moves, re-check rather than assuming parity.

## Contents

- File locations and precedence
- Frontmatter
- Limits and hard rules
- Tool vocabulary
- Model values
- Invocation and delegation
- Known divergences from Claude Code

## File locations and precedence

| Scope | Path |
|---|---|
| Repository | `.github/agents/<name>.agent.md` |
| User | `~/.copilot/agents/<name>.agent.md` |

**Precedence is inverted relative to almost everything else.** If the same agent name exists
in both, the one in the home directory wins over the one in the repository. A stale personal
agent silently shadows the team's. Check for a collision before debugging anything else.

Since CLI 1.0.61 (2026-06-09), nested `.github/agents` and `.claude/agents` directories are
discovered when a session starts from a subdirectory of the repo root.

Unlike Claude Code, the CLI surfaces warnings and errors when a custom agent fails to load
(1.0.68). If you are authoring a file that must work on both platforms, debug it here first.

## Frontmatter

Required: `description`. `name` defaults to the filename.

| Field | Type | Default | Notes |
|---|---|---|---|
| `description` | string | - | Matched against for inference-based invocation. Single-quote it if it contains a colon. |
| `name` | string | filename | Lowercase and hyphens recommended. |
| `tools` | list or comma-string | all tools | `[]` disables **all** tools. `["*"]` or omitting the key enables all. Namespacing: `server/tool`, `server/*`. Unrecognised names are ignored silently. |
| `model` | string | inherits | Provider-qualified identifier. |
| `target` | string | both | `vscode` or `github-copilot`. |
| `user-invocable` | bool | `true` | `false` hides it from pickers but leaves it reachable as a subagent. |
| `disable-model-invocation` | bool | `false` | Blocks automatic context-based selection. |
| `mcp-servers` | object | - | Supports `${{ secrets.X }}` and `${VAR:-default}` interpolation. Ignored by IDE surfaces. |
| `metadata` | object | - | Free-form name/value annotation. Ignored by IDE surfaces. |
| `deferred-tool-loading` | bool | `false` | CLI 1.0.68. Only meaningful when tool search is active and the agent names its tools; wildcard agents already use tool search. |
| `infer` | bool | - | Retired. Use `user-invocable` and `disable-model-invocation`. |

No official source documents CLI behaviour for the VS Code fields `agents`, `handoffs`,
`argument-hint` or frontmatter `hooks`. Do not assume they work here.

## Limits and hard rules

| Constraint | Value |
|---|---|
| Body length | 30,000 characters |
| Filename | must be `<name>.agent.md`; charset limited to `. - _ a-z A-Z 0-9` |
| Hidden filenames | rejected since 1.0.72 |
| Subagent nesting depth | default 4, lowered from 6 in 1.0.79; `subagents.maxDepth` |
| Relative links in the body | resolve from the agent file's location since 1.0.73, not the session cwd |
| Tool inheritance | subagent sessions keep the parent's tool restrictions (1.0.67) |

## Tool vocabulary

Lowercase aliases, disjoint from Claude Code's names. Rough intent mapping, verify against the
CLI version in use since the alias table is not versioned in the docs:

| Intent | Claude Code | Copilot CLI |
|---|---|---|
| Read a file | `Read` | `read` |
| Search content | `Grep` | `search` |
| Find files | `Glob` | `search` |
| Modify files | `Edit`, `Write` | `edit` |
| Run commands | `Bash` | `execute` |
| Fetch web | `WebFetch` | `fetch` or MCP-provided |

Since 1.0.72, requesting a shell tool by alias also grants the matching read, list and stop
shell tools. Unrecognised names are dropped with no message.

Built-in agents available as delegation targets by name: `explore`, `task`,
`general-purpose`, `code-review`, `research`, `rubber-duck`.

## Model values

Provider-qualified identifiers, not the Claude Code aliases. None of `opus`, `sonnet`,
`haiku` or `fable` is valid here. Resolve the tier intent against the models the user's
account actually has - ask rather than guessing an identifier, since availability varies by
plan and the catalogue changes.

## Invocation and delegation

Four paths: the `/agent` picker, naming the agent in natural language,
description-driven inference, and `copilot --agent NAME --prompt "..."`.

Since 1.0.71 (2026-07-16), subagents are multi-turn and the caller may send follow-up
messages to a running subagent.

## Known divergences from Claude Code

| Behaviour | Claude Code | Copilot CLI |
|---|---|---|
| Required fields | `name` and `description` | `description` only |
| Extension | `.md` | `.agent.md` |
| User vs project precedence | project wins | **home wins** |
| Return contract | one final message | multi-turn since 1.0.71 |
| Load failure visibility | debug log only | surfaced as a warning or error |
| Nesting depth default | 3 | 4 |
| Denylist | `disallowedTools` | none |
| Turn budget | `maxTurns` | none |
| Selection control | phrasing of `description` | `user-invocable`, `disable-model-invocation` |

An orchestrator that converses with its subagents is valid here and structurally invalid on
Claude Code. That is a design decision, not a translation detail.
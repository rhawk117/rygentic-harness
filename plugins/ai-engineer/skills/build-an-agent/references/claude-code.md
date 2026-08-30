# Claude Code subagents - reference

Verified 2026-08-30 against docs current to Claude Code v2.1.251.
These values have moved before. If the date above is more than a quarter old, re-check
https://code.claude.com/docs/en/sub-agents before relying on the caps section.

## Contents

- File locations and precedence
- Frontmatter
- Rules that make a file load or not
- What the subagent actually receives
- Tool vocabulary
- Model values
- Runtime caps
- Invocation

## File locations and precedence

| Priority | Location |
|---|---|
| 1 | managed settings `.claude/agents/` |
| 2 | `--agents` CLI flag (session only) |
| 3 | `.claude/agents/` (project) |
| 4 | `~/.claude/agents/` (user) |
| 5 | plugin `agents/` |

Scanned recursively; subfolders are organisational only. Identity comes from the `name` field,
not the path. Within `.claude/agents/`, the definition closest to the working directory wins.
Plugin agents register as `<plugin>:<subdir>:<name>`.

A brand-new `agents/` directory needs a session restart. Edits to files inside an existing one
are picked up within seconds. This is the single most common cause of "my agent never appears".

## Frontmatter

Required: `name`, `description`. Everything else optional.

| Field | Type | Default | Notes |
|---|---|---|---|
| `name` | string | - | Lowercase and hyphens. No `:`. Cannot start with `-`. Filename need not match. Hooks see it as `agent_type`. |
| `description` | string | - | Router input. Combined non-builtin descriptions over 15,000 tokens trigger a startup warning. |
| `tools` | string or list | inherits all | Allowlist. Accepts `mcp__<server>`, `mcp__<server>__*`, and `Agent(a, b)` to restrict which subagents this one may spawn. |
| `disallowedTools` | string or list | - | Denylist. Resolved *before* `tools`. |
| `model` | string | `inherit` | See model values below. |
| `permissionMode` | string | inherits | `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, `plan`, `manual`. A parent running `bypassPermissions`, `acceptEdits` or `auto` wins and cannot be overridden downward. |
| `maxTurns` | int | - | v2.1.246+. Output marked partial at the limit. The authoring-side stop for runaway agents. |
| `skills` | list | - | Injects full skill *content* at startup. Not an access control - the agent can still glob and invoke unlisted skills. |
| `memory` | string | - | `user`, `project`, `local`. Cross-session persistence. |
| `effort` | string | inherits | `low`, `medium`, `high`, `xhigh`, `max`. Known to be dropped under `-p --agent` (issue #82259, open). |
| `isolation` | string | - | `worktree`. Also dropped under `--agent` in some versions (issue #50357). |
| `background` | bool | `false` | Force background even when the parent asks for foreground. |
| `mcpServers` | list or object | - | Inline definitions from project scope require folder trust. |
| `hooks` | object | - | `PreToolUse`, `PostToolUse`, `Stop`, scoped to this agent. Project-scope hooks require folder trust. |
| `color` | string | - | `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, `cyan`. |
| `initialPrompt` | string | - | Only when the definition runs as a main session via `--agent`. |
| `experimental` | object | - | v2.1.248+. `{cacheTtl: "5m"}` or `{cacheTtl: "1h"}`. |

Plugin agents silently ignore `hooks`, `mcpServers` and `permissionMode`.

## Rules that make a file load or not

Skipped with no user-visible error:

- `name` missing (the file is treated as documentation)
- `description` missing (debug log only)
- opening `---` not on line 1
- `name` starting with `-` or containing `:`
- YAML that does not parse

Diagnostics: `claude plugin validate .claude/agents` (v2.1.233+), `/doctor` for duplicate
names, `--safe-mode` to disable all custom agents and bisect. Duplicate `name` in one
directory means one loads by filesystem read order, with no error.

## What the subagent actually receives

> The only content you pass from parent to subagent is the Agent tool's prompt string.

Received: its own system prompt and environment, the dispatch prompt, all `CLAUDE.md` files in
the hierarchy, a git status snapshot, preloaded `skills`, and the sibling roster (v2.1.206+).

Not received: main conversation history, main conversation tool results, the parent's system
prompt, the parent's output style, skills already invoked in the parent.

Forks are the exception and inherit the whole conversation.

Return: only the final message goes back, and the parent may summarise it further.

## Tool vocabulary

PascalCase capability names. Common groupings:

| Intent | Grant |
|---|---|
| Read-only analysis | `Read, Grep, Glob` |
| Research | `Read, Grep, Glob, WebFetch, WebSearch` |
| Test execution | `Bash, Read, Grep` |
| Code modification | `Read, Edit, Write, Grep, Glob` |

A tool you leave out is not in the session at all. The agent works without it, with no
permission prompt and no error.

## Model values

`opus`, `sonnet`, `haiku`, `fable`, a full model ID, or `inherit` (the default).

Tier intent maps to: cheap retrieval `haiku`, standard work `sonnet`, frontier review `opus`.
`fable` is for long-horizon autonomous work; avoid it for security analysis, since its
cyber and bio classifiers fall back to Opus anyway.

Since v2.1.232 the definition's `model:` takes precedence over `CLAUDE_CODE_SUBAGENT_MODEL`.
Advice written before August 2026 about that variable is stale.

## Runtime caps

| Cap | Default | Override |
|---|---|---|
| Spawn depth | 3 | `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` |
| Concurrent subagents | 20 | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` |
| Per-session spawns | none | added and then removed during Q3 2026 |

Claude Opus 5 delegates more readily than earlier models, so these bind hardest exactly where
you are running Opus 5 reviewers. Agent teams run roughly 7x the tokens of a standard session
in plan mode.

## Invocation

- Automatic delegation from the `description`. Include "use proactively" to encourage it.
- `@"name (agent)"` or `@agent-<plugin>:<name>` guarantees the agent runs.
- `claude --agent <name>` runs a whole session as that agent - note that `effort` and
  `isolation` are known to be dropped on this path.

If Claude will not delegate: `Agent` may be missing from `allowedTools`, the prompt may not
name the agent, or the `description` may be too vague to match.
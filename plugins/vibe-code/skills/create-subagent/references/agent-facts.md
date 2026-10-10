# Claude Code subagents: facts

Checked on 2026-10-03 against https://code.claude.com/docs/en/sub-agents and https://code.claude.com/docs/en/plugins/components. These values have moved before; if the date is more than a quarter old, re-check those pages before relying on the caps and version gates. A claim in this skill that this file does not carry is unverified.

## Contents

- Scopes and precedence
- Frontmatter
- Files Claude Code skips
- What a subagent receives
- Model resolution
- Runtime caps
- Invocation
- Tools a subagent keeps

## Scopes and precedence

| Priority | Location                           | Scope                       |
| -------- | ---------------------------------- | --------------------------- |
| 1        | managed settings `.claude/agents/` | organization                |
| 2        | `--agents` CLI flag                | current session             |
| 3        | `.claude/agents/`                  | current project             |
| 4        | `~/.claude/agents/`                | all your projects           |
| 5        | plugin `agents/`                   | where the plugin is enabled |

When several agents share a name, the higher priority wins. Project agents are found by walking up from the working directory, so every `.claude/agents/` between there and the repository root is scanned, and the definition closest to the working directory wins. `.claude/agents/` and `~/.claude/agents/` are scanned recursively; a subfolder is organisational only, because identity comes from the `name` key. Two files under one `.claude/agents/` that declare the same `name`: one loads, chosen by filesystem read order, with no error; `/doctor` reports the duplicates.

A plugin `agents/` directory is also scanned recursively, but there a subfolder becomes part of the scoped name: `agents/review/security.md` in plugin `my-plugin` is `my-plugin:review:security`. The scoped name is `PLUGIN:NAME`, where NAME comes from the frontmatter, or from the file name when there is none.

## Frontmatter

Only `name` and `description` are required. Field names are camelCase and must match exactly; Claude Code ignores a field it does not recognise without reporting an error.

| Key               | Notes                                                                                                                                                     |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`            | Unique identifier; the filename need not match. No `:` and no leading `-`. Hooks see it as `agent_type`.                                                  |
| `description`     | When Claude should delegate to this agent.                                                                                                                |
| `tools`           | Comma-separated string or YAML list. Inherits every tool available to subagents if omitted. Accepts `mcp__SERVER`, `mcp__SERVER__*` and `Agent(a, b)`.    |
| `disallowedTools` | Denylist, applied before `tools`. A specifier such as `Bash(git push *)` still removes the whole tool.                                                    |
| `model`           | `sonnet`, `opus`, `haiku`, `fable`, a full model ID such as `claude-opus-5-5`, or `inherit`. When omitted, resolved as under Model resolution.            |
| `permissionMode`  | `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, `plan`, or `manual` (alias for `default`, v2.1.200 or later). Ignored in plugin agents. |
| `maxTurns`        | Turn budget; output is marked partial at the limit (v2.1.246 or later).                                                                                   |
| `skills`          | Skills whose full content is injected at startup.                                                                                                         |
| `mcpServers`      | A server name already configured, or an inline definition keyed by server name. Ignored in plugin agents.                                                 |
| `hooks`           | Lifecycle hooks scoped to this agent. Ignored in plugin agents.                                                                                           |
| `memory`          | `user`, `project` or `local`: a persistent directory for the agent.                                                                                       |
| `background`      | Keeps the agent in the background even when Claude asks for the foreground.                                                                               |
| `omitClaudeMd`    | `true` launches the agent without the user, project and local `CLAUDE.md` files; managed policy files still load. v2.1.271 or later.                      |
| `effort`          | `low`, `medium`, `high`, `xhigh` or `max`; overrides the session level.                                                                                   |
| `isolation`       | `worktree` runs the agent in a temporary git worktree.                                                                                                    |
| `color`           | Display colour in the task list: `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink` or `cyan`.                                                  |
| `initialPrompt`   | First user turn when the agent runs as the main session through `--agent`. Ignored in plugin agents.                                                      |
| `experimental`    | Map of experimental options; read from subagent files only (v2.1.248 or later).                                                                           |

The plugins page lists the keys a plugin agent drops as `permissionMode`, `hooks`, `mcpServers` and `initialPrompt`; the sub-agents page note names only the first three.

## Files Claude Code skips

In a project, user or managed `agents` directory (or one added with `--add-dir`) a file is skipped, with nothing shown in the session, when:

- it has no `name`: it is treated as documentation kept beside the agents;
- the opening `---` is not the first line: it is read as having no frontmatter;
- the `name` starts with `-` or contains `:`: skipped, with an error in the debug log;
- it has a `name` but no `description`: skipped, with the reason in the debug log;
- the YAML does not parse: no fields are read, and the parse error goes to the debug log.

A plugin agent with no `name`, or with frontmatter that does not parse, still loads under its filename. Run Claude Code with `--debug` to see the log. `claude plugin validate` against an agents directory finds files whose frontmatter does not parse, but not a file that parses and has no `name`.

## What a subagent receives

Each non-fork subagent starts with a fresh, isolated context window. It does not see the conversation history, the skills already invoked or the files already read; Claude writes a delegation message and the subagent works from that.

Received: its own system prompt (the body) plus environment details, not the Claude Code system prompt; the delegation message; the `CLAUDE.md` hierarchy (every level the main conversation loads, including `AGENTS.md` files loaded as project instructions); a git status snapshot; the full content of any preloaded `skills`; and a sibling roster when its tools include `SendMessage` (v2.1.206 or later). `Explore` and `Plan` skip `CLAUDE.md` and git status.

Not received: the output style, the main conversation's auto memory, and the parent's context window size (the subagent's own model sets it). A rule that must reach the subagent, such as "ignore `vendor/`", goes in the delegation message. Only the final message returns to the caller.

## Model resolution

Claude Code picks the model in this order: the per-invocation `model` parameter, the definition's `model` (where `inherit` selects the main conversation's model), the `CLAUDE_CODE_SUBAGENT_MODEL` environment variable, then the main conversation's model. Before v2.1.251 the environment variable came first and overrode both the parameter and the frontmatter, so advice written before then is stale. An organization's `availableModels` list can substitute another model for a blocked value.

## Runtime caps

| Cap                  | Default                              | Override                               |
| -------------------- | ------------------------------------ | -------------------------------------- |
| Spawn depth          | 3 layers below the main conversation | `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` |
| Concurrent subagents | 20                                   | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` |

There is no limit on the total number of subagents spawned over a session. At the depth limit Claude Code withholds the `Agent` tool from the subagent. Do not write these numbers into an agent body; cite this file.

## Invocation

Claude delegates automatically from the `description` and the current context; a description containing "use proactively" encourages it. `@agent-NAME` or the typeahead entry `@"NAME (agent)"` makes that agent run, though Claude still writes its task prompt. `claude --agent NAME` runs the whole session as the agent, with its prompt replacing the default system prompt. Unverified: an older note of this skill said `effort` and `isolation` are dropped under `--agent`, citing two issue numbers; the docs snapshot has no such statement.

A subagent cannot ask the user questions (`AskUserQuestion` is removed from every subagent), so a body that depends on follow-up questions to the user will not work.

## Tools a subagent keeps

A subagent inherits the built-in tools and MCP tools available in the main conversation, narrowed by two filters; a fork skips both and receives the main conversation's exact tool pool. The first filter removes these tools from every subagent, even when listed in the `tools` field: `Agent`, when the subagent is at the depth limit; `AskUserQuestion`; `EndConversation`; `EnterPlanMode`; `ExitPlanMode`, unless the subagent's `permissionMode` is `plan`; `ScheduleWakeup`; `WaitForMcpServers`; and `Workflow`.

The second filter applies to subagents running in the background, which is the default. Apart from `Agent` and `ExitPlanMode`, which follow the first filter's conditions wherever the subagent runs, a background subagent keeps every MCP tool but only these built-in tools: `Read`, `Grep`, `Glob`, `LSP`, `Bash`, `PowerShell`, `Edit`, `Write`, `NotebookEdit`, `WebFetch`, `WebSearch`, `TodoWrite`, `Skill`, `ToolSearch`, `EnterWorktree`, `ExitWorktree`, `Monitor`, `TaskStop`, `SendMessage` and `Artifact`, plus `SubagentHandback` for a subagent that reports through it. Claude Code removes every other built-in tool from a background subagent, whether inherited or listed in the `tools` field, and reports no error unless that leaves the `tools` list resolving to nothing.

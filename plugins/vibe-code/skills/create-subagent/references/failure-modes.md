# Failure modes by symptom

Each row says where its cause is documented. `docs` means the sentence is in the sub-agents or plugin components pages as of 2026-10-03 (see `references/agent-facts.md`). `unverified` means the previous version of this skill asserted it and the docs snapshot neither confirms nor contradicts it; treat it as a lead, not a rule.

## The agent never appears

| Cause                                                                                                 | Evidence |
| ----------------------------------------------------------------------------------------------------- | -------- |
| `name` missing, or `description` missing: the file is skipped with nothing shown in the session       | docs     |
| Opening `---` not on line 1, or YAML that does not parse                                              | docs     |
| `name` contains `:` or starts with `-`                                                                | docs     |
| The first agent file in a new `agents` directory was written mid-session; the watcher needs a restart | docs     |
| Two files in one `.claude/agents/` tree declare the same `name`; one loads, chosen by read order      | docs     |
| A closer `.claude/agents/` or a managed agent of the same name wins                                   | docs     |

Load problems go to the debug log (`--debug`), not the session. `--safe-mode` starts with all custom agents disabled, which separates a broken agent from a broken session.

## It loads but is never chosen

| Cause                                                                                               | Evidence   |
| --------------------------------------------------------------------------------------------------- | ---------- |
| `description` states a capability, not a trigger condition; Claude delegates from the `description` | docs       |
| Combined custom descriptions pass 15,000 tokens: a startup warning, and every agent still loads     | docs       |
| `Agent` missing from the caller's tools, so delegation is impossible                                | unverified |
| Overlapping descriptions across a large agent library cause misrouting                              | unverified |

## It runs but the answer is confidently wrong

| Cause                                                                                                                 | Evidence   |
| --------------------------------------------------------------------------------------------------------------------- | ---------- |
| The agent was assumed to see the conversation; it gets a fresh context and a delegation message                       | docs       |
| The dispatch did not name the request, the known context, the scope and the result format                             | unverified |
| A reviewer given only a diff produced confident verdicts and did not flag the missing brief (reported as 0 of 5 runs) | unverified |
| Prose in a loaded file was executed as a directive, such as a line demanding a particular model                       | unverified |

## It does more than it was asked to

| Cause                                                                                 | Evidence        |
| ------------------------------------------------------------------------------------- | --------------- |
| No explicit out-of-scope list in `<constraints>`, so the agent chose its own boundary | unverified      |
| One agent holding several jobs; a procedure belongs in a skill                        | unverified      |
| The body contradicts `CLAUDE.md`, which the agent also loads                          | docs (it loads) |

## It silently lacks a capability

| Cause                                                                                              | Evidence |
| -------------------------------------------------------------------------------------------------- | -------- |
| A tool left out of `tools` is not available; the agent works without it                            | docs     |
| `tools` is an empty list: the agent launches with no tools                                         | docs     |
| Every entry of a non-empty `tools` list failed to resolve: Claude Code refuses to launch the agent | docs     |
| `disallowedTools` assumed to filter the `tools` list; it is applied first                          | docs     |
| A foreground-only built-in tool in `tools`, with the agent running in the background (the default) | docs     |
| `permissionMode` or `mcpServers` written in a plugin agent: dropped                                | docs     |

## It has more power than intended

| Cause                                                                                                        | Evidence   |
| ------------------------------------------------------------------------------------------------------------ | ---------- |
| Over-granted tools: an auditor holding `Edit` and `Bash` can rewrite what you wanted reviewed                | unverified |
| `skills` treated as access control; it only preloads, and the agent can still invoke unlisted skills         | docs       |
| `bypassPermissions` declared in the agent: it keeps the main conversation's mode instead (v2.1.267 or later) | docs       |

## It costs too much or takes too long

| Cause                                                                                 | Evidence                                             |
| ------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| A simple agent inheriting a strong model; pin `haiku` or `sonnet` for mechanical work | unverified                                           |
| No `maxTurns` on an agent that can run commands, so a runaway delegation has no stop  | docs (the key exists; the hang report is unverified) |
| Delegating a task that is a quick targeted change                                     | docs                                                 |

## It behaves differently than last time

| Cause                                                                                                                         | Evidence                            |
| ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| The same file runs as a subagent, as a whole session through `--agent`, and as a teammate; each applies different parts of it | docs (agent-teams page not re-read) |
| Advice written before v2.1.251 about `CLAUDE_CODE_SUBAGENT_MODEL` taking precedence over the frontmatter                      | docs                                |
| A field honoured on one invocation path and dropped on another, such as `effort` under `--agent`                              | unverified                          |

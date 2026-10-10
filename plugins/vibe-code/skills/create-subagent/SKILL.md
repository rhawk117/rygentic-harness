---
name: create-subagent
when_to_use: >-
  Use when the user says "make me a subagent that ...", "add a reviewer agent", "write an agent file", "why does my agent never load or get chosen", or asks how agent frontmatter, tools, models or plugin agents work, even without the word "subagent".
description: >-
  Interactive builder for Claude Code subagents (agent files with YAML frontmatter and an XML-sectioned Markdown body). Use it to create, scaffold, design or add a subagent, specialist agent, reviewer agent or persona, or to ask how to write an agent file, even when the user only describes the job ("I want an agent that triages CI failures"). It asks where the agent ships (plugin, project, personal), scans what already exists, checks that a subagent is the right mechanism, drives the tool, model and frontmatter choices by question, writes the file after a preview, proves it with vibe-code subagent validate, and ends with a dispatch snippet for the caller.
---

# Create a Claude Code subagent

You are producing one file: `NAME.md`, YAML frontmatter on top and an XML-sectioned Markdown body underneath, plus a dispatch snippet for whoever will call it. The file is only useful if three things line up: it lands in a directory Claude Code scans for the scope the user wants, its frontmatter keys and `tools` entries name things Claude Code honours, and its body gives the model enough structure to do the job without guessing. Each has a failure mode that shows no error: a file with a malformed `name` is skipped without a message in the session, a misspelled key is ignored, and an agent missing a tool works around the gap and reports success. This skill walks the stages in order, asks with the `AskUserQuestion` tool (single select, multi select, or free text through its other option), and never writes a file the user has not previewed. Anything the user has not said is a question, not an assumption; when they answered upfront, use the answer and say which default you took for anything they did not cover.

Read `references/agent-facts.md` once at the start: scopes and precedence, the frontmatter table, files Claude Code skips, what a subagent receives and the runtime caps are there, and a claim outside it is unverified. Read `references/failure-modes.md` when diagnosing an existing agent that never loads, is never chosen, or misbehaves.

## Stage 1: scope

Single select, with a one-line consequence each:

- plugin: `agents/<name>.md` in the plugin root, found by default scan with no manifest key. Ships wherever the plugin is enabled, under the scoped name `PLUGIN:NAME`. Lowest precedence. Claude Code drops four frontmatter keys from a plugin agent, `permissionMode`, `hooks`, `mcpServers` and `initialPrompt`, so a plugin that needs hooks or MCP servers ships them in `hooks/hooks.json` and `.mcp.json` instead, or the agent goes in a project or personal directory. Say this before the user picks plugin.
- project: `.claude/agents/<name>.md`. Versioned and shared with everyone who works in the repository, and it beats a personal agent of the same name.
- personal: `~/.claude/agents/<name>.md`. Available in every project this user opens, only to this user. Keep it project-agnostic.

If the user passed a description with the request, keep it; you still ask scope first because scope decides what Stage 2 scans.

## Stage 2: analyze the current setup

Look at what the target already has with `Read`, `Grep` and `Glob`, not the user's memory.

Build the collision list: every agent name visible at each link of the precedence chain, which runs from managed settings and `--agents` through `.claude/agents/` (every such directory from the working directory up to the repository root, the closest one winning), then `~/.claude/agents/`, then plugin `agents/` directories. Names come from the `name` key, not the filename. Keep the list; Stage 6 warns when a new name would shadow or be shadowed, because the loser is silently ignored. The built-in agents are `Explore`, `Plan` and `general-purpose`. A project or user agent named `Explore` overrides the built-in (the docs state this for `Explore` only), so a built-in name is a warning to raise with the user, not a rejection.

Then per scope:

- plugin: read `.claude-plugin/plugin.json` (an `agents` key there replaces the default scan, so check it is absent or lists this directory), existing `agents/*`, `skills/*`, `hooks/hooks.json` and `.mcp.json`. Record the plugin's own MCP servers; Stage 7 offers them.
- project: read `CLAUDE.md`, existing `.claude/agents/*`, `.claude/skills/*/SKILL.md` and the project `.mcp.json`. Note language, build tooling and conventions the instructions state; the new agent must not contradict them.
- personal: list `~/.claude/agents/*` and the servers in the user's MCP configuration.

Summarise what you found in five lines or fewer, so the user can correct you here rather than after the file is written.

## Stage 3: purpose and recommendations

Ask what the agent does, when it should be used, and what it must never do. If the user already gave a description, restate it and ask what is missing. Also ask what the dispatch must supply (what the agent cannot see: a subagent gets a fresh context, see `references/agent-facts.md`) and what exactly should come back. An agent whose caller guesses at its inputs returns a confident wrong answer, so these two answers feed `<context>`, `<output_format>` and the dispatch snippet in Stage 12.

Then screen the request before building. A subagent is the right mechanism when the task produces verbose output the caller does not need in its context, when it needs tool restrictions or permissions the main session should not have, or when the work is self-contained and can return a summary. It is the wrong one for frequent back-and-forth, for phases that share a lot of context, and for a quick targeted change. A reusable procedure that should run in the main conversation is a skill (offer `create-skill`); an always-on rule is `CLAUDE.md`. Say so plainly and offer to stop: a subagent starts with a fresh context window on every call.

From the description, recommend and explain, and let the user accept or change each:

- Tool posture: read-only jobs (review, audit, explain) get `Read`, `Grep`, `Glob`, maybe `WebFetch`; never `Edit`, `Write` or `Bash`. A job that must run tests needs `Bash`, and the body must say which commands.
- Model: `model` is one of the aliases `sonnet`, `opus`, `haiku`, `fable`, a full model ID, or `inherit`. Suggest a stronger model for judgment-heavy work and `haiku` or `sonnet` for mechanical work.
- `effort` (`low`, `medium`, `high`, `xhigh`, `max`; the available levels depend on the model): set it only when the job warrants a different level from the session's.
- `isolation: worktree` for an agent that writes files, so its edits happen in a temporary git worktree that is removed if it changes nothing.

## Stage 4: tools

Offer these groupings as a multi-select, pre-ticked from Stage 3, and write the list into `tools` as a comma-separated string or a YAML list of Claude Code tool names:

| intent               | grant                                        |
| -------------------- | -------------------------------------------- |
| read-only analysis   | `Read`, `Grep`, `Glob`                       |
| research             | `Read`, `Grep`, `Glob`, `WebFetch`, `WebSearch` |
| test execution       | `Bash`, `Read`, `Grep`                       |
| code modification    | `Read`, `Edit`, `Write`, `Grep`, `Glob`      |
| delegation           | `Agent` (the type list inside parentheses has no effect in a subagent) |
| task list            | `TodoWrite`                                  |

The field has three states. Omitted: the agent inherits every tool available to subagents, and `vibe-code subagent validate` warns on it, so write the list even for "all". A list: exactly those tools. An empty list: the agent launches with no tools. A non-empty list whose entries all fail to resolve (a misspelling, or a tool subagents cannot use) makes Claude Code refuse to launch the agent with an error naming the entries. Subagents that run in the background, which is the default, keep a smaller set of built-in tools than foreground ones, so the same list can resolve differently; the full set is in `references/agent-facts.md`.

MCP tools are `mcp__SERVER` (every tool of that server) or `mcp__SERVER__TOOL`, in `tools` or `disallowedTools`. `disallowedTools` is the denylist: it is applied first and `tools` is resolved against what remains, so a tool in both is removed, and setting both rarely does what it looks like; prefer one. An entry with a specifier such as `Bash(git push *)` removes the whole tool, not just the matching commands, so a command allow-list cannot live in frontmatter (Stage 5).

## Stage 5: command plan

A body that says "run the tests" leaves the model to pick the command every run; one that says `uv run pytest -q -x` behaves the same every time and can be reviewed once. Before the frontmatter, draft the plan as an ordered list where each line is one tool call: the tool, the exact command or arguments, and the reason. Derive the commands from Stage 2 evidence (the project's instructions, lockfiles, CI workflows), not defaults; if the repository says `uv run pytest`, do not write `python -m pytest`. Show it with a lead-in such as "Given what NAME does, I think it should generally run these, in this order" and ask for edits (add, remove, reorder, change flags) until the user accepts.

For an agent holding `Bash`, the accepted commands become a prose allow-list in `<constraints>` ("run only `uv run pytest` and `git diff`; anything else needs the caller's approval"). Prose is guidance, not enforcement. Enforcement is `permissions.allow` or `permissions.deny` rules such as `Bash(git push *)` in settings, which apply to the whole session and its subagents, or `claude --allowedTools` for one run; tell the user which they want and offer to write the settings rule, which is outside this skill's file. The steps themselves become the numbered `<workflow>`.

## Stage 6: frontmatter dialog

One question per key, with a default shown. Skip the keys that do not apply to the scope from Stage 1.

1. `name`: lowercase letters, digits and single hyphens, no `:` (reserved for `PLUGIN:NAME`) and no leading hyphen; propose one from the purpose. Check it against the Stage 2 collision list and ask for another name if it collides or is a built-in name. The filename need not match, but match it anyway so a reader can find the file. In `.claude/agents/` and `~/.claude/agents/` a file with no `name` is treated as documentation and never loads; a plugin agent with no `name` loads under its filename, so write the `name` in every scope.
2. `description`: one or two sentences, what it does and when to use it. Claude reads this to decide when to delegate, so state a trigger ("Use when a PR touches Terraform"), not only a capability, and quote the value if it contains a colon. Add "use proactively" when the user wants Claude to delegate without being asked. The validator's trigger-phrase check is a heuristic of this plugin, not a documented rule. Keep it short: Claude Code warns at startup when all custom descriptions together pass 15,000 tokens.
3. `model`: from Stage 3; check it is one of the accepted forms above.
4. `permissionMode` (project and personal only): `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions` or `plan`. When the main conversation is in `bypassPermissions`, `acceptEdits` or auto mode, the subagent keeps that mode and the setting is ignored. A subagent that declares `bypassPermissions` keeps the main conversation's mode instead (v2.1.267 or later), so do not recommend it as a way to skip prompts. Leave it unset unless there is a reason.
5. `maxTurns`: required in practice when `Bash` is granted, because a runaway delegation otherwise has no stop; the validator warns without it. At the limit Claude Code returns the output marked partial (v2.1.246 or later) and Claude can resume the agent.
6. `skills`: names of skills whose full content is injected at startup. Preloading is not access control: the agent can still invoke unlisted skills through the `Skill` tool, which only leaving `Skill` out of `tools` or listing it in `disallowedTools` prevents. A skill that only the user may invoke cannot be preloaded.
7. `memory`: `project` (recommended, shareable through version control), `user` or `local`; the agent gets a persistent directory and the `Read`, `Write` and `Edit` tools to manage it. It has no effect when auto memory is off.
8. `omitClaudeMd`: a subagent loads the `CLAUDE.md` files by default, so omit the key when the agent works inside the repository's conventions (reviewers, test runners). Set `omitClaudeMd: true` (Claude Code v2.1.271 or later) when it must stay repository-agnostic, such as a plugin agent shipped to many repositories, and say in `<context>` what it needs instead.
9. `mcpServers`: Stage 7.

If the run is non-interactive and the user supplied answers up front, use them and say which you used; do not stop to re-ask. Do not ask about other keys unless the user raises them; the table in `references/agent-facts.md` lists every key Claude Code reads.

## Stage 7: MCP

Ask, multi-select, whether the agent uses a server already configured, a new one, or none.

- Already configured (the servers Stage 2 found): add `mcp__SERVER` or `mcp__SERVER__TOOL` entries to `tools`, and in `mcpServers` a string entry naming the server if the agent should have a server the main conversation lacks.
- New server: search for its package or repository and extract its tool names from its README or registry entry. Label everything found this way as unverified and show the source URL, and do not write a tool name you could not find. If nothing is found, ask the user to paste the tool list.
- Inline definition: an `mcpServers` entry keyed by the server name, using the same schema as a `.mcp.json` entry (`stdio`, `http`, `sse` or `ws`). It connects only while the agent runs and keeps the server's tool descriptions out of the main conversation. A project agent's inline servers load only after the user trusts the folder.
- Plugin scope: Claude Code ignores `mcpServers` in a plugin agent, so the plugin's `.mcp.json` holds the server and the agent lists `mcp__SERVER__TOOL` entries.

## Stage 8: compose the body

Build the body from `assets/agent.template.md`: the frontmatter, then XML sections containing Markdown directly under it, with no single root element around the file. Write placeholders inside prose in `UPPER_CASE`, never in angle brackets, so they cannot be read as section tags. Required sections, in this order:

- `<role>`: one paragraph, who the agent is and the single job it does.
- `<context>`: what it can assume about the repository or plugin, from Stage 2, and what the dispatch supplies (Stage 3). Name instruction files by path rather than copying them.
- `<workflow>`: the accepted Stage 5 plan as numbered steps, each naming its tool and exact command.
- `<constraints>`: the never-do list with reasons, tool restrictions in prose, and what to do when blocked: stop and ask, not guess.
- `<output_format>`: the exact shape of what it returns. Only the final message goes back to the caller, so anything not in this section is lost.
- `<verification>`: how the agent checks its own work before returning and how the caller can check it. An agent that cannot say how to verify its output is not ready to write.

Optional, when the purpose warrants: `<examples>` (input and output pairs), `<escalation>` (when to stop and hand back to a human), `<tools_guidance>` (per-tool advice, such as which MCP tool to prefer). Write the body to the agent in the second person, give the reason behind each rule, and state goals more than step-by-step scaffolding when the agent runs on a stronger model. Do not write a line into the body that demands a particular model: a bug report quoted by the previous version of this skill says a subagent acted on such a line by spawning a nested one (unverified: the report is not in the docs snapshot), and the validator warns on it.

## Stage 9: preview and confirm

Show the complete file and its target path. For plugin scope, say that no `plugin.json` change is needed, because the default `agents/` folder is scanned and the optional `agents` key would replace that scan. Ask for one confirmation to write, and do not write before the answer.

## Stage 10: write and validate

Write the file to `agents/<name>.md` in the plugin root, `.claude/agents/<name>.md` in the project, or `~/.claude/agents/<name>.md` for personal scope, and nowhere else. A file in a directory named `agents` that is not under `.claude` is checked as a plugin agent.

Run `vibe-code subagent validate FILE`, add `--strict` to fail on warnings, and show the output. It runs `claude plugin validate` on the file first, then checks what that misses: the `name` form, a description with a trigger phrase, tool names, the three tool and turn-budget warnings of Stages 4 and 6, undocumented keys, the keys a plugin agent drops, and the body (the six required sections present and in order, balanced tags, no root wrapper). It exits 0 on a pass, 1 on findings and 2 when it could not check. Fix errors before moving on; warnings are judgment calls, so state which you are keeping and why.

## Stage 11: smoke test

Validation proves the file is well-formed; only Claude Code proves it loads. Offline first: `claude plugin validate .claude/agents` (the directory you wrote to, or the plugin directory) confirms the frontmatter parses and needs no login. It needs v2.1.233 or later.

Then build one non-interactive command and ask before running it:

```
claude --agent NAME -p "SMOKE_PROMPT" [--plugin-dir PLUGIN_PATH] [--allowedTools "RULE"]
```

`SMOKE_PROMPT` is the smallest real task the agent's `<workflow>` describes, phrased so a correct answer is recognisable, never "hello". `--plugin-dir` loads a plugin agent from disk for this session; `--allowedTools` mirrors the Stage 5 allow-list; a plugin agent is `PLUGIN:NAME`. `--agent` runs the definition as the whole session, so its prompt replaces the default system prompt: this proves the file loads, stays inside its tool posture and follows `<output_format>`, not that Claude delegates to it. Combining `--agent` with `-p` is not shown in the docs snapshot; treat the command as unverified until it runs. If it fails on authentication, print the command and say the model-level check is pending on the user's machine.

Run it on a yes and report three things: whether Claude Code accepted `--agent NAME`, whether it stayed inside the tool posture, and whether the answer follows `<output_format>`. A failure goes back to Stage 8, not to the user.

## Stage 12: hand off

Deliver three things, because the dispatch is where agent quality is decided:

1. The path written.
2. A dispatch snippet: the paragraph the caller uses when spawning it, naming the inputs from Stage 3 that the subagent cannot fetch and the return shape. State the facts the agent needs in the snippet, since the conversation history, the skills already invoked and the files already read never reach it.
3. The smoke-test command, whether it ran, and what it showed.

Then say how to use it. Claude delegates from the `description`; `@agent-NAME` or `@"NAME (agent)"` in a prompt makes that agent run, and a plugin agent is `@agent-PLUGIN:NAME`; `claude --agent NAME` runs a whole session as it. Edits to an existing file are picked up within seconds, but the directory is watched only if it existed when the session started, so after creating the first agent file in a new `agents` directory, restart; a plugin component needs `/reload-plugins` or a new session. Close by listing everything unverified, meaning any claim above that `references/agent-facts.md` does not carry.

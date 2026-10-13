---
name: create-hooks
description: >-
  Interactive builder for Claude Code hooks. Use it to create, add or set up a hook, or to ask what hooks would suit a repository. It asks how the hook ships (project, project-local, personal, plugin), when it runs and what it is for (failure mode, context injection, tracking), takes one or several plain descriptions or infers candidates from the repository's CI, formatter and runner, routes to permissions, a skill, a subagent, instructions or a git hook when that mechanism fits better and says why, then writes one Python script per hook that fails gracefully, the hooks entry for settings or a plugin, and proves both with vibe-code hook validate and hook test.
when_to_use: >-
  Use when the user says "block X before it runs", "run the formatter after every edit", "tell Claude how to fix Y when it fails", "log every command", "give Claude the git state at session start", describes a failure mode that repeats, asks what hooks would help here, or asks how PreToolUse, Stop, hooks.json or hook events work, even without the word "hook".
---

# Create a Claude Code hook

A hook is the one Claude Code customization that runs deterministically: a script, HTTP call or command the host runs at a lifecycle point, whose output can block a tool call, rewrite its input, inject context, keep Claude from finishing, or record what happened. That is its value and its danger. A misconfigured hook blocks every command in the repo, loops Claude at turn end, or never fires because of a misspelled event. So this skill treats a hook as production code with a blast radius: it routes away requests another mechanism serves better, designs the failure posture before the logic, writes one Python script that runs on every platform, and proves it against sample payloads before anyone relies on it.

Ask every question with the `AskUserQuestion` tool: single select, multi select, or free text through its other option. Anything the user has not said is a question, not an assumption; when they answered upfront, use the answer and say which default you took for anything they did not cover.

| phase         | what happens                                                                                  | user involvement                          |
| ------------- | --------------------------------------------------------------------------------------------- | ----------------------------------------- |
| A. Establish  | how it ships, which mode, when it runs, what it is for                                        | four questions                            |
| B. Understand | the description in the user's words; scan of existing hooks, permissions, CI and tooling      | confirm the restated intent               |
| C. Route      | is a hook the right mechanism; if not, which one and why                                      | one decision per candidate                |
| D. Design     | event, matcher, decision shape, failure posture, timeout, what Claude will read               | a question per design point, defaults set |
| E. Produce    | script from the template, config entry, validation, contract test, hand-off                   | one confirmation to write, then results   |

Read `references/hook-facts.md` once at the start: the events, payload and output fields, handler fields, matcher rules and exit-code semantics live there, and an event or field outside it is unverified (an invented event name silently never fires). Read `references/hook-catalog.md` in phase C and in infer mode, and `references/hook-json-examples.md` in phase D and E2: it shows every config shape, and `assets/hooks.example.json` is the copyable settings file. The path placeholders for scripts are written in full only in those reference files, so copy them from there.

## Phase A: establish

**A1. How it ships.** Single select:

- project: the `hooks` key of `.claude/settings.json`, with the script at `.claude/hooks/NAME.py`, addressed through the project-root placeholder `CLAUDE_PROJECT_DIR` so it resolves from any working directory. Versioned and shared: it runs for every contributor who opens the repository in Claude Code, and in `-p` runs where no trust dialog is shown. Treat it like CI config: reviewed, pinned, no `curl | sh`.
- project-local: `.claude/settings.local.json`, gitignored, one project and one person.
- personal: `~/.claude/settings.json`, every repository this user opens; keep it repo-agnostic. Cloud sessions do not read it.
- plugin: `hooks/hooks.json` at the plugin root (or the `hooks` key of `plugin.json`) with scripts under `hooks/scripts/`, addressed through the plugin-root placeholder. It ships wherever the plugin is enabled. A plugin hooks file holds only `hooks` and an optional `description`.

Team-valuable hooks derived from the repository's own CI default to project; personal preferences default to personal or project-local. Justify any deviation.

**A2. Mode.** Single select: one hook from a description; several hooks from descriptions; infer candidates from this repository's conventions. Infer mode skips A3 and A4, scans in B2, and proposes candidates from `references/hook-catalog.md`, each quoting the repository evidence that justifies it (a CI step, a formatter config, a runner wrapper). Never propose a catalog pattern whose evidence is absent, and cap the list at eight, ranked by evidence.

**A3. When it runs.** Multi-select from human-readable moments; each maps to one event and the mapping is shown after selection:

| choice                                                         | event                                                  |
| -------------------------------------------------------------- | ------------------------------------------------------ |
| when a session starts or resumes                               | `SessionStart`                                         |
| when the user sends a prompt                                   | `UserPromptSubmit`                                     |
| before Claude runs a command, edits a file or calls a tool     | `PreToolUse` (with a `matcher` on the tool name)       |
| when a tool call needs a permission decision                   | `PermissionRequest`                                    |
| after a command, edit or tool call succeeds                    | `PostToolUse`                                          |
| after a command, edit or tool call fails                       | `PostToolUseFailure`                                   |
| when Claude says it is done                                    | `Stop`                                                 |
| when a subagent starts                                         | `SubagentStart`                                        |
| when a subagent finishes                                       | `SubagentStop`                                         |
| when a turn ends on an API error                               | `StopFailure` (no decision control; tool errors are `PostToolUseFailure`) |
| when Claude Code sends a notification                          | `Notification`                                         |
| before the context window is compacted                         | `PreCompact` (matcher `manual` or `auto`)              |
| when the session ends                                          | `SessionEnd`                                           |

Any other moment: look the event up in `references/hook-facts.md` before offering it.

**A4. What it is for.** Single select, because it decides the failure posture in phase D:

- a specific problem or failure mode I keep seeing: prevent it (deny or rewrite before it happens) or recover from it (tell Claude the fix after it fails).
- injecting context Claude cannot get from files: state computed at fire time (git status, ahead/behind, what changed, environment facts).
- tracking or collecting data: audit, telemetry, metrics, nothing Claude needs to read.

## Phase B: understand

**B1. Describe.** Ask for the hook in the user's own words: what should happen, what triggers it, what Claude should see afterwards, what must never happen. For several hooks, one description each; number them. Restate each as one sentence of the form "at EVENT, when CONDITION, do ACTION, and Claude sees RESULT", and confirm before routing.

**B2. Scan.** Read what already exists so the new hook neither duplicates nor contradicts it:

- hooks at every level: the `hooks` key of `~/.claude/settings.json`, `.claude/settings.json` and `.claude/settings.local.json`; each installed plugin's `hooks/hooks.json` (installed copies live under `~/.claude/plugins/cache`, and `claude plugin details PLUGIN` prints a component inventory); and managed policy settings where readable. Levels merge, so a duplicate with different text runs twice; an identical handler in several settings files runs once, and a plugin's copy stays separate.
- permissions already in place: `permissions.allow`, `permissions.ask` and `permissions.deny` in settings. A deny rule that already covers the request makes a deny hook redundant.
- CI workflows, lint and format configs, the project runner (`uv`, `pnpm`, `make`), the pre-commit config, git hooks. These are the evidence infer mode needs and the commands enforcing hooks should run verbatim.
- how Claude Code names tools in payloads (`Bash`, `Edit`, `Write`, `Read`, `Glob`, `Grep`, `Agent`, `mcp__server__tool`), from `references/hook-facts.md`, so matchers are written against real names.

Summarise in five lines or fewer.

## Phase C: route, and say plainly when a hook is the wrong mechanism

A hook is the right tool when the behavior must be enforced without the model's cooperation, when context must be computed at fire time, or when data must be collected regardless of what the model does. It is the wrong tool in four recognizable cases. Walk each candidate through them in order and stop at the first match:

1. A static blocklist or allowlist: "never run `git push --force`", "never touch `.env`". A `permissions.deny` rule in settings, or the `--disallowedTools` flag, does this without a script; deny is checked before ask and allow, nothing can time out, and nothing fails open. A hook here adds a process launch per tool call and a timeout hole for no coverage the rule does not give. Route unless the rule depends on the command's arguments or on repository state, which a rule cannot express.
2. A persona or a multi-step procedure: "run the release when I say so", "review every PR for auth bugs". That is a skill or a subagent; a hook that runs a procedure is a skill in disguise, with worse failure modes. Offer `create-skill` or `create-subagent`.
3. Advisory guidance with exceptions: "prefer X unless the surrounding code does Y". Prose in an instructions file, not a deny. But "when Z fails, do W" is a `PostToolUseFailure` hook, not an instruction, even though it reads like guidance: an instructions file cannot handle a failure programmatically. Offer `create-instructions` only for the steering part.
4. Something humans must also obey: commit message format, tests before push. That lives in git hooks or CI. A Claude Code hook is complementary: it makes the agent run the same gate without being told ("run `pre-commit run --files ...` after each edit"). Keep the hook, and say what it complements.

Everything else stays a hook. Show one table: candidate, mechanism chosen, why in one line. When a candidate is routed away, name the exact setting, file or skill that replaces it, so the user does not lose the requirement.

## Phase D: design each hook

One question per point, defaults pre-selected from A4 and the catalog:

- **Event and matcher.** Confirm the event from A3. For tool events, `SessionStart`, `SubagentStart`, `PreCompact` and the others that take one, propose a `matcher` on the real tool, source or agent type (`Bash`, `Edit|Write`, `^(tf-reviewer|api-reviewer)$`); the grammar is in `references/hook-facts.md`, and an unmatched hook still launches a process on every call. Where the hook only matters for some commands or files, add an `if` rule such as `Bash(git *)` to the handler so the process starts only on a match; `if` holds one permission rule and works on tool events only, so a hard allow or deny stays in `permissions`.
- **Decision shape.** From the event's documented outputs only. `PreToolUse`: `hookSpecificOutput` with `permissionDecision` allow, deny or ask and `permissionDecisionReason`, or `updatedInput` to rewrite. `PostToolUse`, `PostToolUseFailure`, `SessionStart`, `SubagentStart`, `UserPromptSubmit`: `additionalContext`; `UserPromptSubmit` and `PostToolUse` also take top-level `decision: block` with `reason`, and a `PostToolUse` block does not undo the call. `Stop` and `SubagentStop`: top-level `decision: block` with `reason` to keep Claude working, or `hookSpecificOutput.additionalContext` for non-error feedback that continues the turn and is shown as hook feedback rather than a hook error. Any event accepts `systemMessage` (a warning shown to the user) and `continue: false` with `stopReason` (stops Claude entirely, overriding the event's own decision). Nothing is acted on for `SessionEnd`, `Notification` and `StopFailure`. Prefer rewrite over deny when the fix is mechanical (`pytest` becomes `uv run pytest`): Claude keeps moving and learns nothing wrong.
- **What the model reads.** Deny reasons, block reasons and `additionalContext` land in Claude's context. Draft the exact text and show it. A deny reason is guidance ("run `uv run pytest -q` instead; the bare command skips the project's virtualenv"), never an error code. `additionalContext` reads best as factual statements, because text framed as an out-of-band command can trigger Claude's prompt-injection defenses. Injected text is paid from the context budget on every fire and is capped at 10,000 characters per string, with overflow saved to a file and only a preview shown, so keep it to a few lines.
- **Failure posture, by intent.** Claude Code has no fail-closed default: a timed-out `PreToolUse` command hook does not block, and exit 1 without JSON proceeds. An enforcing hook therefore catches every exception and, on internal error, exits 2 with a reason on stderr that names the hook and the error, so Claude and the human both see why; it gets a tight `timeout` (5 seconds unless the command it runs needs more, and the validator warns above 10 on `PreToolUse`). Gates on `Stop` and `SubagentStop` are the exception: on internal error they allow with a stderr note, because a broken gate that blocks every turn end is worse than a missed gate, and they must allow when `stop_hook_active` is true so a block never loops. Context and tracking hooks catch everything, write the error to stderr, and exit 0 with no stdout. State the chosen posture in one line and confirm it.
- **Cost.** Say what the hook costs per fire (a process launch, a git call, a formatter run) and how often it fires, so the user can veto a per-tool-call hook that runs a two-second command. A slow tracking step takes `"async": true`; it can then neither block nor decide.
- **Subagents.** Settings, managed and plugin hooks also run inside subagents, and the payload carries `agent_id` and `agent_type`, so a guard written for the main thread applies there too. Hard limits for a subagent still belong in its agent file's tool list.

## Phase E: produce

**E1. Write the script** from `assets/hook.template.py`, one file per hook, Python 3.12 or newer, standard library only, no comments beyond the module docstring. The template reads the Claude Code payload (snake_case fields, dispatch on `hook_event_name`, no extra argument) and prints Claude Code output. It is a complete hook: typed payloads per event, one constructor per decision the host acts on (`deny`, `ask`, `rewrite`, `context`, `block`, `block_once`), a `CommandRunner` that turns a missing binary, a timeout and an OS error into a `CommandResult` instead of a traceback, XML context sections (`ContextSection`, rendered inside `<hook_context hook="NAME">`), and five working example handlers: `on_pre_tool_use` (deny a download piped into a shell or a force-push, ask on a release-workflow edit or a push, rewrite a bare runner command), `on_post_tool_use_failure` (recovery advice), `on_session_start` (orientation), `on_stop` (test gate that blocks once) and `on_subagent_stop` (report gate). Replace the placeholder tokens (`HOOK_NAME`, `ONE_LINE_PURPOSE`, `EVENT_NAME`, `POSTURE_VALUE`, and the `POSTURE` constant), keep the handler for this hook's event, delete the other examples, and leave `HANDLERS` with only the events this hook is registered for. Invoke through system `python3`, which the `type` alias statement needs at 3.12 or newer; go through the repo runner (`uv run`) only when the hook needs repo dependencies, and say that this makes `python3` on `PATH` a contract for every contributor. Hook scripts default to Python because JSON on stdin, regular expressions and subprocess calls are its home ground; a trivial one-liner is still written in Python here.

**E2. Write the config entry** from `assets/hooks.example.json`: a `hooks` object, event, matcher group, handlers, one concern per handler, an explicit `timeout` on every handler, and the script named through the project placeholder (or the plugin placeholder for a plugin) so it resolves from any directory. Prefer exec form, a `command` of `python3` plus an `args` array, which needs no quoting; use shell form only for a pipe or `&&`, and then wrap the placeholder in double quotes. Pick the matcher from `references/hook-facts.md`. The payload names its event, so one script registered under two events needs no extra argument; both entries point at the same file.

Show both files, then one question to write. Do not write before it.

**E3. Validate.** Run `vibe-code hook validate FILE` on the settings file or the plugin `hooks/hooks.json`, add `--strict` to fail on warnings, and show the output. It checks the hooks against the schema of the hooks reference first (handler types, field names and types, PascalCase event names that exist), runs `claude plugin validate` second, and then checks what both miss: JSON parses, `timeout` present and sane, matcher grammar, every referenced script exists. It exits 0 on a pass, 1 on findings, 2 when it could not check. A file named `hooks.json` is read as the plugin shape and any other name as a settings file; the script paths resolve for a file directly under `.claude/` or `hooks/` and are skipped elsewhere.

**E4. Contract test.** The bundled fixtures are one complete payload per file under `scripts/payloads/` (`PreToolUse-Bash.json`, `PreToolUse-Bash-dangerous.json`, `PreToolUse-Edit.json`, `PostToolUse-Bash.json`, `PostToolUseFailure-Bash.json`, `SessionStart.json`, `Stop.json`, `Stop-active.json`, `SubagentStop.json`), each carrying `hook_event_name`. Run `vibe-code hook test SCRIPT PAYLOAD` for the fixture of the hook's event, with `--expect-field KEY=VALUE` for the output it must produce (a dotted key such as `hookSpecificOutput.permissionDecision=deny`) and `--expect-silent` for the case it must leave alone. `--expect-exit` defaults to 0, so a hook that blocks through exit 2 is tested with `--expect-exit 2`, or through a JSON deny on exit 0. The command reads the event from the payload, and fails stdout that is not one JSON object except plain text on the four events that take it as context (`UserPromptSubmit`, `UserPromptExpansion`, `SessionStart`, `PostModelSwitch`). Add a payload for the situation the hook exists for (the command that should be denied, the failure text that should trigger recovery) and one for what it must leave alone, copying a bundled file and changing what differs, and keep them with the hook. Then test the failure posture itself with `--malformed`: an enforce hook exits 2 with a reason naming itself, and a context or tracking hook exits 0 silently. Show the output. A claim of "tested" without shown output does not count.

**E5. Hand off.**

- The paths written, and that a settings edit is normally picked up by Claude Code's file watcher; `/hooks` lists active hooks with their source, and a plugin hook needs the plugin reloaded.
- To watch the hook run: `claude --debug-file PATH` writes hook execution details to a known file, and a hook that did not fire shows why there. A mistyped script path fails in one of two ways, so check the first run: `python3` given a file that does not exist exits 2, the blocking code, so the hook blocks every matching call; a shell-form command whose program is not found exits 127, a non-blocking error, so an enforcing hook is silently off.
- Workspace trust: in an interactive session, hooks from a settings file are held back until the folder's trust dialog is accepted, and `-p` runs treat the folder as trusted, so a committed `.claude/settings.json` hook runs there without a prompt.
- How to turn it off: delete the entry, or `"disableAllHooks": true` in a settings file for everything the user controls; managed hooks stay unless the setting is at managed level.
- For `PreToolUse` deny rules, a removable demo trigger string the user can fire once to see the deny path.
- Under `claude -p` a `PreToolUse` `ask` cannot be answered, so headless policy lands on allow or deny.
- The mechanisms chosen for anything routed away in phase C and, when a git hook or CI gate is complemented, which one and how.
- Everything unverified: any claim above that `references/hook-facts.md` does not carry.

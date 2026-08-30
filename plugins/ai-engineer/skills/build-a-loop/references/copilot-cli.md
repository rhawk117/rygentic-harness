# GitHub Copilot CLI wiring

How to enforce a loop contract in Copilot CLI. Copilot ships weekly; confirm event names and payload fields against the current docs or `copilot --help` before shipping. Shapes below reflect what was documented as of 2026-08-30.

## Contents

- The loop and how it ends
- Autopilot
- Budgets and caps
- The stop gate
- Hook config format and discovery
- Keeping the contract alive through compaction
- The verifier custom agent
- Parallel workers with /fleet

## The loop and how it ends

Per turn: the CLI sends the full conversation history, the model responds possibly with tool requests, the CLI executes them, `assistant.turn_end` fires. A turn is one model call and its consequences. In the default interactive mode the loop ends when the model stops requesting tools, which means the model decides when it is done.

## Autopilot

`--mode autopilot` replaces model-driven termination with an explicit signal: the model must call the `task_complete` tool. If the loop would end without it, the CLI injects a nudge and restarts. This is a stronger default against premature stopping than anything in the interactive mode, and it is the right base for an unattended loop.

Always pair it with `--max-autopilot-continues N`. Without the cap, a loop that cannot satisfy itself keeps being nudged.

```
copilot --mode autopilot --max-autopilot-continues 15 --prompt "..."
```

`--plan` can be combined with `--mode autopilot` in headless `-p` runs.

## Budgets and caps

`--max-ai-credits` caps spend for non-interactive runs, `/limits` sets it interactively. It is a **soft cap**: usage is computed after a response returns, so an in-flight response finishes and actual usage can slightly exceed the number. Interactive sessions prompt to raise it; automated runs simply end.

There is no documented turn limit for the default non-interactive loop and no documented `/fleet` concurrency limit. Custom agent prompts cap at 30,000 characters.

## The stop gate

`agentStop` and `subagentStop` hooks return:

```json
{ "decision": "block" }
```

and `block` forces another turn. This is the CI-in-the-loop primitive: run the check, block on failure.

There is **no documented override after N consecutive blocks**, unlike Claude Code. A hook that always blocks will hold the session indefinitely. Build the escape into the hook itself: block on the first failure, then downgrade to advisory (`continue` plus an explanatory message) on subsequent invocations, using a small state file keyed on the session. `assets/verify_gate.py` implements this pattern.

`preToolUse` can both block and rewrite arguments:

```json
{ "permissionDecision": "deny" }
{ "toolArgs": { "command": "uv run pytest" } }
```

Tool **results** cannot be replaced. `postToolUse` and `postToolUseFailure` can only append via `additionalContext`, which injects text for the model to process.

Command hook exit codes: `0` success and output is parsed for a decision, `1` failure with output ignored (and a default deny for `preToolUse`), `2` signals `postToolUseFailure` and can carry recovery guidance.

Hooks run synchronously and block the agent. Keep them under about 5 seconds; the default timeout is 30.

## Hook config format and discovery

```json
{
  "version": 1,
  "hooks": {
    "agentStop": [
      {
        "type": "command",
        "bash": "python3 ~/.copilot/hooks/verify_gate.py",
        "timeoutSec": 30
      }
    ]
  }
}
```

Discovery, most specific last: policy dirs (`/etc/github-copilot/policy.d/*.json`, and the ProgramData equivalent on Windows), repo `.github/hooks/*.json`, user `~/.copilot/hooks/`, repo `.github/copilot/settings.json`, user `~/.copilot/settings.json`, plugin `hooks.json`. Policy hooks cannot be disabled by users; everything else yields to `disableAllHooks`.

Cloud coding agent: `.github/hooks/*.json` only, on the default branch, only the `bash` field honored. The cloud-agent documentation lists six events and does not include stop hooks, while the hooks reference does. Treat cloud stop-gating as unconfirmed and verify before relying on it.

Event names come in a native camelCase form and a PascalCase Claude-compatible form. `PreToolUse` in PascalCase accepts Claude-format matchers (`*`, or `|`-separated tool names).

## Keeping the contract alive through compaction

Background compaction starts at **80%** of context capacity and, at **95%**, the session pauses briefly to finish it. The summary keeps goals, decisions, and next steps; it loses exact wording and full command output. Each compaction writes a numbered checkpoint, inspectable with `/session checkpoints`, which is the way to diagnose what was lost.

`preCompact` cannot modify anything, so re-injection is the only defense. Write a snapshot on `preCompact`, then re-inject it once through `sessionStart` `additionalContext` on resume and through a guarded `postToolUse` `additionalContext` in the running session.

`/context` shows the token breakdown; `/compact [FOCUS]` steers a manual compaction.

## The verifier custom agent

Custom agents live in `.github/agents/` or `~/.copilot/agents/` as `<name>.agent.md`. Only `description` is required; `name`, `tools`, `model`, `skills`, and `user-invocable` are the fields that matter here.

Two things bite:

- **Skills are not inherited.** A subagent receives no skills by default and must list them explicitly. A verifier that needs the contract format must be told, in its own prompt, what the contract looks like.
- **Dispatch is by intent matching** against the agent's `name` and `description`. "Helps with code" will not be selected reliably; "Grades a diff against named acceptance criteria and reports which are met with evidence" will.

Restrict tools to enforce read-only grading:

```yaml
tools: ["grep", "glob", "view", "read"]
```

Tool names are lowercase here (`shell`, `read`, `write`, `edit`, `grep`, `glob`, `web_fetch`), not the PascalCase Claude Code names. Permission syntax is `--allow-tool='shell(git:*)'` and `--deny-tool='shell(git push)'`; deny always beats allow, even under `--allow-all`.

## Parallel workers with /fleet

The main agent decomposes the request and runs independent subtasks in parallel waves. Each subagent has its own context window and cannot see the orchestrator's history, so **every dispatch prompt must be self-contained**.

Subagents share a filesystem with no file locking. Two agents writing one file means the last to finish wins, silently. Partition explicitly by file or module in the prompts, and use "depends on" wording to serialize what must be serial.

Splitting costs more model calls than doing the work in the main agent. Use `/fleet` when the subtasks are genuinely independent, not to make sequential work feel faster.

`/delegate` hands a task to the remote coding agent on a branch with a draft PR. Reserve it for tangential work: docs, isolated refactors, async chores. Do not delegate debugging or anything needing constant feedback.

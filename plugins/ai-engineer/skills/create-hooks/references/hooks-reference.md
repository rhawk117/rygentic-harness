# Claude Code hooks — events, payloads, and output contract

This file is create-hooks's ground truth. Propose nothing that is not on this page, and when the installed Claude Code version's own docs disagree with it, trust the installed docs and update this file.

## Where hook config lives

Hooks are entries under the `hooks` key of a settings file. Sources merge; when several levels define hooks for the same event, all of them run:

1. `~/.claude/settings.json` — user level, every repo.
2. `.claude/settings.json` — project level, versioned, every contributor.
3. `.claude/settings.local.json` — project level, personal, gitignored.
4. Managed policy settings — organization level, outside user control.
5. Plugins — a `hooks/hooks.json` at the plugin root (or a `hooks` key in the plugin manifest), same shape, merged in.

`{"disableAllHooks": true}` in settings disables every hook source the user controls. Hook config is snapshotted at session start; mid-session edits need a restart or a `/hooks` review before they fire.

## Config shape

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/guard.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

- `matcher` filters which tool (or source) the event group applies to: an exact tool name (`Bash`), pipe alternation (`Edit|Write`), a regex, or an MCP tool id (`mcp__server__tool`). Events without a tool (e.g. `SessionStart`) match on their source instead (`startup`, `resume`, `clear`, `compact`).
- Each hook entry is `{"type": "command", "command": "...", "timeout": N}`.
- Env vars available to hook commands: `CLAUDE_PROJECT_DIR` (project root), `CLAUDE_PLUGIN_ROOT` (for plugin-shipped hooks), `CLAUDE_ENV_FILE`.

## Events

The core set create-hooks proposes against:

| Event                | Fires                                            | Matcher on            |
| -------------------- | ------------------------------------------------ | --------------------- |
| `SessionStart`       | Session begins                                   | startup/resume/clear/compact |
| `UserPromptSubmit`   | User submits a prompt, before the model sees it  | (none)                |
| `PreToolUse`         | Before a tool call executes                      | tool name             |
| `PostToolUse`        | After a tool call succeeds                       | tool name             |
| `PostToolUseFailure` | After a tool call fails                          | tool name             |
| `Notification`       | Claude Code emits a notification                 | notification type     |
| `SubagentStart`      | A subagent is dispatched                         | agent type            |
| `SubagentStop`       | A subagent finishes                              | agent type            |
| `Stop`               | The main agent is about to end its turn          | (none)                |
| `PreCompact`         | Before context compaction                        | manual/auto           |
| `SessionEnd`         | Session ends                                     | (none)                |

More events exist (a long tail including `PermissionRequest`, `PostCompact`, and setup/config events); consult the installed version's docs before proposing outside this table, and never invent names — a misspelled event silently never fires.

## Stdin payload

Every hook receives one JSON object on stdin, snake_case fields. Common fields:

```json
{
  "session_id": "...",
  "cwd": "/path/to/project",
  "hook_event_name": "PreToolUse",
  "transcript_path": "/path/to/transcript.jsonl",
  "permission_mode": "default"
}
```

Per-event additions:

- Tool events add `tool_name` and `tool_input` (the tool's own argument object: `Bash` has `tool_input.command`, `Edit` has `tool_input.file_path`/`old_string`/`new_string`, and so on). `PostToolUse` adds `tool_response`; `PostToolUseFailure` carries the error.
- `Stop` adds `stop_hook_active`: true when the turn is already continuing because a Stop hook blocked it. Every Stop gate must allow when this is true, or the turn loops forever.
- `SessionStart` adds `source`; `PreCompact` distinguishes manual from auto.
- `UserPromptSubmit` adds the prompt text; `SubagentStart`/`SubagentStop` add the agent type.

## Output contract

Exit codes first, JSON second:

- **Exit 0** — success. Stdout may be empty, may carry plain text (added as context on context-accepting events like `UserPromptSubmit` and `SessionStart`), or may carry one JSON object using the fields below.
- **Exit 2** — block. Stderr is the reason, and the model reads it, so write it as an actionable instruction.
- **Any other exit** — non-blocking error; the tool call proceeds and the failure is surfaced to the user.

Structured output goes in a `hookSpecificOutput` wrapper (plus optional top-level `"systemMessage"` shown to the user):

- `PreToolUse`:

  ```json
  {
    "hookSpecificOutput": {
      "hookEventName": "PreToolUse",
      "permissionDecision": "allow",
      "permissionDecisionReason": "why",
      "updatedInput": { "command": "uv run pytest" }
    }
  }
  ```

  `permissionDecision` is `allow`, `deny`, `ask`, or `defer`. `updatedInput` rewrites the tool's arguments before execution — the rewrite pattern (`allow` + `updatedInput`) replaces denying and hoping the model retries correctly.

- `PostToolUse` and `Stop`: `{"decision": "block", "reason": "..."}` blocks (for Stop, the turn continues with the reason as guidance — guard with `stop_hook_active`).
- `UserPromptSubmit`: `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "..."}}` injects context; a `decision: "block"` rejects the prompt.
- `SessionStart` and `SubagentStart`: `additionalContext` injects live context at the boundary.

Scripts should emit at most one JSON object on stdout and keep diagnostics on stderr; interleaved prose on stdout corrupts parsing.

## Non-interactive sessions

Under `claude -p` hooks run normally, but there is no human to answer a permission prompt: a `PreToolUse` decision of `ask` cannot be resolved interactively, so automated policy must land on `allow` or `deny`. Anything that genuinely needs a human belongs in interactive sessions only.

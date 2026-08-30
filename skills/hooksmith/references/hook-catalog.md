# Hook catalog — repo signal → candidate hook

Map Phase 1 evidence onto these patterns. Every proposal must quote its signal. If a pattern's signal is absent from the repo, the pattern is off the table — do not propose it "just in case".

## CI mirror gates (highest value density — they prevent red CI)

### Done-gate: run CI's checks before the agent declares done
- Signal: CI workflow runs lint/tests/typecheck (e.g. `npm test`, `uv run pytest`, `ruff check`, `tox`, `cargo clippy`).
- Hook: `Stop`. Run the same commands CI runs (fast subset if the full suite is slow — prefer lint + typecheck + affected tests). On failure: `{"decision": "block", "reason": "<failing output + 'fix these before finishing'>"}`. On pass, or when `stop_hook_active` is true: exit 0 with no output — block once then stand down, so the turn can never loop.
- Cost: seconds per turn end. Keep the command set fast; a 5-minute gate will get disabled by annoyed humans.
- Placement: repo.

### Format/lint after edit
- Signal: CI or pre-commit runs a formatter (ruff format, prettier, gofmt, a fix-capable linter).
- Hook: `PostToolUse`, matcher `Edit|Write`. If `tool_input.file_path` matches, run the formatter on the touched file; optionally return `additionalContext` noting what was reformatted so the model re-reads before further edits.
- Cost: milliseconds–low seconds per edit. Very low false-block risk (it can't block).
- Placement: repo.

### Command rewrite to project runner
- Signal: repo runs tools through a wrapper (uv, poetry, pnpm, make targets) but agents habitually run bare `pytest`/`ruff`/`tsc`.
- Hook: `PreToolUse`, matcher `Bash`. If `tool_input.command` starts with a bare tool name and the project marker exists (pyproject.toml etc.), return `permissionDecision: "allow"` with `updatedInput` carrying the wrapped command (`uv run <original>`). Rewrite, don't deny — the agent keeps moving and learns nothing wrong.
- Cost: sub-ms string check on every shell call.
- Placement: repo.

## Guardrails (justify with risk surface found in THIS repo, and dedupe first)

Before proposing anything here, check what already runs at user and policy level — security-conscious users often carry global protected-path and dangerous-command hooks, and a repo-level duplicate executes twice per tool call. Propose only what the repo's own evidence demands and nothing existing coverage already handles.

### Protected paths
- Signal: publish/release workflows, lockfiles, migrations dirs, IaC dirs, .env patterns, CODEOWNERS-guarded paths.
- Hook: `PreToolUse`, matcher `Edit|Write|Bash`. `permissionDecision: "deny"` (or `"ask"` in interactive flows) on writes to the protected set, with a `permissionDecisionReason` that names the escalation path ("release workflow — change it via PR review, not an agent session").
- Cost: sub-ms. False-block risk if the path set is too broad — start narrow.
- Placement: repo.

### Dangerous command classes
- Signal: any repo (baseline), stronger with deploy scripts or db access in-repo.
- Hook: `PreToolUse`, matcher `Bash`. Deny: sudo/su, rm -rf /, mkfs/dd, curl|sh / wget|sh, force-push to default branch, package publish (npm publish, uv publish, cargo publish), destructive db verbs against non-local hosts. Ask (interactive only): env dumps piped anywhere, chmod 777.
- Cost: sub-ms regex set. Keep the deny list short and incremental — broad matches erode trust in the whole hook layer.
- Placement: repo for team baseline, user for personal extras.

## Fresh-session context and recovery

### Dynamic session orientation
- Signal: things an agent starting cold needs but can't know from static files — is the working tree dirty and with what, ahead/behind upstream, what repo-specific skills/commands exist, non-obvious build/test invocations, top-level layout.
- Hook: `SessionStart` script that COMPUTES state at fire time and returns it as `additionalContext`: `git status --porcelain` summary + ahead/behind, a two-level directory sketch, the canonical build/test/lint commands, available repo skills. A hook earns its place here precisely because the content is live — static prose belongs in the instructions file, not a hook. Keep the output to ~10 lines; it's paid from the context budget every session.
- Cost: one git invocation + a dir walk per session start. Near-zero risk (can't block).
- Placement: repo.

### Failure playbook
- Signal: predictable failure modes (missing venv → `uv sync`, stale deps → `npm install`, migrations out of date).
- Hook: `PostToolUseFailure` mapping recognizable error text to the fix command via `additionalContext`.
- Cost: ms per failed call, zero on success path.
- Placement: repo.

## Hygiene and telemetry

### Audit log
- Signal: compliance need, or user asks for visibility.
- Hook: `UserPromptSubmit` + `PreToolUse` (+ `SessionStart`/`SessionEnd`) appending redacted JSONL to a gitignored path. Redact token-shaped strings before writing. Add the log dir to .gitignore in the same change.
- Placement: user for personal telemetry, repo only if the team wants shared audit policy.

## Subagent patterns (only when the repo/user actually uses custom agents)

### Per-agent context injection
- Signal: .claude/agents/ or plugin agents exist.
- Hook: `SubagentStart`, matcher on agent type, `additionalContext` with the per-agent charter (scope, report format).

### Subagent report gate
- Signal: custom agents expected to return structured reports.
- Hook: `SubagentStop` validating response shape; block once with the schema as reason (track one-shot state yourself — no `stop_hook_active` guard exists here).
- Caveat: hard restrictions for a subagent belong in its agent file's `tools`/`disallowedTools`; this gate is quality control, not a security boundary.

## Anti-patterns — do not propose

- Hooks for events that don't exist (PreCommit, OnFileSave). Check the reference table.
- Automation that depends on an interactive answer: a `permissionDecision` of `ask` is unanswerable under `claude -p` — headless policy lands on `allow` or `deny`.
- A deny-everything security posture via hooks alone — hooks complement permissions and agent definitions, they don't replace them.
- Slow enforcement hooks: a gate that stalls every turn gets disabled by annoyed humans, and a gate that times out has enforced nothing.
- Injecting large context blobs at `SessionStart` — context budget is a real cost every session.
- `SessionStart` hooks that inject STATIC text an instructions file could carry — hooks are for state computed at fire time.
- Repo-level duplicates of guards the user/policy level already runs — both fire, doubling latency for zero coverage.

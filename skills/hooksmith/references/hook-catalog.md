# Hook catalog — repo signal → candidate hook

Map Phase 1 evidence onto these patterns. Every proposal must quote its signal. If a pattern's signal is absent from the repo, the pattern is off the table — do not propose it "just in case".

## CI mirror gates (highest value density — they prevent red CI)

### Done-gate: run CI's checks before the agent declares done
- Signal: CI workflow runs lint/tests/typecheck (e.g. `npm test`, `uv run pytest`, `ruff check`, `tox`, `cargo clippy`).
- Hook: agentStop. Run the same commands CI runs (fast subset if the full suite is slow — prefer lint + typecheck + affected tests). On failure: {"decision":"block","reason":"<failing output + 'fix these before finishing'>"}. On pass or when stop_hook_active is true: {"decision":"allow"} — block once then advisory, so the turn can never loop.
- Cost: seconds per turn end. Keep the command set fast; a 5-minute gate will get disabled by annoyed humans.
- Placement: repo.

### Format/lint after edit
- Signal: CI or pre-commit runs a formatter (ruff format, prettier, gofmt, xo --fix-capable linter).
- Hook: postToolUse. If toolName is an edit/create tool and the file matches, run the formatter on the touched file; optionally return additionalContext noting what was reformatted. Never rewrite file content via modifiedResult (that field rewrites the tool RESULT shown to the model, not the file).
- Cost: milliseconds–low seconds per edit. Very low false-block risk (it can't block).
- Placement: repo.

### Command rewrite to project runner
- Signal: repo runs tools through a wrapper (uv, poetry, pnpm, make targets) but agents habitually run bare `pytest`/`ruff`/`tsc`.
- Hook: preToolUse, matcher on the shell tool. If toolArgs.command starts with a bare tool name and the project marker exists (pyproject.toml etc.), return {"modifiedArgs": {"command": "uv run <original>"}}. Rewrite, don't deny — the agent keeps moving and learns nothing wrong.
- Cost: sub-ms string check on every shell call.
- Placement: repo.

## Guardrails (justify with risk surface found in THIS repo, and dedupe first)

Before proposing anything here, check what already runs at user and policy level — security-conscious users often carry global protected-path and dangerous-command hooks, and a repo-level duplicate executes twice per tool call. Propose only what the repo's own evidence demands and nothing existing coverage already handles.

### Protected paths
- Signal: publish/release workflows, lockfiles, migrations dirs, IaC dirs, .env patterns, CODEOWNERS-guarded paths.
- Hook: preToolUse, matcher on edit/create/shell tools. Deny or ask on writes to the protected set, with a reason that names the escalation path ("release workflow — change it via PR review, not an agent session").
- Cost: sub-ms. False-block risk if the path set is too broad — start narrow.
- Placement: repo.

### Dangerous command classes
- Signal: any repo (baseline), stronger with deploy scripts or db access in-repo.
- Hook: preToolUse on shell. Deny: sudo/su, rm -rf /, mkfs/dd, curl|sh / wget|sh, force-push to default branch, package publish (npm publish, uv publish, cargo publish), destructive db verbs against non-local hosts. Ask: env dumps piped anywhere, chmod 777.
- Cost: sub-ms regex set. Keep the deny list short and incremental — broad matches erode trust in the whole hook layer.
- Placement: repo for team baseline, user for personal extras.

## Fresh-session context and recovery

### Dynamic session orientation
- Signal: things an agent starting cold needs but can't know from static files — is the working tree dirty and with what, ahead/behind upstream, what repo-specific skills/commands exist, non-obvious build/test invocations, top-level layout.
- Hook: sessionStart script that COMPUTES state at fire time and returns it as additionalContext: `git status --porcelain` summary + ahead/behind, a two-level directory sketch, the canonical build/test/lint commands, available repo skills. A hook earns its place here precisely because the content is live — static prose belongs in the instructions file, not a hook. Keep the output to ~10 lines; it's paid from the context budget every session.
- Cost: one git invocation + a dir walk per session start. Near-zero risk (can't block).
- Placement: repo.

### Failure playbook
- Signal: predictable failure modes (missing venv → `uv sync`, stale deps → `npm install`, migrations out of date).
- Hook: postToolUseFailure mapping recognizable error text to the fix command via additionalContext.
- Cost: ms per failed call, zero on success path.
- Placement: repo.

## Hygiene and telemetry

### Audit log
- Signal: compliance need, or user asks for visibility.
- Hook: userPromptSubmitted + preToolUse (+ sessionStart/sessionEnd) appending redacted JSONL to a gitignored path. Redact token-shaped strings before writing. Add the log dir to .gitignore in the same change.
- Placement: user for personal telemetry, repo only if the team wants shared audit policy.

### Output truncation for noisy commands
- Signal: repo has chatty tooling (verbose test runners, big build logs) and long sessions.
- Hook: postToolUse on shell; if toolResult.textResultForLlm exceeds a threshold, return modifiedResult with head+tail and a note. Saves context budget; risk: truncating the line the model needed — keep generous thresholds.
- Placement: user (taste-dependent).

## Subagent patterns (only when the repo/user actually uses custom agents)

### Per-agent context injection
- Signal: .github/agents/ or ~/.copilot/agents/ profiles exist.
- Hook: subagentStart, matcher on agent names, additionalContext with the per-agent charter (scope, report format).

### Subagent report gate
- Signal: custom agents expected to return structured reports.
- Hook: subagentStop validating response shape; block once with the schema as reason (track one-shot state yourself — no stop_hook_active here), or modifiedResponse to trim/redact before the parent ingests it.
- Caveat: pair with the #2392 note from hooks-reference.md if anyone expects preToolUse to constrain subagents.

## Anti-patterns — do not propose

- Hooks for events that don't exist (preCommit, onFileSave). Check the reference table.
- prompt-type hooks for automation (new interactive sessions only; dead in -p and resumes).
- A deny-everything security posture via hooks alone — timeouts fail open and subagent enforcement is unproven; hooks complement permissions and agent profiles, they don't replace them.
- Slow enforcement hooks (see fail-open timeout note).
- Injecting large context blobs at sessionStart — context budget is a real cost every session.
- sessionStart hooks that inject STATIC text an instructions file could carry — hooks are for state computed at fire time.
- Repo-level duplicates of guards the user/policy level already runs — both fire, doubling latency for zero coverage.

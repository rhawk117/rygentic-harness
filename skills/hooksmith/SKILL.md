---
name: hooksmith
description: Analyze a repository and design, select, plan, and implement GitHub Copilot hooks that pay off for that specific repo — driven by its CI workflows, lint/format/type configs, existing agent config, and fresh-session context needs. Use this whenever the user wants Copilot hooks set up, audited, extended, or recommended for a repository; asks "what hooks would help here" or "set up hooks for this repo"; wants CI conventions enforced during agent sessions (format-on-edit, test gates before done, command rewriting); wants session context injection (working-tree state, repo layout, available skills) for agents starting cold; or wants automation for Copilot CLI or the Copilot coding agent — even if they never say the word "hook".
---

# Hooksmith

Design and install GitHub Copilot hooks for a repository, end to end: recon → evidence-ranked candidates → user selection → approved plan → implementation → verification.

The core idea: a hook is only worth its latency and failure modes if it enforces something this repository already cares about. CI is the best evidence of what a repo cares about — every check CI runs is a failure the agent could have caught minutes earlier, during the session. Generic hook packs are noise; hooks justified by the repo's own workflows are leverage. Every candidate you propose must point at its evidence.

Ground truth for events, payloads, and config lives in `references/hooks-reference.md`. Read it before proposing anything and never invent event names or output fields beyond it — a config with a misspelled or imagined event silently never fires, which is worse than no hook.

## Phase 1 — Recon (read-only)

Build an evidence inventory before forming opinions. Do not write anything in this phase.

Inventory these signal classes, with why:

- CI workflows (`.github/workflows/*.yml`): every lint, format, typecheck, or test step is a candidate for an agent-time equivalent (a gate before the agent declares done, a format-after-edit, a command rewrite). Note the exact commands CI runs — hooks should run the same commands, not approximations, or the gate and CI will disagree.
- Lint/format/type configs and the runner: ruff/eslint/prettier/biome configs, mypy/pyright/ty settings, pre-commit config, `pyproject.toml`/`uv.lock` (→ `uv run`), `package.json` scripts, `Makefile`/`justfile`. These say what "clean" means here and what wrapper bare commands should be rewritten to.
- Fresh-session needs: what does an agent starting cold in this repo not know that it needs immediately? Dirty working tree state, ahead/behind vs upstream, directory layout, repo-specific skills/commands, non-obvious build/test invocations. This feeds dynamic `sessionStart` context injection — the hook's edge over instruction files is that it computes live state at session start, not static prose.
- Existing agent config: `.github/hooks/*.json`, `.github/copilot/settings.json`, user-level `~/.copilot/hooks/`, policy hooks, instruction files, `.agent.md` profiles. Hook sources combine across levels (policy → repo → user → plugins), so a duplicate at two levels runs twice — propose only gaps, never collisions, and say what you're deliberately not proposing because it's already covered. Audit existing hooks for defects too (stale redaction patterns, missing timeouts, fail-open enforcement): report what you find and offer the fix as a candidate, but never modify someone's existing hook uninvited — other machinery may depend on its exact behavior.
- Risk surface, conditionally: publish/release workflows, lockfiles, migration dirs, credential-shaped paths. Propose guardrail hooks only when the repo shows concrete risk evidence AND no existing user/policy-level hook already covers the concern — generic security packs duplicate what security-conscious users run globally.
- Team signals: contributor platforms and CONTRIBUTING conventions — mainly to validate the script-language choice in Phase 3.

Summarize as a short evidence table: signal → where found → what it implies. This table is what makes the next phase credible.

## Phase 2 — Candidates and user selection

Read `references/hook-catalog.md` and map your evidence onto its patterns. Select 4–8 candidates at most, ranked by evidence strength. Fewer, well-justified candidates beat a carpet-bomb: each hook adds per-tool-call or per-turn latency and a new way for the session to misbehave, so an unjustified hook is tech debt from day one.

For each candidate present: what it does, event(s) + matcher, the evidence line from Phase 1 (quote the actual workflow/command, e.g. "CI runs `npm test` (xo + ava) on every push → agentStop gate running the same"), the cost/risk (latency, false-block potential), and proposed placement.

Then ask the user which candidates to build, using whatever ask-user mechanism your environment provides (multi-select where supported), recommending your top picks. This selection is the user's call, not yours — they know constraints you can't see (team appetite, rollout policy, existing tooling).

Placement logic (confirmed per-hook in the plan): repo-derived, team-valuable hooks (CI gates, protected paths for this repo) default to `.github/hooks/` where they're versioned and the cloud coding agent also picks them up; personal-preference hooks (output truncation tastes, personal telemetry) default to `~/.copilot/hooks/`. Justify any deviation.

## Phase 3 — Plan and approval

For the selected hooks, write a concrete plan before touching any file. Per hook:

- Files to create: config JSON path (descriptive filename, one file per concern) and script path(s).
- Surface consequence: anything placed in `.github/hooks/` also executes for the Copilot cloud coding agent once it reaches the default branch — so those entries need a `bash` variant, must tolerate `ask` degrading to `deny`, and can't rely on egress beyond allow-listed hosts. State this in the plan for every repo-level hook rather than letting the team discover it.
- Event(s), matcher, `timeoutSec`. Set timeouts deliberately: hook errors deny the tool call (fail closed), but timeouts always fail OPEN — a slow enforcement hook silently allows what it meant to block. Keep enforcement hooks fast and set tight timeouts so slowness is visible during verification rather than silent in production.
- Script language: default to Python 3, stdlib only — one cross-platform script beats maintaining bash+powershell pairs, and hook logic (JSON on stdin, regex, subprocess) is Python's home turf. Invoke via system `python3` for speed; go through the repo's runner (`uv run`) only when the hook genuinely needs repo dependencies. Note the contract this creates for repo-level hooks: `python3` on every contributor machine — where Phase 1 found evidence against that, fall back to bash plus a `powershell` variant and say why. Trivial one-liners may stay bash.
- Failure behavior: what happens on deny (the `permissionDecisionReason` the agent will see — write it as guidance, since the model reads it and adjusts), and for gates, how the block avoids looping (block once, then allow when `stop_hook_active` is true).
- The verification step for this specific hook (which sample payload proves it, what a live canary looks like).

Present the plan and get explicit approval through the environment's ask-user mechanism before implementing. If the user asked only for recommendations or a proposal, stop after presenting — do not implement uninvited.

## Phase 4 — Implement

Only after approval. Conventions that keep hooks debuggable:

- Config: `{"version": 1, "hooks": {...}}`, camelCase event names, one concern per file (`ci-gates.json`, `protected-paths.json`), explicit `timeoutSec` on every entry.
- Scripts: read stdin once; emit either nothing or a single line of JSON on stdout (mixed prose on stdout corrupts the contract — send diagnostics to stderr or a log file); exit 0 with output, non-zero only to signal failure. Redact token-shaped strings before logging anything. Shebang + executable bit.
- Deny reasons and injected context are read by the model: write them as actionable instructions ("run `uv run pytest` instead"), not error codes.
- Keep any `sessionStart`/`subagentStart` injected context short — it occupies the session's context budget on every session, so every line must earn its place.

## Phase 5 — Verify (never skip)

An untested hook is a liability installed at the exact point of maximum blast radius. Verify in layers:

1. Config validity: parse every JSON file; check every event name against `references/hooks-reference.md`; check every referenced script path resolves.
2. Contract tests: run every script through `scripts/test_hook.py` with the bundled sample payloads in `scripts/payloads/` (add a repo-specific payload when the hook matches on arguments — e.g. a `toolArgs.command` that should be denied and one that should pass). Show the test output to the user; a claim of "tested" without shown output doesn't count.
3. Live canary where practical: hooks load when the CLI starts, so note that a restart is required; for a preToolUse deny rule, include a removable demo trigger (a magic string like `HOOKSMITH_DENY_DEMO`) the user can fire once to see the deny path work, then delete.
4. Hand-off summary: what was installed where, expected behavior, how to disable (remove the file, or `COPILOT_HOOKS_DISABLED=1` — noting policy-level hooks ignore it), and any open caveats.

## Non-interactive mode

When no ask-user dialog is available (headless run, `copilot -p`, CI), do not stall waiting for selection or approval. Implement the top 3 strongest-evidence candidates, and write an ASSUMPTIONS section at the top of the hand-off summary stating what was chosen and why, so a human can review and prune. The selection and approval gates exist to respect user judgment — in their absence, substitute conservative defaults and full transparency, never silence.

## Known limits — state these when relevant, don't discover them in production

- Subagent enforcement gap: a public, still-open copilot-cli issue reports preToolUse restrictions not being enforced on subagents spawned via the task tool. Never present a preToolUse hook as a security boundary for subagent activity without testing it on the installed CLI version; hard restrictions for custom agents belong in their agent profiles, with hooks as defense in depth.
- Cloud coding agent (if placing in `.github/hooks/`): bash only, config read from the default branch only, `ask` decisions degrade to `deny`, egress firewalled. Say so if the repo uses the coding agent.
- Hooks are also a supply-chain surface: repo-level hooks execute for everyone who runs the CLI in that repo. Treat hook scripts with the same review bar as CI config.

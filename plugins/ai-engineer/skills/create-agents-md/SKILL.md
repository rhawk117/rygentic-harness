---
name: create-agents-md
license: Apache-2.0
description: >-
  Generate an evidence-based AGENTS.md for the current repository by dispatching two explorer subagents (toolchain/verification and conventions/structure), then wire per-platform router files — CLAUDE.md as an @AGENTS.md import for Claude Code, .github/copilot-instructions.md as a pointer for Copilot surfaces that don't read AGENTS.md. Use this whenever the user wants to create, regenerate, audit, port, or merge repository instruction files — AGENTS.md, CLAUDE.md, copilot-instructions.md, cursor/windsurf/cline rules — or says anything like "set up agent instructions", "init this repo for Claude/Copilot", "write an AGENTS.md", "make a CLAUDE.md", even if they name only one platform's file.
---

# create-agents-md

Produce a small AGENTS.md of verified facts — not a comprehensive document. The rules here come from vendor docs and three 2026 controlled studies: instruction files do not generally raise agent task success; the content that pays is exact commands and explicit conventions; repo-overview prose adds cost with no measured benefit; adherence drops as files grow. When you need the why behind any rule, or the user challenges one, read `references/evidence.md`.

## Step 1 — Ask before touching the repo

Ask two things up front, in one dialog where the platform supports it:

1. **Platform**: Claude Code, GitHub Copilot, or both. This decides which router files you write in step 5.
2. **Explorer model**: a free-text input field — the user types the model the two explorer subagents run on (examples to show them: `claude-haiku-4-5`, `claude-sonnet-5`). Normalize what they type to a real model identifier available on this platform. If it doesn't match anything cleanly, confirm your best match before dispatching — never silently substitute. One model applies to both explorers.

In Claude Code, use AskUserQuestion (its Other option gives the free-text field). In Copilot CLI, use the ask-user mechanism your harness provides. If the user already answered either question in their request ("use haiku for the explorers", "I'm on both"), don't re-ask it. Headless or no ask mechanism available: state your assumptions at the top of your output (platform: both; model: this platform's fast tier) and proceed.

## Step 2 — Dispatch two explorers in parallel

Read `references/explorer-prompts.md`, fill in the placeholders, and dispatch both prompts as parallel subagents on the chosen model:

- **Explorer A — toolchain & verification**: build/test/lint/typecheck/run commands, CI workflows, validation scripts.
- **Explorer B — conventions & structure**: layout, git conventions from history, existing agent-config files to mine, style deviations, testing patterns.

In Claude Code: two Task tool calls in a single message, `model` set from step 1. In Copilot: your harness's subagent dispatch with the model override. No subagent mechanism available: work through both briefs yourself, sequentially — the report structure still applies, and the separation keeps discovery honest.

Explorers report XML distinguishing verified findings from inferred ones, with file-path evidence. When reports disagree with README or docs, trust CI workflow files — CI is the ground truth of what must pass.

## Step 3 — Synthesize AGENTS.md

Build the file from the two reports using the skeleton in `references/template.md`. Section order and content rules:

1. **Commands** — build, test, lint, typecheck, run, with real flags. Lead with these; they're the highest-value content and the only class with empirical support. Include only commands an explorer verified (ran, or extracted verbatim from CI). Prefix anything less certain with `(unverified)` rather than dropping the marker.
2. **Stack** — exact: "Python 3.12, uv, ruff, pytest", never "a Python project".
3. **Layout** — only non-obvious pointers ("API handlers live in `src/api/handlers/`"). If the tree is self-explanatory, keep this to two or three lines.
4. **Conventions** — only deviations from ecosystem defaults, each with its why. Include the observed commit-message convention from git history.
5. **Boundaries** — always do / ask first / never touch. Mined rules about generated code, migrations, and protected paths land here.
6. **Verification** — what the agent runs before declaring work done. Usually a subset of Commands; make it explicit anyway, because "able to validate its own changes" is the mechanism behind every vendor's quality claim.

Omit entirely: repo-overview prose, anything a configured linter/formatter already enforces, anything derivable by reading the codebase (directory listings, dependency inventories), personas, vague quality demands. One real code example is allowed only when style genuinely deviates from what a model would produce by default. Target ≤150 lines; if you're over, cut Layout and Conventions before touching Commands and Boundaries.

## Step 4 — Merge with existing instruction files

If the repo already has AGENTS.md, CLAUDE.md, copilot-instructions.md, or cursor/windsurf/cline rules, Explorer B quotes their keep-worthy rules. Migrate into AGENTS.md: commands, real conventions, boundary rules. Drop: personas, linter duplicates, overview prose, and anything contradicting explorer findings (a rule that disagrees with current CI is stale, not sacred — but list what you dropped and why when you present the draft). Genuinely platform-specific rules stay in that platform's router file, not AGENTS.md.

## Step 5 — Router files by platform

**Claude Code** — Claude Code reads CLAUDE.md, not AGENTS.md. Write a CLAUDE.md whose first line is `@AGENTS.md` (the vendor-official import pattern; works on Windows where symlinks need elevation). Claude-specific rules go in a `## Claude Code` section below the import; delete the section if there are none.

**GitHub Copilot** — Copilot's agent surfaces (cloud agent, CLI, VS Code, code review) read AGENTS.md natively, so no router is needed for them. Write `.github/copilot-instructions.md` as a short pointer anyway: it covers the chat surfaces that don't load AGENTS.md (github.com Chat; JetBrains, Visual Studio, Xcode, Eclipse chat). Keep it a pointer, not a mirror — duplicated content drifts. Exact contents in `references/template.md`.

**Both** — write all three files.

## Step 6 — Self-check, confirm, write

Before showing the user anything, check your draft: within the line budget; Commands section contains only verified or explicitly-marked commands; none of the omitted content classes crept in; routers contain no rules that belong in AGENTS.md. Then present the draft — plus a unified diff against any existing instruction files — and get confirmation before writing. Headless: write the files and lead your report with what you wrote and what you dropped from existing files.

## Notes

- Monorepo: generate the root AGENTS.md only; note in your summary that nested AGENTS.md (Copilot: nearest-file-wins) or path-scoped rules (Claude: `.claude/rules/` with `paths:`) are the follow-up for per-package instructions.
- Explorers are read-only. All writes happen in step 6, by you, after confirmation.
- If both explorers come back thin (tiny repo, no CI), a 20-line AGENTS.md is a success, not a failure. Never pad.

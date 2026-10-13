---
name: create-agents-md
when_to_use: >-
  Use when the user says "set up agent instructions", "write an AGENTS.md", "make a CLAUDE.md", "init this repo for Claude", or asks why Claude ignores their AGENTS.md, even if they name only one file.
description: >-
  Generate an evidence-based AGENTS.md for the current repository by dispatching two explorer subagents (toolchain and verification, conventions and structure), and optionally a CLAUDE.md that imports it with @AGENTS.md. Use it to create, regenerate, audit or merge repository instruction files: AGENTS.md, CLAUDE.md, CLAUDE.local.md and cursor, windsurf or cline rules.
---

# Create an AGENTS.md

Produce a small `AGENTS.md` of verified facts, not a comprehensive document. The rules come from vendor docs and three 2026 controlled studies. Instruction files do not generally raise agent task success. The content that pays is exact commands and explicit conventions. Repo-overview prose adds cost with no measured benefit, and adherence drops as files grow. When you need the why behind a rule, or the user challenges one, read `references/evidence.md`.

The output is `AGENTS.md`, and a `CLAUDE.md` that imports it when step 1 or the loading rules below call for one. Nothing else is written.

## How Claude Code reads AGENTS.md

These rules decide what step 1 asks and what step 5 writes.

- Claude Code reads `AGENTS.md` directly only from v2.1.277. Before v2.1.281 some sessions (Amazon Bedrock, telemetry disabled) read `CLAUDE.md` files only.
- By default Claude reads `AGENTS.md` only when there is no `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` in the working directory or any directory above it. With one of those present, Claude reads the `CLAUDE.md` files only.
- A `CLAUDE.md` that contains `@AGENTS.md` brings `AGENTS.md` in through the import. Claude does not read it twice.
- The user's `~/.claude/CLAUDE.md`, the managed `CLAUDE.md` and `.claude/rules/` files do not count for that check.
- The **Project instructions** setting in `/config` can change the default.

## Step 1: ask before touching the repo

Check with `Glob` whether a `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` exists in the working directory or above it. Then ask two things in one `AskUserQuestion` call:

1. **Output**: `AGENTS.md` alone, or `AGENTS.md` plus a `CLAUDE.md` whose first line is `@AGENTS.md`. Recommend the import file when any `CLAUDE.md` or `CLAUDE.local.md` already exists on the path, when the team runs Claude Code older than v2.1.277, or when the sessions may be on Bedrock. Recommend `AGENTS.md` alone otherwise: it is the one file other tools read too. When a `CLAUDE.md` or `CLAUDE.local.md` already exists, offer only the import option and say why: Claude would not read an `AGENTS.md` alone.
2. **Explorer model**: the model both explorers run on. Offer the aliases `haiku` and `sonnet` as options, and let the user type another through `Other`; a full model ID such as `claude-sonnet-5` also works. Confirm your reading of anything that is not an alias or a full model ID before dispatching, and never substitute silently. One model applies to both explorers.

If the user already answered either question in the request ("use haiku for the explorers"), do not ask it again. Headless, or no way to ask: state your assumptions at the top of the output (output: `AGENTS.md` alone, or with the import when step 1's check found a `CLAUDE.md` or `CLAUDE.local.md`; model: `haiku`) and go on.

## Step 2: dispatch two explorers in parallel

Read `references/explorer-prompts.md`, fill in the placeholders, and dispatch both prompts as two Agent tool calls in a single message, with `model` set to the step 1 answer:

- **Explorer A, toolchain and verification**: build, test, lint, typecheck and run commands, CI workflows, validation scripts.
- **Explorer B, conventions and structure**: layout, git conventions from history, existing instruction files to mine, style deviations, testing patterns.

Explorers are read-only and cannot ask the user anything. They may search, read and run safe inspection commands. They report XML that separates verified findings from inferred ones, with file-path evidence. When a report disagrees with the README or other docs, trust the CI workflow files: CI is the ground truth of what must pass.

## Step 3: synthesize AGENTS.md

Build the file from the two reports with the skeleton in `references/template.md`. Section order and content rules:

1. **Commands**: build, test, lint, typecheck, run, with real flags. Lead with these. They are the highest-value content and the only class with empirical support. Include only commands an explorer verified (ran, or extracted verbatim from CI). Prefix anything less certain with `(unverified)`.
2. **Stack**: exact. "Python 3.12, uv, ruff, pytest", never "a Python project".
3. **Layout**: only non-obvious pointers ("API handlers live in `src/api/handlers/`"). If the tree explains itself, keep this to two or three lines.
4. **Conventions**: only deviations from ecosystem defaults, each with its why. Include the commit-message convention observed in git history.
5. **Boundaries**: always do, ask first, never touch. Mined rules about generated code, migrations and protected paths land here.
6. **Verification**: what the agent runs before it declares work done. Usually a subset of Commands. Make it explicit anyway, because an agent that can validate its own changes is the mechanism behind the quality gain.

Omit entirely: repo-overview prose, anything a configured linter or formatter already enforces, anything derivable by reading the codebase (directory listings, dependency inventories), personas, vague quality demands. One real code example is allowed only when the style deviates from what a model writes by default.

Target 150 lines or fewer. Claude Code's own guidance is under 200 lines per file, because files over 200 lines consume more context and may reduce adherence. If you are over 150, cut Layout and Conventions before Commands and Boundaries.

## Step 4: merge existing instruction files

If the repo already has `AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules/*.md`, or cursor, windsurf or cline rules, Explorer B quotes the rules worth keeping. Migrate commands, real conventions and boundary rules into `AGENTS.md`. Drop personas, linter duplicates, overview prose, and anything that contradicts the explorer findings. A rule that disagrees with current CI is stale, not sacred. List what you dropped and why when you present the draft.

Claude-specific rules stay in the `## Claude Code` section of `CLAUDE.md`, not in `AGENTS.md`. Leave `.claude/rules/*.md` files and `CLAUDE.local.md` as they are: rules load alongside the instruction files, and `CLAUDE.local.md` is the user's own. Leave cursor, windsurf and cline rule files untouched, since other tools may still read them, and tell the user so.

## Step 5: write the files

`AGENTS.md` at the repository root, always.

If step 1 chose the import, or a `CLAUDE.md` or `CLAUDE.local.md` is already on the path, also write `CLAUDE.md` with `@AGENTS.md` as its first line and the Claude-specific rules in a `## Claude Code` section below it. Delete that section when there are none. Exact contents are in `references/template.md`. An existing `CLAUDE.md` with real content: migrate its keep-worthy rules in step 4, then replace its body with this router.

A symlink (`ln -s AGENTS.md CLAUDE.md`) also works when there are no Claude-specific rules. Claude reads through it, but the Edit and Write tools refuse to write through a symlink, and on Windows creating one needs Administrator privileges or Developer Mode. Use the import when anyone on the team works on Windows.

## Step 6: self-check, confirm, write

Before showing the user anything, check the draft:

- It is within the line budget.
- Commands contains only verified or explicitly marked commands.
- None of the omitted content classes crept in.
- The `CLAUDE.md`, if any, holds the import and Claude-specific rules, nothing that belongs in `AGENTS.md`.
- No `CLAUDE.local.md` is created or edited. Adding one to a project that relies on `AGENTS.md` stops Claude reading `AGENTS.md` for you.

Present the draft with a unified diff against any existing instruction files, and get confirmation before writing. Headless: write the files and lead the report with what you wrote and what you dropped.

After writing:

1. Run `vibe-code instruction validate <project dir>`. It audits the `CLAUDE.md` and `.claude/rules` files of that directory: oversized files, formatter and linter leakage, references that do not say when to read them, conflicting commands, rules without `paths`, and an `AGENTS.md` that no `CLAUDE.md` imports. Show the output and fix what it reports.
2. Tell the user how to confirm discovery in a fresh session: `/memory` lists the `AGENTS.md` path Claude read (v2.1.280 or later), and `/context` lists the `CLAUDE.md` files. An `InstructionsLoaded` hook does not fire for an `AGENTS.md` that Claude read directly.
3. Warn the user about `CLAUDE.local.md`: if they add one later for personal notes, Claude stops reading `AGENTS.md` unless a `CLAUDE.md` that imports it exists.

## Notes

- Monorepo: generate the root `AGENTS.md` only. A subdirectory's `AGENTS.md` loads when Claude reads a file there and that subdirectory has no `CLAUDE.md` of its own. Path-scoped rules in `.claude/rules/` with a `paths` field are the other follow-up for per-package instructions. Mention both in your summary.
- Explorers are read-only. All writes happen in step 6, by you, after confirmation.
- If both explorers come back thin (tiny repo, no CI), a 20-line `AGENTS.md` is a success. Never pad.

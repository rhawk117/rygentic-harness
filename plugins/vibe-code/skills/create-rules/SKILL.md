---
name: create-rules
argument-hint: '[rule to enforce]'
description: >-
  Interactive builder for Claude Code rule files (Markdown files under .claude/rules/ with optional paths frontmatter and an XML-sectioned body). Use it to create, add, write or scaffold a rule, a set of coding conventions or a style guide for Claude, or to ask how paths scoping works, even when the user only describes the behavior ("make Claude always do X in these files"). It asks where the rule lives (project or personal), which files it governs, takes the conventions from chat or a file, routes each one away from the file when a linter, hook, skill or CLAUDE.md would do the job better, shows a steering preview and iterates until accepted, then writes a file validated with vibe-code instruction validate and proves Claude Code loads it.
when_to_use: >-
  Use when the user says "add a rule for ...", "write conventions for these files", "make Claude stop doing X in src/", "split my CLAUDE.md", "why does Claude ignore my rule", or asks how .claude/rules, paths globs, CLAUDE.md or AGENTS.md loading work, even without the word "instructions".
---

# Create a Claude Code rule file

The file you produce is loaded into context every time its paths match, for as long as it exists. That makes it cheap to write and expensive to get wrong: a rule a linter already enforces wastes attention on every turn, a rule the user never saw applied steers Claude in ways they did not intend, and a file that quotes today's line numbers is wrong by next week. Claude treats these files as context, not enforced configuration, so the work is mostly deciding which conventions belong in a file at all. The skill walks five phases and writes the file in the last one. Ask every question with the `AskUserQuestion` tool: single select, multi select, or free text through its other option. Anything the user has not said is a question, not an assumption; when they answered upfront, use the answer and say which default you took for anything they did not cover.

| phase         | what happens                                                                          | how the user is involved                                                          |
| ------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| A. Establish  | scope, target files                                                                   | two questions                                                                     |
| B. Understand | scan what already loads and what tooling enforces; collect the conventions            | confirm one numbered list                                                         |
| C. Route      | send each convention to the right home; discourage the file when it is the wrong tool | one table, one decision                                                           |
| D. Steer      | quick per-convention checks, then a code preview, then a review loop                  | questions for everything that needs no code; a Markdown preview only for the code |
| E. Produce    | compose from the accepted conventions, confirm, write, validate, prove it loads       | one confirmation, then results                                                    |

Read `references/instruction-facts.md` once at the start: file locations, load order, `paths` semantics, glob budgets, size limits, imports, `AGENTS.md` loading and the verification commands are there, and a claim outside it is unverified. Read `references/smell-catalog.md` in phase C and whenever a candidate rule feels borderline. Write nothing to the target tree before phase E.

## Phase A: establish

**A1. Scope.** Single select, each with its consequence:

- project: `.claude/rules/**/NAME.md`. Any `.md` file counts and subfolders such as `frontend/` are organisational only. Versioned and shared with everyone who works in the repository.
- personal: `~/.claude/rules/NAME.md`. Applies to every project on this machine, so it must be project-agnostic, and it loads before project rules, so a project rule that conflicts with it appears later in context without overriding it.

Two things the user may ask for are not rule files. Personal preferences for one project belong in `CLAUDE.local.md` (add it to `.gitignore`), which is always-on text: phase C routes it there and phase E5 hands over the lines; this skill does not write it. A plugin does not ship rule files (unverified: the docs list skills, agents, hooks and MCP servers as plugin components and no rules component); guidance that should reach every user of a plugin goes to a skill, or to the `CLAUDE.md` of the repository the plugin is used in.

**A2. Target files.** Ask the user to describe the files in their own words, then propose the `paths` globs and confirm them with a single select between your proposal and one or two plausible alternatives (narrower, wider). State the consequence of each: `**/*.ts` matches any depth, `src/**/*` is a directory, `*.md` matches the project root only, and several patterns are several list entries. A rule without `paths` loads unconditionally at launch, so phase C steers a rule that needs no scoping to `CLAUDE.md` instead. A rule with `paths` loads when Claude uses Read, Write or Edit on a matching file, not at session start and not on every tool use. Brace groups multiply against a budget of 1,000 expanded patterns, and a `[` that is not a valid bracket expression matches nothing; both are spelled out in `references/instruction-facts.md`, and `validate` flags them. After confirming, name three real matching files and one non-matching file so the boundary is visible.

## Phase B: understand

**B1. Scan.** Read what already loads and what tooling enforces:

- existing instruction sources: `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules/**`, `~/.claude/CLAUDE.md`, `~/.claude/rules/**` and `AGENTS.md`, directly with `Read`, `Grep` and `Glob`. Run `vibe-code instruction validate DIR` on the project directory for its audit: oversized files, formatter and linter leakage, references that do not say when to read them, conflicting commands, rules without `paths`, and an `AGENTS.md` that no `CLAUDE.md` imports. Note any file whose scope overlaps the new one; the user may prefer to extend it, and a convention must not contradict one already loaded.
- lint, format and type-check configuration: `pyproject.toml` (ruff, mypy), `ruff.toml`, `.eslintrc*`, `eslint.config.*`, `.prettierrc*`, `biome.json`, `.editorconfig`, `tsconfig.json`, `.golangci.yml`, `.pre-commit-config.yaml`, CI lint steps. Phase C rejects rules these already enforce.
- a handful of files that match the `paths` globs, to learn the language and idioms the preview must use.

When an `AGENTS.md` exists, its loading depends on whether a `CLAUDE.md` or `CLAUDE.local.md` sits in or above the working directory, and on the Claude Code version; `references/instruction-facts.md` has the rules and the `@AGENTS.md` import that shares one file with other tools. Summarise in five lines or fewer.

**B2. Conventions.** Get the rule from the user, never from a repo scan: ask what behavior they want changed. Reading the repo to check a rule the user stated is expected; reading it to invent rules produces files that measurably degrade agents (`references/smell-catalog.md` names the studies). If the user asks for a scan-and-generate pass, say plainly that the evidence points the other way and offer to audit what exists instead. Accept chat text or a path (Markdown, text, an existing instructions file, a style-guide URL via `WebFetch`). Extract every distinct rule into a numbered list, one imperative sentence each, keeping the user's wording where it is already concrete. Confirm the list is complete before routing.

## Phase C: route, and discourage the file when it is the wrong tool

Instructions are advisory prose that costs context on every turn, and Claude may follow either of two conflicting rules. Most candidates belong somewhere else. Walk each one through these gates, first match wins:

1. A linter, formatter or type checker found in B1 already enforces it: drop it and name the tool and config. If the tool is absent, the fix is installing it, not prose. This is the most common smell (`references/smell-catalog.md`).
2. It must hold every time (never commit secrets, never `terraform destroy`, tests pass before done): a hook, because hooks execute as shell commands at fixed lifecycle events and apply regardless of what Claude decides to do. Name the event (`PreToolUse` blocks a command, `PostToolUse` checks after an edit) and offer the `create-hooks` skill, or a hook in `.claude/settings.json`.
3. Claude could learn it by reading the code (layout, dependency list, architecture): drop it.
4. A multi-step procedure needed occasionally (release, migration): a skill; offer `create-skill`.
5. It applies to every file: `CLAUDE.md` or `.claude/CLAUDE.md` for the project, `~/.claude/CLAUDE.md` for the user, `CLAUDE.local.md` for one person in one project. A rule file without `paths` is the topic-split alternative to a long `CLAUDE.md`.
6. Everything else survives as a path-scoped rule.

A convention that matters only to pull request review goes to `REVIEW.md` at the repository root, whichever gate it would otherwise have met.

Show one table: candidate, gate, destination, one-line reason. Then one question: continue with the survivors, or stop. If fewer than two survive, lead with "a rule file is the wrong tool for this request" and list where each rule goes; do not soften it. Survivors must be checkable (imperative, concrete, assertion-shaped: "use 2-space indentation", not "format code properly"); rewrite any that are not and show the rewrite.

## Phase D: steer

The user is here to see how the file will change Claude's output. Most of that can be settled with questions; only code needs a file.

**D1. Quick checks, no file.** For each surviving convention, one question at a time, defaults pre-selected:

- Strength: `must` (Claude stops and asks if it cannot comply), `prefer` (Claude follows unless the surrounding code clearly does otherwise), `avoid` (Claude flags but does not rewrite). This word ends up in the convention's sentence.
- Exceptions: multi-select of plausible carve-outs you infer from the repo (tests, generated code, migrations, scripts, a legacy directory). Chosen carve-outs go into `<scope>`.
- Boundary situations: multi-select of four to six one-line scenarios ("Claude adds a new endpoint", "Claude edits a helper that already violates the rule", "Claude reviews a PR touching only tests") asking which the convention should govern. The answers decide what `<anti_patterns>` says about existing violations and what `<scope>` says it does not cover.
- Negative-test file: single select among the matching files from B1 that appear to violate the convention, so the user picks what gets inspected.

**D2. Code preview, one Markdown file.** Only now write the preview, to a scratch path outside the target tree, never into `.claude/rules/`. It contains, per convention, one before/after pair in the repo's language and idioms, and the negative test: the chosen file with the lines the convention objects to, quoted with `path:line`. Nothing else.

**D3. Review loop.** After showing the preview: accept; a pair is wrong (single select which convention, then free text for the correction); the negative test flags the wrong things (free text); start over from the conventions. On a correction, regenerate the affected pair and re-show the whole preview with a two-line changelog. Repeat until accepted. Keep every accepted answer from D1 and D3; phase E composes from them, not from the preview text.

## Phase E: produce

**E1. Compose** from `assets/instructions.template.md`: frontmatter with `paths` and no other key (Claude Code reads no other field), then XML sections containing Markdown, no root element, placeholders in `UPPER_CASE`, in this order:

- `<scope>`: the `paths` globs in words, plus the D1 carve-outs.
- `<conventions>`: the survivors, numbered, each one sentence carrying its D1 strength word and a short reason. Reasons stop Claude from over-applying; "prefer X because Y" generalises where "always X" does not.
- `<examples>`: at most one pair per convention, trimmed to the lines that show the delta, using generic names rather than the repo's own identifiers unless the identifier is the point.
- `<anti_patterns>`: the patterns, described generically, that the negative test and the D1 boundary answers surfaced. Never cite `path:line` from the repo: those lines will move or be fixed, and the file must stay true.
- `<verification>`: a check Claude runs before finishing (a grep, a command, a question) and a check a reviewer can run.

`<rationale>` may follow `<verification>` when the user wants the reasoning kept. Omit `paths` only for the topic-split case from gate 5. The preview is evidence for the user, not source for the file: do not paste its scenario list, its full snippets or its citations into the file. Keep the body well under 200 lines, use one emphasis marker per file at most, and make every referenced path say what it contains and when to read it.

**E2. Confirm.** Show the complete file and its target path. One question to write; do not write before it.

**E3. Write and validate.** Write the file to `.claude/rules/**/NAME.md` or `~/.claude/rules/NAME.md`, and nowhere else. Run `vibe-code instruction validate FILE`, add `--strict` to fail on warnings, and show the output. It checks the `paths` globs (empty list, match-everything and root-only globs, a leading `/`, an invalid `[`, the brace budget) and the body (the five required sections present and in order, balanced tags, no root wrapper, emphasis count, size). It exits 0 on a pass, 1 on findings and 2 when it could not check; info findings never change the exit code. Fix errors; warnings are judgment calls, so state which you are keeping and why. Then run `vibe-code instruction validate DIR` on the project directory to see the file in the context of the others.

**E4. Prove it loads.** A path-scoped rule loads when Claude uses Read, Write or Edit on a matching file, so have Claude read a matching file first. Then `/context` and the list under **Memory files** show what loaded, and an `InstructionsLoaded` hook logs which files load, when and why; the commands are in `references/instruction-facts.md`. Behavior is a separate check: run the same prompt in a fresh session before and after.

**E5. Hand off.** Deliver:

- the path written;
- the validate output and the discovery result;
- how to open and edit the files, `/memory`, and that a new session loads the file from launch (unverified: the docs snapshot does not say whether a running session picks up a new rule, and describes no per-file toggle);
- the destination of everything routed away in phase C, with the lines to add for `CLAUDE.md`, `CLAUDE.local.md` or `REVIEW.md`, so those rules are not lost;
- everything unverified: any claim above that `references/instruction-facts.md` does not carry.

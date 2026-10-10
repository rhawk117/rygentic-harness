# Claude Code instruction files: facts

Checked on 2026-10-03 against https://code.claude.com/docs/en/memory, https://code.claude.com/docs/en/hooks, https://code.claude.com/docs/en/sub-agents and https://code.claude.com/docs/en/code-review. Versions and limits have moved before; if the date is more than a quarter old, re-check those pages before relying on them. A claim in this skill that this file does not carry is unverified.

## Contents

- Where instruction files live
- Load order and precedence
- Rules directory and `paths`
- Globs, braces and brackets
- Size
- Imports
- AGENTS.md
- Delivery and compliance
- Compaction
- Comments
- Monorepos and exclusions
- Who loads what
- Verification commands
- Review-only instructions

## Where instruction files live

| Layer | Path | Notes |
| ----- | ---- | ----- |
| Managed policy | macOS `/Library/Application Support/ClaudeCode/CLAUDE.md`, Linux and WSL `/etc/claude-code/CLAUDE.md`, Windows `C:\Program Files\ClaudeCode\CLAUDE.md` | Organization-wide. Cannot be excluded. The `claudeMd` key of managed settings holds the same content inline and is honored in managed settings only. |
| Personal, every project | `~/.claude/CLAUDE.md` | |
| Project | `./CLAUDE.md` or `./.claude/CLAUDE.md` | Shared through version control. |
| Project, personal | `./CLAUDE.local.md` | Add it to `.gitignore`. Loads alongside `CLAUDE.md`, appended after it in each directory. A gitignored file exists only in the worktree where it was created. |
| Rules, personal | `~/.claude/rules/<name>.md` | Loaded before project rules. |
| Rules, project | `.claude/rules/**/<name>.md` | One topic per file. |

`CLAUDE.md` and `CLAUDE.local.md` load from the working directory and every directory above it at launch. Files in subdirectories load on demand, when Claude reads a file in that directory.

## Load order and precedence

There is no priority order. All discovered files are concatenated into context rather than overriding each other, from the filesystem root down to the working directory, so the file closest to where Claude started is read last. User-level rules load before project rules, so a project rule appears later in context. If two files conflict, Claude may follow either, so check a new rule against every loaded file, not only the one being edited.

## Rules directory and `paths`

- Place markdown files under `.claude/rules/`. Any `.md` file counts; there is no required suffix. All of them are discovered recursively, and a subdirectory such as `frontend/` is organisational only.
- A rule without a `paths` field loads at launch with the same priority as `.claude/CLAUDE.md`, and applies to all files.
- A rule with `paths` loads when Claude uses the Read, Write or Edit tool on a file that matches, not at session start and not on every tool use.
- `paths` is the only field Claude Code reads from a rule; any other field is ignored without an error. It accepts a YAML list or a comma-separated string. Claude Code removes the frontmatter before loading the rule.
- If the YAML between the markers does not parse, Claude Code ignores the frontmatter and loads the rule as if it had no `paths`. `claude --debug` shows the parse error.
- `.claude/rules/` supports symlinks. A symlink whose target is outside the working directory is treated like an external import: the linked rules do not load until external imports are approved for the project, and then only those without `paths` load.

## Globs, braces and brackets

| Pattern | Matches |
| ------- | ------- |
| `**/*.ts` | All TypeScript files in any directory |
| `src/**/*` | All files under `src/` |
| `*.md` | Markdown files in the project root only |
| `src/components/*.tsx` | React components in one directory |

- Brace expansion works: `src/**/*.{ts,tsx}` is two patterns.
- Each brace group multiplies: `src/*.{ts,tsx}` expands to two patterns and `{a,b}/{c,d}/*.{ts,tsx}` to eight. A rule's whole `paths` list shares one budget of 1,000 expanded patterns and 4 MiB, and patterns without braces do not count against it. A pattern that would exceed the budget is used unexpanded, and its literal braces match no files. `vibe-code instruction validate` errors over the 1,000 patterns; it does not check the 4 MiB half.
- `[` starts a bracket expression. A pattern with a `[` that cannot be read as one, such as `photos [2024/**`, is invalid and matches nothing, while the rule's other patterns keep working. Escape a literal one as `photos \[2024/**`. `validate` warns on an unescaped invalid `[`.

## Size

Target under 200 lines per CLAUDE.md file; longer files consume more context and reduce adherence. Claude Code loads a CLAUDE.md file of up to 4 MiB in full and skips a larger file. When a file passes the recommended length, Claude Code warns at startup and in `/status`; each CLAUDE.md, rules file and `@path` import counts as a file toward a combined limit. `/doctor` proposes trims for a checked-in CLAUDE.md (v2.1.206 or later): it cuts what Claude can derive from the codebase, such as directory layouts, dependency lists and architecture overviews, and keeps pitfalls, rationale and conventions that differ from tool defaults.

## Imports

`@path/to/file` in a CLAUDE.md expands at launch alongside the file that names it, so an import organises a long file but does not reduce its context cost. Relative paths resolve against the file containing the import, not the working directory. Imports can recurse to a maximum depth of four hops. Import parsing skips Markdown code spans and fenced blocks, so wrap a path in backticks to mention it without importing it. A path with spaces needs a backslash before each space; a quoted path is not imported.

An import of a file outside the working directory in a project-level memory file shows a one-time approval dialog; declining leaves those imports disabled. User-scope files such as `~/.claude/CLAUDE.md` and `~/.claude/rules/` load their imports without the dialog.

## AGENTS.md

Reading `AGENTS.md` directly requires Claude Code v2.1.277 or later. By default Claude reads it only when no `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` exists in the working directory or any directory above it. With one of those present, Claude reads the `CLAUDE.md` files only, unless a `CLAUDE.md` imports `AGENTS.md` or the **Project instructions** setting in `/config` says otherwise (`claude-md-and-agents-md` reads both). `~/.claude/CLAUDE.md`, the managed `CLAUDE.md` and `.claude/rules/` files do not count for that check. Adding a `CLAUDE.local.md` to a project that relies on `AGENTS.md` therefore stops Claude from reading `AGENTS.md`.

Sessions before v2.1.277, and some sessions before v2.1.281 (Amazon Bedrock, telemetry disabled), read `CLAUDE.md` files only. To share one `AGENTS.md` with other tools in any of those cases, or when a `CLAUDE.md` exists, put `@AGENTS.md` in a `CLAUDE.md` next to it and the Claude-specific lines below the import. A symlink (`ln -s AGENTS.md CLAUDE.md`) also works, but the Edit and Write tools refuse to write through it, and on Windows creating one needs Administrator privileges or Developer Mode and Git may check it out as a plain text file, so use the import there. Keeping the import never makes Claude read `AGENTS.md` twice.

## Delivery and compliance

CLAUDE.md content is delivered as a user message after the system prompt, not as part of the system prompt. There is no guarantee of strict compliance, especially for vague or conflicting instructions. Instructions that must hold at one point, such as before every commit, belong in a hook. For the system prompt level, `--append-system-prompt` works at launch and suits scripts more than interactive use.

## Compaction

Project-root CLAUDE.md survives `/compact`: Claude re-reads it from disk and re-injects it. Nested CLAUDE.md files in subdirectories and rules with `paths` reload as Claude reads files they apply to, so an instruction that seems lost after compaction may live in one of those or have been given only in conversation.

## Comments

Block-level HTML comments in CLAUDE.md files are stripped before the content is injected into context, so they carry notes for human maintainers at no token cost. Comments inside code blocks are preserved. The docs state this for CLAUDE.md only; whether a rule file gets the same stripping is not stated, so do not put a note a rule needs in a comment.

## Monorepos and exclusions

`claudeMdExcludes` in settings lists glob patterns matched against absolute file paths; user, project, local and managed layers all apply and arrays merge across them. It can skip ancestor CLAUDE.md files and rules directories from other teams. Managed policy CLAUDE.md files cannot be excluded.

## Who loads what

- Every custom subagent loads the CLAUDE.md files, unless its definition sets `omitClaudeMd`, which skips the user, project and local files (managed policy files still load). The built-in Explore and Plan agents skip them.
- `--add-dir` directories do not load their CLAUDE.md files by default. Set `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` to load `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/*.md` and `CLAUDE.local.md` from them.
- `--bare` skips auto-discovery including CLAUDE.md, and `--safe-mode` starts with CLAUDE.md and other customizations disabled.

## Verification commands

| Goal | Command |
| ---- | ------- |
| What loaded | `/context`, then the list under **Memory files** |
| Open and edit the files | `/memory` |
| Log which files load, when and why | `InstructionsLoaded` hook; its load reasons are `session_start`, `nested_traversal`, `path_glob_match`, `include` and `compact`. Its exit code is ignored. |
| Propose trims | `/doctor` |
| Audit for outdated or conflicting instructions | `/doctor prompt-audit` (v2.1.283 or later) |
| Generate a starting file | `/init` |

## Review-only instructions

`REVIEW.md` at the repository root holds instructions for Claude Code Review only; the agents that find and verify findings receive it. `CLAUDE.md` is also read by Code Review as project context, and applies to all tasks. Keep a convention that matters only to review out of `CLAUDE.md` and rules.

# Platform matrix

Everything here is from official Anthropic and GitHub documentation as of August 2026.
Verify against the live docs if a behavior looks wrong; both products ship weekly.

## Contents

- [Layer mapping](#layer-mapping)
- [Claude Code](#claude-code)
- [GitHub Copilot](#github-copilot)
- [Agent Skills](#agent-skills)
- [Sharing rules between the two tools](#sharing-rules-between-the-two-tools)
- [Verification commands](#verification-commands)

## Layer mapping

| Layer | Claude Code | GitHub Copilot |
|---|---|---|
| Always-on, repo-wide | `CLAUDE.md` or `.claude/CLAUDE.md` | `.github/copilot-instructions.md` |
| Always-on, personal | `~/.claude/CLAUDE.md` | `~/.copilot/copilot-instructions.md` (CLI) |
| Always-on, local uncommitted | `CLAUDE.local.md` | none |
| Path-scoped | `.claude/rules/*.md` with `paths:` | `.github/instructions/**/*.instructions.md` with `applyTo:` |
| Path-scoped, personal | `~/.claude/rules/*.md` | `~/.copilot/instructions/**/*.instructions.md` |
| On-demand | `.claude/skills/*/SKILL.md` | `.github/skills`, `.claude/skills`, `.agents/skills` |
| Cross-tool agent file | not read natively | `AGENTS.md` read natively |
| Org-wide | managed policy `CLAUDE.md` | organization instructions |

## Claude Code

**Load order**, broadest first, concatenated rather than overridden: managed policy →
`~/.claude/CLAUDE.md` → `./CLAUDE.md` or `./.claude/CLAUDE.md` → `./CLAUDE.local.md`.
Ancestor directories load at launch. Subdirectory files load on demand when Claude reads files
in those directories.

**Managed policy paths**: macOS `/Library/Application Support/ClaudeCode/CLAUDE.md`, Linux and
WSL `/etc/claude-code/CLAUDE.md`, Windows `C:\Program Files\ClaudeCode\CLAUDE.md`. Cannot be
excluded by user settings. The `claudeMd` key in `managed-settings.json` is an inline
alternative.

**Size**: target under 200 lines. Files above 4 MiB are skipped entirely.

**Imports**: `@path/to/file` expands at launch, so imports do not reduce context. Max depth 4
hops. Relative paths resolve against the file containing the import, not the working directory.
Import parsing skips code spans and fenced blocks, so backtick a path to mention it literally.
Imports resolving outside the working directory trigger a one-time approval dialog.

**Rules**: `.claude/rules/` is discovered recursively and supports symlinks, including to a
shared directory outside the repo. Rules without `paths:` load unconditionally at the same
priority as `.claude/CLAUDE.md`. `~/.claude/rules/` loads before project rules.

**Glob budget** for `paths:`: 1,000 expanded patterns and 4 MiB per rule. Brace groups multiply,
so `{a,b}/{c,d}/*.{ts,tsx}` expands to eight. Patterns exceeding the budget are used unexpanded
and match nothing. An unparseable `[` matches nothing; escape it as `\[`.

**Delivery**: CLAUDE.md arrives as a user message after the system prompt, not as system prompt.
There is no compliance guarantee. `--append-system-prompt` is the system-prompt-level escape
hatch but must be passed on every invocation.

**Compaction**: project-root CLAUDE.md is re-read from disk after `/compact`. Nested files and
path-scoped rules reload only when a matching file is touched again.

**Monorepos**: `claudeMdExcludes` takes glob patterns matched against absolute paths and merges
across settings layers. Managed policy files cannot be excluded.

**Free space**: block-level HTML comments are stripped before injection, so maintainer notes in
`<!-- -->` cost nothing.

## GitHub Copilot

**Files**: `.github/copilot-instructions.md` repo-wide;
`.github/instructions/**/*.instructions.md` path-scoped with `applyTo` frontmatter (glob string
or list); `AGENTS.md` for agent instructions. CLI personal files live at
`~/.copilot/copilot-instructions.md` and `~/.copilot/instructions/**/*.instructions.md`, with
`COPILOT_HOME` overriding `$HOME/.copilot`.

**Size**: roughly 1,000 lines per file is the documented ceiling before response quality
degrades. Treat 200 as the practical target for the same reasons as Claude Code.

**Precedence**: on GitHub.com Chat, personal beats repository beats organization. Copilot CLI
explicitly does **not** define a general precedence order across user-level, repo-wide, and
agent instructions - it combines them and removes duplicate copies of identical files.

**Support varies sharply by surface.** Do not assume uniformity:

| Surface | Repo-wide | Path-scoped | AGENTS.md | Personal |
|---|---|---|---|---|
| GitHub.com Chat | yes | no | no | yes |
| Cloud agent | yes | yes | yes | no |
| Copilot code review | yes | yes | yes | no |
| VS Code Chat | yes | yes | yes | no |
| VS Code code review | yes | no | no | no |
| Visual Studio Chat | yes | yes | no | no |
| JetBrains Chat | yes | yes | no | yes |
| Eclipse Chat | yes | no | no | no |
| Eclipse code review | none | none | none | none |
| Xcode Chat | yes | yes | no | no |
| Copilot CLI | yes | yes | yes | yes |

**Documented as unsupported** - do not write these, they add noise without effect: changing
comment formatting or emoji, modifying the PR overview comment, blocking merges, following
external links (copy the content in instead), and vague quality directives like "be more
accurate" or "don't miss any issues".

**Testing advantage**: Copilot code review reads instructions, agent instructions, and skills
from the **head branch**, so an instruction change can be validated in the same pull request
that introduces it, before merge.

**Includes**: in `.github/copilot-instructions.md`, `AGENTS.md`, or `CLAUDE.md`, an `@` followed
by a relative path pulls in another file, recursively.

## Agent Skills

An open standard, originally from Anthropic, now multi-vendor. A skill is a directory with a
`SKILL.md` carrying at minimum `name` and `description` frontmatter, plus optional `scripts/`,
`references/`, and `assets/`.

Loading is three-stage: name and description at startup, full `SKILL.md` on activation, bundled
files on demand.

Copilot's project skill paths include `.claude/skills`, so **a skill placed at
`.claude/skills/<name>/SKILL.md` is read by both tools without duplication.** This is the only
layer where a single artifact genuinely serves both.

## Sharing rules between the two tools

Recommended topology when both tools are in play:

- `AGENTS.md` holds the always-on rules. Copilot reads it natively.
- `CLAUDE.md` contains `@AGENTS.md`, plus any Claude-Code-only lines below the import.
- Path-scoped rules are written as a matched pair and drift-checked in CI.
- Skills live in `.claude/skills/` and serve both.

Known rough edge: Copilot CLI discovers both `AGENTS.md` and `CLAUDE.md` and resolves `@`
includes inside them. With the import pattern, AGENTS.md content may be presented twice. The
docs say identical copies are deduplicated but do not state whether that covers
include-resolved content. Confirm with `/instructions` in the target repo before relying on it.

The alternative is a symlink from `CLAUDE.md` to `AGENTS.md`, which avoids the double-load
question but requires Administrator or Developer Mode on Windows.

## Verification commands

| Goal | Claude Code | Copilot |
|---|---|---|
| What actually loaded | `/context` | `/instructions` (CLI); References list in IDE chat |
| Open and edit memory files | `/memory` | `/instructions` (CLI) |
| Programmatic load log | `InstructionsLoaded` hook | not available |
| Propose trims | `/doctor` | not available |
| Generate a starting file | `/init` | Copilot can draft one on request |

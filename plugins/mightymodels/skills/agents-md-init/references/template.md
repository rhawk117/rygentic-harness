# Output templates

## AGENTS.md skeleton

Sections in this order. Delete any section with nothing real to say — never pad. Target ≤150 lines total.

```markdown
# <repo-name> — agent instructions

## Commands
<!-- verified only; prefix "(unverified)" where applicable; include flags -->
- Test: `uv run pytest -q`
- Lint: `uv run ruff check src tests`
- Typecheck: `uv run ty check src`
- Build: ...
- Run: ...

## Stack
<!-- exact versions and tools, one line each: "Python 3.12, uv, ruff, pytest" -->

## Layout
<!-- only non-obvious pointers: "API handlers live in src/api/handlers/" -->

## Conventions
<!-- only deviations from ecosystem defaults, each with its why -->
<!-- include the observed commit convention: "Conventional commits (feat/fix/chore), scope optional — matches git history" -->

## Boundaries
- Always: <e.g. run the Verification commands before finishing>
- Ask first: <e.g. dependency changes, schema migrations>
- Never: <e.g. edit src/*/generated/ — regenerate with `make codegen`>

## Verification
<!-- the exact commands an agent runs before declaring work done -->
```

A code example section is allowed only when observed style genuinely deviates from what a model produces by default — one real snippet from the repo, not an invented one.

## CLAUDE.md router (Claude Code)

```markdown
@AGENTS.md

## Claude Code
<!-- Claude-specific rules only (e.g. "use plan mode for changes under src/billing/").
     Delete this section if there are none. -->
```

The `@AGENTS.md` import is the vendor-official bridge — Claude Code reads CLAUDE.md, not AGENTS.md, and loads the import at session start. Prefer the import over a symlink: it works on Windows without elevation and allows Claude-specific additions below it.

## .github/copilot-instructions.md router (Copilot)

```markdown
Repository instructions live in [AGENTS.md](../AGENTS.md) at the repo root. Read
and follow that file — it is the single source of truth for this repository.

This pointer exists for Copilot surfaces that do not load AGENTS.md automatically
(github.com Chat; JetBrains, Visual Studio, Xcode, and Eclipse chat). Copilot's
agent surfaces (cloud agent, CLI, VS Code, code review) read AGENTS.md natively.
```

Keep it a pointer. Copilot combines copilot-instructions.md and AGENTS.md additively on agent surfaces, so any rule duplicated here will drift from the canonical copy. If the user explicitly wants chat-surface coverage without a file-read hop, mirror at most the Commands section and add a comment naming AGENTS.md as canonical — but offer that trade-off, don't default to it.

## Merge guidance (existing instruction files)

| From existing files | Disposition |
| --- | --- |
| Commands, validation steps | Migrate to AGENTS.md `## Commands` / `## Verification`; reconcile against explorer findings — CI wins conflicts |
| Real conventions, boundary rules ("never touch X", "ask before Y") | Migrate to `## Conventions` / `## Boundaries` |
| Platform-specific rules (plan-mode habits, tool quirks) | Keep in that platform's router file |
| Personas, overview prose, linter duplicates, stale facts | Drop — list each dropped item and its reason when presenting the draft |

Existing CLAUDE.md with real content: migrate its keep-worthy rules, then replace the file body with the router (import first line). Existing cursor/windsurf/cline rules: mine them but leave the files untouched — other tools may still read them; note that to the user.

---
name: writing-agent-rules
license: Apache-2.0
description: Create, place, and audit coding-agent instruction and rule files across Claude Code and GitHub Copilot - CLAUDE.md, AGENTS.md, .claude/rules/, .github/copilot-instructions.md, and .github/instructions/*.instructions.md. Use this skill whenever the user wants to add a rule or convention for a coding agent, set up or clean up agent instructions in a repo, share rules between Claude Code and Copilot, split an oversized instructions file, or asks why an agent keeps ignoring a rule. Use it even when the user only describes the behavior they want ("make Copilot stop using default exports", "Claude keeps forgetting to run migrations") without naming any file.
---

# Writing agent rules and instructions

Most instruction files fail for a reason that has nothing to do with how they are written.
A 2026 study of 100 popular repositories found 91 of them carried at least one configuration
smell, and controlled experiments found that context files raise inference cost by over 20%
without improving task success, because agents over-comply: every line becomes another
constraint to satisfy. A tool merely named in a context file was invoked 160 times more often.

So the job here is not to write good markdown. It is to decide, for each rule, whether it
belongs in a file at all - and if it does, which of the four possible files, in two different
tools, with two different frontmatter schemas.

Work in this order. Do not skip step 1; writing a rule the user did not ask for is the single
most damaging thing this skill can do.

## 1. Get the rule from the user, never from a repo scan

Ask what behavior they want changed. Scanning a codebase and inventing rules from it produces
files that measurably degrade agent performance - this is the documented failure mode behind
both LLM-generated context files and the `/init`-and-never-touch-again pattern.

Reading the repo to *check* a rule the user stated is good and expected. Reading the repo to
*generate* rules is not. If the user asks for a scan-and-generate pass, say plainly that the
evidence points the other way, then offer the audit path instead (step 6).

Get enough to route the rule:

- What should the agent do or stop doing?
- Does it apply everywhere, or only to certain paths or languages?
- Must it hold every single time, or is it a strong default?
- Which tools are in play - Claude Code, Copilot, or both?

## 2. Detect the layout before writing anything

Never assume a repo shape. Run:

```bash
python scripts/audit_rules.py <repo-root> --json
```

The `layout` block in the output tells you which files exist, which tool reads each one, and
whether an `AGENTS.md` is currently invisible to Claude Code. Adapt to what is there rather
than imposing a preferred structure. If the repo has nothing yet, propose a topology from
`references/platform-matrix.md` and let the user pick.

## 3. Route the rule before drafting it

Walk these gates in order. The first one that matches decides the destination. Most candidate
rules die before gate 6, and that is the point.

| Gate | Question | If yes |
|---|---|---|
| 1 | Is a linter, formatter, or type checker already enforcing this? | Delete the rule. Add the tool to the build if it is missing. This is the most common smell in the wild, at 62% prevalence. |
| 2 | Must it hold every time, with no exceptions? | Write a hook, not prose. Instruction files are advisory context; hooks are deterministic. Compliance also decays within a session - median first omission is around the fourth generated function - so a prose rule will not survive a long run. |
| 3 | Could the agent work this out by reading the code? | Delete it. Architecture overviews, directory layouts, and dependency lists all fail this gate. |
| 4 | Does it apply only to certain paths or file types? | Path-scoped rule. Generate the matched pair - see step 5. |
| 5 | Is it a multi-step procedure needed only occasionally? | Its own skill, loaded on demand. Testing, workflow, and scaffolding procedures are the most frequently misplaced. |
| 6 | Everything else | Always-on file. Keep it short. |

Tell the user which gate caught their rule and why. A user who wanted a CLAUDE.md line and got
a hook instead deserves the reasoning, and the reasoning is what stops them re-adding it later.

## 4. Write the rule so it can be checked

Rules that survive to a file follow four constraints:

- **Imperative and concrete.** "Use 2-space indentation" not "format code properly". The test is
  whether you could write an assertion for it.
- **One emphasis marker per file, at most.** Marking one line IMPORTANT works. Marking six means
  none of them stands out.
- **Every reference pitched.** A bare path gets ignored. State what the file contains and when to
  read it: "See `docs/auth-flow.md` for the token refresh sequence when touching session code."
- **No contradictions.** Check the new rule against what is already in every loaded file, not just
  the one you are editing. Conflicting instructions co-occur with bloat at high confidence.

Templates are in `assets/`. Use them rather than inventing structure.

## 5. Place it, and pair it when scoped

Read `references/platform-matrix.md` for exact paths, load order, size limits, and per-surface
support before writing. Two facts trip people up constantly:

- Claude Code does not read `AGENTS.md`. It needs a `CLAUDE.md` containing `@AGENTS.md`, or a
  symlink. Copilot reads `AGENTS.md` natively.
- `@path` imports load at launch and save no context at all. Splitting a file into imports is an
  organizational move, not a cost saving.

Path-scoped rules have **no shared format**. Claude Code uses `.claude/rules/*.md` with a `paths:`
list; Copilot uses `.github/instructions/*.instructions.md` with `applyTo:`. There is no single
file both read. When a rule is path-scoped and both tools are in play, write both from one
intent and note in each file that the pair exists, so the next person updates both.

## 6. Verify - writing the file is not the finish line

Three checks, in increasing cost:

1. **Did it load?** `/context` in Claude Code lists loaded memory files. `/instructions` in
   Copilot CLI lists discovered instruction files and lets you toggle them. If the file is not
   listed, nothing else matters.
2. **Does the repo still smell clean?** Re-run `scripts/audit_rules.py <repo-root>`. It exits
   non-zero on errors. Wire it into CI if the user wants the drift caught automatically.
3. **Did behavior change?** For Copilot, code review reads instructions from the head branch, so
   an instruction change can be tested in the very PR that introduces it - the cheapest real
   experiment available on either platform. For Claude Code, run the same prompt in a fresh
   session before and after.

Report what you verified. "I added the rule" is not a result; "the rule loads, the audit is
clean, and the agent used the new pattern on a fresh run" is.

## Bundled resources

- `references/platform-matrix.md` - exact file paths, load order, precedence, size limits, and
  the per-surface support table. Read this before writing to any file, every time; the support
  gaps between VS Code, JetBrains, Eclipse, and the CLI are not guessable.
- `references/smell-catalog.md` - the six configuration smells with prevalence, detection
  questions, and before/after rewrites. Read this when auditing or when a rule feels borderline.
- `assets/` - templates for each of the four file types, with correct frontmatter.
- `scripts/audit_rules.py` - layout detection and smell linting. Run with `--json` for structured
  output, `--no-fail` to report without a non-zero exit.

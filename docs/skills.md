# Skills

Twenty skills ship with the plugin: ten loop stages, a three-skill review stack, the
using-mightmodels fleet reference, and five standalone utilities. Each is a directory under
`skills/` with a `SKILL.md` whose frontmatter carries only `name` and `description` (plus
`license` or harness-specific keys where needed), so the same files load in Copilot CLI and
Claude Code.

Two things decide when a skill fires. You can always invoke one explicitly with a slash,
`/agents-assemble` or `/prune-ticket`, in either harness. Otherwise the harness selects from your
prompt and the skill's description, which makes the description the retrieval surface: every
description in this repo names its trigger phrases and its boundaries, and the eval datasets
include near-miss prompts (a Jira sprint question must not trigger `agents-assemble`) to keep that
selection honest.

## The loop skills

`lets-investigate` opens a chat-first triage session on a problem, claim, or unexplained
behavior. The primary delegates retrieval to scouts, one narrow question each, and accumulates
cited facts in the conversation. It fires at the start of work, before any ticket exists, and
ends by offering `what-we-know`.

`what-we-know` consolidates understanding: a table of knowns with file:line citations,
enumerated uncertainties resolved through the ask-user dialog, and a SWOT-level analysis. Inside
an active sprint it runs in a second mode that gathers citations for the current task only and
never asks the user anything.

`prepare-handoff` bridges from understood problem to startable ticket through a five-question
interview, then creates the ticket directory, `ticket.yml` with derived model routing, the
optional GitHub issue with humanizer-cleaned prose, the branch, and a thin `handoffs/SPRINT.md`.

`inline-sendoff` is the small-scope ramp. It reads `ticket.yml` and the issue first, reconfirms
the ticket's claims at HEAD with two or three scouts, writes the task checklist into the issue
body, and hands control to `agents-assemble`. It auto-invokes at session start when the active
ticket says `scope: sm` and `plan-first: false`.

`formulate-plan` is the large-scope ramp. Same verification first, then it writes
`.mightymodels/<slug>/plan.md`, high-level strategy and enumerated tasks with size hints,
deliberately free of code-level citations, and gets the user's approval before invoking
`agents-assemble`. It auto-invokes for every scope/plan-first combination other than `sm` with
`plan-first: false`; the routing table in [docs/workflow.md](workflow.md) is canonical.

`agents-assemble` runs the per-task work loop: fresh citations, a promptlint-templated engineer
dispatch carrying an ASKED stanza with checkable acceptance criteria, the two-half task brief,
scout verification of DONE against ASKED, `budgetron` for residuals, and `whats-broken`
after repeated failures. It ends in a REPORT.md of at most 50 lines.

`finish-assembly` closes the sprint: push, `gitty-up` opens the PR from the repo's template and
watches CI, failures route by the log-tail test (mechanical fixes to `budgetron`,
unclear causes to `whats-broken`), and on green it offers the thin `handoffs/REVIEW.md`.

`review-circus` runs the endgame review on a ticket, a branch, or the whole codebase: scouts
triage the surface, `uncle-bob` and `merge-vader` run in parallel with models from `ticket.yml`,
reports land under `.mightymodels/<slug>/review/`, findings are deduped and severity-unified
through the shared table, and an abridged comment is always posted to the PR, pass or fail.
Worth-fixing triage routes by risk first (Critical findings and High+ security findings go to
an engineer regardless of source), then by source: remaining uncle-bob findings to an engineer,
remaining merge-vader findings to `budgetron`.

`ask-an-adult` escalates a genuinely undecidable judgment call to `wingman`, a tool-less
reasoning advisor, and carries its questions to the user before work resumes. `dialectic` runs
`grumpy` and `sunny` independently and in parallel against one falsifiable proposition, then
records the adjudicated position. Use these for reasoning, not for facts a scout can retrieve.

`whats-broken` is the debugging protocol: reproduce, gather evidence with scouts (no fixes
proposed during the evidence phase), one named falsifiable hypothesis at a time written to the
ticket's `whats-broken.md`, a minimal hypothesis test, then the fix through a normal engineer
dispatch with a regression test. A hard three-strike breaker stops and escalates instead of
attempting a fourth patch.

`prune-ticket` closes out a finished unit of work: a 30-line archive at
`.mightymodels/archives/<slug>.md`, cascading documentation updates proposed as diffs, then
deletion of the ticket directory. It refuses while live work remains.

## The review stack

`uncle-bob` grades a codebase against Robert C. Martin's published principles: SOLID, the Clean
Code rules and smells catalog, and the Clean Architecture component metrics (dependency cycles,
instability, abstractness, distance from the main sequence). It produces `UNCLE-BOB-REPORT.md`
with letter grades and severity-ranked findings. Its `Blocker` maps to `Critical` in the shared
severity table.

`merge-vader` is the adversarial pre-merge review of a feature branch: code quality, security,
SDLC regressions (weakened tests, CI, or tooling gates), documentation drift, and plan
conformance when a plan or issue is supplied. It coordinates scouts for facts beyond the diff
and ends in a gated verdict, `BLOCK`, `MERGE WITH CONDITIONS`, or `CLEAR`. `CLEAR` is impossible
while any security-relevant question sits `UNKNOWN-BLOCKED`.

`thermo-nuclear-code-quality-review` is the deliberately harsh maintainability audit for
abstraction quality, giant files, and spaghetti-condition growth. Reach for it when a normal
review keeps waving things through.

## The fleet reference

`using-mightmodels` is the orientation skill for the mightymodels, mightymodels's worker fleet. It
answers the routing questions a primary faces at dispatch time: which worker for which job, what
each one refuses to do, what a dispatch must contain, and how model selection resolves between
`ticket.yml` and the agent-file pins. Consult it when asking "which agent should handle this",
"what agents are available", or before the first dispatch of a session. Its creation smoke eval
caught the exact failure it exists to prevent: without it, a capable baseline routed per-task
verification to merge-vader and guessed from the name that budgetron "only scaffolds".

## Utilities

`promptlint` turns a rough task description into a production-quality prompt for a coding agent,
applying Anthropic's prompt-engineering practices. Inside the loop it supplies the dispatch
templates, including the engineer template that emits the ASKED stanza.

`humanizer` removes signs of AI-generated writing, based on Wikipedia's "Signs of AI writing"
catalog. `prepare-handoff` runs issue prose through it; this documentation was written under it.

`jira` manages Jira issues, epics, sprints, boards, and JQL queries through `jira-cli`. Its
description is one half of the trigger collision pair the eval datasets guard: sprint words
alone must not pull in `agents-assemble`.

`hooksmith` analyzes a repository and designs, plans, and implements GitHub Copilot hooks that
pay off for that specific repo, driven by its CI workflows, lint and type configs, and
fresh-session context needs.

`agents-md-init` generates an evidence-based AGENTS.md by dispatching two explorer subagents,
then wires the per-platform router files: `CLAUDE.md` as an `@AGENTS.md` import and
`.github/copilot-instructions.md` as a pointer.

## Editing a skill

Every skill edit ships with a re-run of its evals and a new dated result, or it does not ship.
The per-skill datasets live in `evals/datasets/<skill>/`; [CONTRIBUTING.md](../CONTRIBUTING.md)
walks through the gate.

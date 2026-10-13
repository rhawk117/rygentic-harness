# Skills

Nineteen skills ship with the plugin: twelve loop stages, three escalation and debugging skills,
the two reviewer doctrines, the `prompting-subagents` fleet reference, and one standalone
utility. Each is a directory under `plugins/mightymodels/skills/` with a `SKILL.md` whose
frontmatter carries `name`, `description` and `when_to_use`, plus `argument-hint`,
`allowed-tools`, `user-invocable` and `disable-model-invocation` where a skill needs them.

Two things decide when a skill fires. You can invoke most of them explicitly with a slash,
`/agents-assemble` or `/prune-ticket`. Otherwise Claude Code selects from your prompt and the
skill's description, which makes the description the retrieval surface: every description in
this repo names its trigger phrases and its boundaries, so that near-miss prompts (a
sprint-board question must not trigger `agents-assemble`) stay out. Three skills run only when
you start them: `stick-the-landing`, `prune-ticket` and `crashout`. Four are never invoked by
hand, because a worker or the primary loads them: `agent-debugging`, `becoming-uncle-bob`,
`becoming-merge-vader` and `prompting-subagents`.

## The loop skills

`lets-investigate` opens a chat-first investigation of a problem, claim, or unexplained
behavior. The primary sends code-scout and web-scout one narrow question each and folds every
report into a ledger that is restated in chat and saved in the state database. Each round stops
at a gate where you choose to dig further, redirect, stop, or consolidate through
`what-we-know`. It fires at the start of work, before any ticket exists.

`what-we-know` consolidates understanding: a table of knowns with file:line or URL citations,
enumerated uncertainties resolved through the ask-user dialog, and an analysis shaped by the
question. Inside an active sprint it runs in a second mode that gathers citations and the files
in scope for the current task only and never asks the user anything.

`open-ticket` turns an understood problem into a staged ticket. One interview asks for the slug
and the tracker (GitHub, Jira, both or none), and the `ticket` tool asks for the scope, the
branch and whether a compaction is expected. It creates the ticket directory, a findings rollup,
the issue or a local draft with a checked body, the branch, and `ticket.yml` with derived model
routing, then validates the ticket into the state database. It ends by asking whether to plan
now (`game-plan`), go straight to `one-shot`, or hand off (`baton-pass`).

`one-shot` is the fast ramp. From an active ticket, a pasted issue, or a task described in chat,
it asks in one dialog whatever `open-ticket` would have asked that the context has not answered,
stages the ticket when none exists, reconfirms the claims at HEAD with two or three scouts,
writes the task list with a checkable acceptance criterion per task, and gets its commands
approved into the verification contract before it hands control to `agents-assemble`. It
assumes no compaction and writes no plan or handoff file. It auto-invokes at session start when
the active ticket says `scope: sm` and `plan-first: false`, and runs explicitly on any scope
after an ask-user confirmation on med or large.

`cross-examine` interviews the user about a plan, design, or decision at a depth the user
picks first (Skim, Standard, or Relentless), working the design tree in rounds through the
ask-user dialog: facts go to scouts, decisions go to the user, and a decisions record is
restated after every round. `game-plan` runs it between claim verification and drafting; it
also runs standalone for "grill me" or "stress-test this design".

`game-plan` is the large-scope ramp. Scouts verify the ticket's claims while `terry-toolchain`
surveys the environment, and the survey is saved as `toolchain.md` in the ticket directory.
Then comes `cross-examine`, and then `.mightymodels/<slug>/plan.md` as a compaction-safe ledger:
invariants with proving commands, dependency-ordered tasks each with a size, deterministic
acceptance criteria and verify commands, non-goals, and risks with the user's chosen handling,
free of code-level citations. Every verification command goes into a user-approved contract and
runs at HEAD before approval. One dialog question asks who answers a blocked task, and only the
answer "escalate automatically" writes `auto-escalate: true` into `ticket.yml`. It gets the
user's approval before invoking `agents-assemble`. It auto-invokes for every scope/plan-first
combination other than `sm` with `plan-first: false`; the routing table in
[docs/workflow.md](workflow.md) is canonical.

`break-it-down` splits one task that is too large into tasks of one reviewable unit each. It
runs when the `task` tool's `start` refuses a task for more than four acceptance criteria or
more than ten owned files, when an engineer or architect returns `too-large` with its cuts, or
when you ask for a split. It shows every piece (id, intent, acceptance, owned files) in one
dialog and changes nothing before you answer; only then is the original task superseded and the
plan updated. You may also keep the task whole, and `start` then accepts it as approved by you.

`agents-assemble` runs the per-task work loop: fresh citations, the two-half task brief with an
ASKED stanza of checkable acceptance criteria, a `task` `start` and a dispatch of the engineer
(or the intern for a `tiny` task), the contract commands at the new HEAD, the fact-checker on
DONE against ASKED, and the `task` tool's `verify` as the gate. A bounded miss becomes an
engineer residual under an `R<n>` task. A blocked or failed task goes to you before the
architect unless the ticket has `auto-escalate` on, and to `whats-broken` when the architect
fails too. It ends in a REPORT.md of at most 50 lines and never pushes.

`stick-the-landing` closes the sprint, and only you can start it. It gates on the `task` tool's
`ready` action, pushes, opens the PR from the repo's template with a checked body, and has
`gitty-up` watch CI. Each failing check becomes a recorded `C<n>` task routed by the log-tail
test (mechanical fixes to an engineer residual, unclear causes to `whats-broken`), and the whole
contract is proven again at every new HEAD before a re-push. On green it asks whether to review
now or hand off.

`review-circus` runs the endgame review on a diff, a branch, a ticket, or the whole codebase.
One gate sets depth, emphasis and scope, the `review` tool records the run, and `uncle-bob` and
`merge-vader` run in parallel on the models the run recorded. Reports land in the run's
directory under `.mightymodels/<slug>/review/`, overlapping findings are merged and
severity-unified through the shared table, and an abridged comment is always posted to the PR,
pass or fail. Only the findings you pick are fixed, risk first, each as an `R<n>` task: Critical
findings and High security findings go to a full engineer task regardless of source, as do
remaining uncle-bob findings, and a single-concern merge-vader finding goes to an engineer
residual.

`baton-pass` hands a session to the next one: from an active sprint or an un-ticketed session
it writes a snapshot of the recorded state, runs `what-we-know`, asks the user what the next
session should focus on and what to do with uncommitted work, writes `handoffs/BATON.md` with
the facts that live nowhere else (settled decisions, dead ends, working commands, gotchas,
parked threads) and refreshes the ticket's `context` lines, running `open-ticket` first when no
ticket exists, then prints the opening prompt for the next session.

`prune-ticket` closes out a finished unit of work, and only you can start it: a 30-line archive
at `.mightymodels/archives/<slug>.md` with a JSON sidecar, cascading documentation updates
proposed as diffs, then deletion of the ticket directory on your confirmation. It refuses while
live work remains.

## Escalation and debugging

`ask-an-adult` escalates a genuinely undecidable judgment call to `wingman`, a tool-less
reasoning advisor, and carries its questions to the user before work resumes. The packet it
builds holds the ticket's text, because the wingman cannot read it. Use it for reasoning, not
for facts a scout can retrieve.

`whats-broken` is the primary's debugging protocol: reproduce, gather evidence with scouts (no
fixes proposed during the evidence phase), one named falsifiable hypothesis at a time written to
the ticket's `whats-broken.md`, a minimal hypothesis test, then the fix through a normal
engineer dispatch with a regression test. A hard three-strike breaker stops and escalates
instead of attempting a fourth patch.

`agent-debugging` is the same protocol for one engineer with nobody to dispatch. It is preloaded
into the engineer and applies when a task's verification fails after its edit: reproduce,
gather evidence alone, test one hypothesis, fix inside the owned files, and record each fix that
failed with the `failed_fix` tool. The tool stores three per task and refuses a fourth, and that
refusal ends the engineer's work with a `blocked` report listing the three.

## The reviewer doctrines

`becoming-uncle-bob` is the uncle-bob worker's doctrine: grade a branch or a codebase against
Robert C. Martin's published principles, SOLID, the Clean Code smells catalog, and the Clean
Architecture component metrics (dependency cycles, instability, abstractness, distance from the
main sequence). Findings are tied to named principles and the letter grade's arithmetic can be
checked.

`becoming-merge-vader` is the merge-vader worker's doctrine: the adversarial pre-merge review
of a branch or a codebase across security, SDLC regressions (weakened tests, CI, or tooling
gates), quality, documentation drift, and plan conformance when a plan or issue is supplied. It
ends in a gated verdict, `BLOCK`, `MERGE WITH CONDITIONS`, or `CLEAR`. `CLEAR` is impossible
while any security-relevant question sits `UNKNOWN-BLOCKED`.

Each is preloaded into its one worker and neither starts a review; `review-circus` does that.

## The fleet reference

`prompting-subagents` builds, checks or repairs the dispatch packet for a worker. It answers the
routing questions a primary faces at dispatch time: which of the twelve workers for which job,
which template to fill, which model alias and which `mightymodels:<folder>:<name>` type to pass,
and how to read the report that comes back. The skills that dispatch build their packets with
it, and the engineer, the architect and the two reviewers preload it for their own dispatches.
It also holds the template for the opening prompt `baton-pass` prints.

## Utilities

`crashout` is the pressure valve and flight recorder: on an explicit `/crashout`, it journals
the user's rant verbatim, checks whether the failure has happened before, and turns repeated
tilt into standing corrective actions. It fires only when invoked by name.

Issue-tracker sprint and board operations are deliberately outside the plugin, and their
phrasing is one half of a collision pair: sprint words alone must not pull in
`agents-assemble`.

## Editing a skill

Every skill edit ships with a re-run of its evals and a new dated result, or it does not ship.
Dated results live in `plugins/mightymodels/skills/<skill>/evals/`; [CONTRIBUTING.md](../CONTRIBUTING.md)
walks through the gate.

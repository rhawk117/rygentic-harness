---
name: using-mightymodels
description: >-
  The reference for mightymodels's worker fleet: which subagent to dispatch for a
  given job, what each worker refuses to do, what a dispatch must contain, and how model
  selection resolves. Consult this whenever you are deciding which agent, subagent, or worker to
  dispatch or delegate to; when the user asks what agents are available, who should handle a
  task, or "which model does X use"; when routing review findings or CI failures to a fixer; and
  at the start of any mightymodels session before the first dispatch. Covers scout, engineer,
  budgetron, gitty-up, grumpy, sunny, wingman, and the reviewer roles (uncle-bob, merge-vader).
  Not the sprint
  loop itself (that is agents-assemble), not for creating or editing agent files, and not for
  generating AGENTS.md instruction files (that is create-agents-md).
---

# using-mightymodels

Mightymodels is a worker fleet. You, the primary, spend your context on routing and judgment;
workers spend theirs on one narrow job each. Every worker is delegation-only and reports in a
parseable shape. Worker conversational state is never authoritative: a worker may retain
task-local context for bounded follow-ups, but all state required for recovery must be
externalized before the workflow advances, and verification requiring independence must use a
fresh worker context.
The fleet stays cheap because each worker refuses the work of the tier above it, and your
dispatches stay honest because every claim a worker makes is checkable by another worker.

## Promptlint requirement for every subagent prompt

**ALL prompts sent to subagents MUST use the criteria in
`skills/promptlint/SKILL.md`.** Before every dispatch, either instantiate the matching
promptlint role template or apply its full prompt architecture. Every prompt must include:

- a clear `<objective>` stating what the worker must do and why;
- `<context>` only for facts the worker cannot discover, plus `<discovery>` instructions for
  what to inspect before acting;
- explicit `<constraints>` that define the owned scope and preserve repository conventions;
- exact `<verification>` commands and expected results, with evidence required in the report; and
- an `<output>` section specifying changed files, verification evidence, and contradictions or
  blockers.

Prompts must state instructions positively, explain non-obvious constraints, avoid prescribing
implementation before discovery, and trim any content that does not change worker behavior.
For known fleet roles, use the corresponding template under
`skills/promptlint/references/templates/`; engineer prompts must carry the complete ASKED stanza.
When no role template exists, apply the full prompt architecture rather than dispatching the
rough task directly. This applies especially to grumpy, sunny, and wingman.

## The fleet at a glance

| Worker    | Class     | Job                                           | Hard state        | Never does                        |
| --------- | --------- | --------------------------------------------- | ----------------- | --------------------------------- |
| scout     | utility   | Locate, extract, run one command, cite facts  | `UNKNOWN-BLOCKED` | Analyze, diagnose, recommend      |
| engineer  | utility   | Implement one task group, verify, commit      | `blocked`         | Touch files outside its owned set |
| budgetron | utility   | Fix one named, bounded residual issue         | `escalated`       | Expand scope past the named issue |
| gitty-up  | utility   | Watch CI on one PR, report the verdict        | `error`           | Modify code, ever                 |
| grumpy    | reasoning | Attack a proposition, plan, diff, or claim    | report only       | Validate or fix the work          |
| sunny     | reasoning | Independently corroborate load-bearing claims | report only       | Criticize or fix the work         |
| wingman   | reasoning | Decide a genuinely stuck judgment call        | one-shot          | Read files, run commands, or act  |

Two reviewer roles complete the fleet but are not agent-file workers: `uncle-bob` (structure and
abstraction grading) and `merge-vader` (adversarial pre-merge review) are skills you run on a
frontier subagent during review-circus. Dispatch them by invoking the skill with the model named
in `ticket.yml`, not by agent name.

## Choosing a worker

Route by what you need, not by what feels senior:

- You need a fact, a location, a call-site list, a config value, or one command's output: scout.
  One narrow question per dispatch. If you are about to ask a scout "why" or "should", stop; that
  judgment is yours or an analyst's, and scouts will hand it back as `NEEDS-ANALYSIS`.
- You need code written against acceptance criteria: engineer, dispatched with an ASKED stanza
  (promptlint's engineer template emits it). The engineer commits its own work and appends the
  DONE half of the brief; do not commit for it.
- You need one known fix applied (a failing lint rule, a missed verification item, a review
  finding that carries explicit Fix and Verify lines): budgetron. If the fix is not
  nameable in a sentence, it is not bounded, and it belongs to an engineer.
- You need to know whether CI passed: gitty-up, after the PR exists. Treat its `error` verdict as
  a stop, never as a pass.
- You need verification of an engineer's DONE claims: a scout, checking DONE against ASKED
  criterion by criterion. Never let the engineer grade its own work, and never grade it yourself
  from the diff alone.
- You need to attack a proposition, plan, diff, or root-cause claim: grumpy. Give it one
  falsifiable claim and the evidence surface; it reports defects, risks, and questions only.
- You need independent corroboration of that same proposition: sunny. Run it blind and in parallel
  with grumpy; it reports confirmations and unconfirmed areas only.
- You are stuck between defensible choices, facing an expensive-to-reverse decision, holding
  conflicting scout reports, or have failed twice: use `ask-an-adult`, which dispatches wingman
  with the complete facts packet and surfaces its questions before work resumes.
- You are arguing both sides of a technical proposition, weighing a safety or data-integrity
  claim, or disputing a review finding: use `dialectic`, which dispatches grumpy and sunny in
  parallel on one proposition, then adjudicate their evidence. Do not use it for a fact a scout
  can retrieve or a decision already made.

Review findings route by risk first, then source: a Critical finding, or a security finding at
High severity or above, goes to a full engineer no matter which reviewer found it. Below that
line, uncle-bob findings go to an engineer (structure judgment needed to fix what a structure
judge flagged) and merge-vader findings go to budgetron (concrete and bounded, and its
`escalated` verdict is the safety valve when a bound was misjudged).

CI failures route by the log-tail test: cause obvious from the last screen of the log means
budgetron; cause needing investigation means the whats-broken protocol, not a fixer.

## What a dispatch must contain

Workers fail fast on underspecified dispatches, which is by design: a bounced dispatch costs one
cheap round trip, a misunderstood one costs a bad diff.

- scout: one concrete question, the scope to search, and the citation form you want back.
- engineer: the ASKED stanza (objective, checkable acceptance criteria, verification commands in
  order, files-in-scope, engineer tier), plus the brief path under the ticket's `briefs/`.
- budgetron: the one named issue, its Fix line, its Verify line, and nothing else.
- gitty-up: the PR reference and the base branch.
- grumpy: one falsifiable proposition, the artifact or files under review, the requirement, and
  the repository root.
- sunny: the exact same proposition and evidence surface as grumpy, without grumpy's report or
  the primary's lean.
- wingman: the decision, options and costs, gathered facts with citations, constraints, attempted
  approaches, and the primary's lean.

Reasoning workers are read-only. `dialectic` may write only its compact decision record under the
active `.mightymodels/<task-slug>/` directory; neither reviewer modifies the reviewed artifact.

## How models resolve

Read the active ticket's `subagent-models` block in `.mightymodels/<slug>/ticket.yml` at every
dispatch; the `model:` pins inside the agent files are only the fallback for headless runs
where no ticket answers. Defaults: scout and gitty-up on `claude-haiku-4-5`; budgetron and
grumpy on `claude-sonnet-5`; sunny, wingman, uncle-bob, and merge-vader on `claude-opus-5`;
engineer derived from ticket scope (`large` pulls `claude-opus-5`, otherwise
`claude-sonnet-5`). You may bump a
single gnarly task's engineer one tier at dispatch; log the reason in that task's ASKED stanza.

## Reading reports

Workers report in XML with a shared vocabulary: `<report>`, `<findings>`, `<verdict>`,
`<confidence>`, `<follow_up>`. Scouts separate `VERIFIED` facts from `INFERRED` ones, and
anything inferred names what it rests on; treat an `INFERRED` line as a hypothesis, not a fact.
The full verdict vocabularies and the severity table live in
`skills/agents-assemble/references/contracts.md`, which wins whenever a report and this page seem
to disagree.

## Anti-patterns the mill exists to prevent

Dispatching an engineer to answer a lookup question burns implementation budget on retrieval.
Asking a scout to recommend an approach gets you `NEEDS-ANALYSIS` at best and laundered
guesswork at worst. Handing budgetron a vague "clean this up" invites scope creep that
its contract will refuse anyway. Reading gitty-up's `error` as "probably fine" ships unverified
code. And doing a worker's job yourself as the primary, committing for an engineer or verifying
your own dispatch, removes the second pair of eyes the loop is built around.

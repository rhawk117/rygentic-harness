---
name: agents-assemble
description: >-
  Use when starting, resuming, or continuing the mightymodels per-task work loop for a staged
  ticket (after game-plan or one-shot): engineer dispatch per task, contract commands run
  before judgment checks, the `task` tool gating each task on receipts, citations and
  ownership, architect once on failure, whats-broken after that.
when_to_use: >-
  Use for "run the loop", "start the sprint", "do the next task", "pick the sprint back up", and
  when game-plan or one-shot hands over a staged ticket.
argument-hint: "[ticket-slug]"
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_state__contract
  - mcp__plugin_mightymodels_state__task
  - mcp__plugin_mightymodels_state__ticket
---

# agents-assemble

The per-task loop. Its whole design bet is that verification has a persisted target: the ASKED half of each brief is written *before* the engineer starts, so "done" is checkable against what was asked rather than against what got built. Read `references/contracts.md` once per session — it carries the severity table, verdict vocabularies, the two-half brief schema, and the caps this file assumes.

**Preconditions:** a staged ticket (`mcp__plugin_mightymodels_state__ticket` with action `show` answers; open-ticket's `validate` staged it) and an enumerable task list: the issue's task list (one-shot) or `plan.md` tasks (game-plan). Missing either → stop and name it; the ramps exist to produce them.

**Argument:** the ticket's slug, given when the skill was started: "$ARGUMENTS". Empty quotes mean none was given, and the ticket is the session's active one.

Progress lives in the `task` tool and the `contract` tool; the one command run through Bash is
`mightymodels verify run`, from the repository root.

## Per task

**1. what-we-know, sprint mode.** Fresh citations for this task against current HEAD: where the change lands, what touches it, candidate `files-in-scope`. Uncertainties come back to you with blast radius; you decide ask-versus-proceed. A wrong guess confined to one file is a fix; a wrong guess across a boundary is a mess.

**2. Write the ASKED stanza.** Use prompting-subagents' engineer template; its output is the stanza. Paste it to the top of `briefs/task-NN.md` and into the dispatch. Every AC is a contract command (`Tn.AC-m`) or a checkable assertion with a location; "works correctly" is refused at write time, because an uncheckable criterion turns verification into theater. A command AC not yet in the contract goes to the user in one `AskUserQuestion` dialog (id and argv) and is approved with the `contract` tool's `approve` action, as game-plan shows, before the dispatch; the runner will not execute anything else. Engineer tier comes from ticket.yml; bump one tier for a genuinely gnarly task, with the reason logged in the stanza.

**3. Open the attempt, then dispatch.**

Call `mcp__plugin_mightymodels_state__task` with action `start` (`T1` stands for the task's id):

```json
{"request": {"action": "start", "slug": "SLUG", "payload": {"task_id": "T1", "change": {"by": "engineer", "owned": ["<files-in-scope>"]}}}}
```

The owned set recorded here is what step 5 checks the commit against, so it is the stanza's `files-in-scope`, not a guess. Then dispatch `mightymodels:workers:engineer` through the `Agent` tool, its `model` the engineer's fixed alias, `sonnet`, which `subagent-models` repeats. The dispatch names the brief path; the engineer appends `## DONE` before reporting and commits, and never pushes: only the primary pushes.

A task's size in the plan picks the worker: a `tiny` task (it owns exactly one file and every acceptance criterion is a command with an expected result) goes to the intern, and every other size to the engineer, which may also take a tiny one. A task given to the intern is opened the same way with `by` `intern` and its one owned file, and dispatched as `mightymodels:workers:intern` on `haiku`, with prompting-subagents' intern template. The dispatch hook refuses that dispatch unless the intern has a started task and every task started for it owns exactly one file; its refusal names the engineer. The intern gets one attempt at a task: `task` `start` refuses a second one by it.

**4. Mechanical checks before judgment.** On `done`, run the task's contract commands at the new HEAD:

```bash
mightymodels verify run --slug SLUG --phase task --id Tn.AC-1 --id Tn.AC-2
```

Then one code-scout pass for the assertion ACs only, criterion by criterion, each coming back `VERIFIED` with a citation or not. An engineer report claiming `verified="true"` on a criterion the check contradicts gets called out by name; averaging a contradiction is how drift compounds. Then your own surface-level read of the diff; it is the second opinion now, not the only one.

**5. Gate the task.**

Call `mcp__plugin_mightymodels_state__task` with action `verify`:

```json
{"request": {"action": "verify", "slug": "SLUG", "payload": {"task_id": "T1", "change": {"commit": "<engineer commit>", "assertions": {"AC-2": "<file:line from code-scout>"}}}}}
```

It passes only when the commit is the current HEAD, every `Tn.*` contract command passed at it, the brief's DONE half names that commit on a `commit: <hash>` line of its own, every other AC in the brief carries a citation, and the commit touched nothing outside the owned set (read from git, not from the report). The tool finds the brief from the slug and the task id. It stores the outcome and its transition row in one transaction before it answers `verified`. A `blocked` result lists why and leaves the task `blocked`; treat it as a failed attempt.

**6. Route what did not verify.**

- Bounded, mechanical, one-concern residual (the gate's reasons name it) → **engineer**, residual variant of its template, Fix:/Verify: verbatim, after `task` `start` with `by` `engineer` and `owned` the files the Fix touches.
- Intern returns `blocked`, or the gate blocks after its attempt → `task` `mark` with `to` `blocked` and a `reason` (a task the gate blocked already is `blocked`), then **engineer**: `task` `start` with `by` `engineer` and the same owned set, and the engineer template with the intern's blocker in its context. The task goes to the engineer with no question to the user, and never back to the intern.
- Engineer returns `failed` or `blocked`, or the gate blocks after its attempt (an engineer's `blocked` after three failed fixes lists the hypotheses it tried; put them in the architect's ASKED so none is tried again) → `task` `mark` with `to` `failed` or `blocked` and a `reason` (a task the gate blocked already is `blocked`), then **architect** once: `task` `start` with `by` `architect` and `owned` the same owned set (the mode defaults to `recovery-implementation`), and the architect template (trigger, ASKED, mode, brief path). Architect replaces the brief's DONE half and is gated by step 5 like the engineer.
  - `scope-expansion-requested`: put the requested files to the user. On approval, hand the task, still in progress, to the architect again: `task` `start` with `by` `architect`, `mode` `systemic-refactor` and the expanded `owned` set, and dispatch in that mode; the tool allows exactly one such extra pass.
  - `replanned`: `task` `mark` with `to` `superseded` closes the old task so `ready` can pass, and the revised ASKED becomes a new task (next free `T` id) with its own contract commands, approved like any other.
- Architect also fails → **whats-broken**, the primary's protocol (the engineer's `agent-debugging` has already spent its three fixes), with the engineer's hypotheses in its log. The `task` tool refuses a second implementation pass on its own; only `diagnose-replan`, which edits nothing, may still start. The next attempt is never another patch, because repeated failure means the understanding is wrong.

**7. Close the task.** Durable before advance: only after `task` `verify` answered `verified` do you move on. A task that did not verify does not close; it routes (step 6) or escalates to the user with the gate's reasons. On recovery after a compaction, `task` `show` and `contract` `status` are the state; the conversation is not.

Review remediation from review-circus re-enters here: each selected finding is a new task or residual with its own contract commands, and an architect `diagnose-replan` result from review arrives as a revised ASKED, run through this same loop.

## Sprint end

Report the count: tasks completed, residuals fixed, anything escalated. Write `REPORT.md` (≤50 lines): what shipped per task, commits, open threads. Then **stop** — pushing and PR-opening belong to stick-the-landing, so the user gets a look between "work done" and "work public".

## Rules that keep the loop honest

Models never hardcoded: ticket.yml decides. State never lives only in the conversation: the `task` tool and the verification receipts are what a recovered session reads. Briefs are written, never pasted wholesale into dispatches (paths travel, content doesn't). Caps are contracts: 80-line briefs, 50-line REPORT. And the loop never asks the user a question a blast-radius judgment could answer — but never guesses across a boundary either.

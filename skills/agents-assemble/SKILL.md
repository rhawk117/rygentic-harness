---
name: agents-assemble
description: >-
  Run the mightymodels per-task work loop for an active ticket: for each task — what-we-know citations, a promptlint-templated engineer dispatch carrying an ASKED stanza with checkable acceptance criteria, the two-half task brief, scout verification of DONE against ASKED, budgetron for residuals, whats-broken after repeated failures — ending in a ≤50-line REPORT.md. Use when a ticket is ramped and the user says to start, begin, run, resume, or continue the mightymodels work loop on a ticket — "begin the sprint", "start working the ticket", "run the loop", "continue the sprint". Not for Jira sprint or board operations (the jira skill owns those), not for opening PRs or watching CI (finish-assembly), and not for ramping a fresh session (inline-sendoff / plan-work run first).
---

# agents-assemble

The per-task loop. Its whole design bet is that verification has a persisted target: the ASKED half of each brief is written *before* the engineer starts, so "done" is checkable against what was asked rather than against what got built. Read `references/contracts.md` once per session — it carries the severity table, verdict vocabularies, the two-half brief schema, and the caps this file assumes.

**Preconditions:** an active ticket (`.mightymodels/<slug>/ticket.yml`) and an enumerable task list — the issue-body checklist (sm ramp) or `plan.md` tasks (large ramp). Missing either → stop and name it; the ramps exist to produce them.

## Per task

**1. what-we-know, sprint mode.** Fresh citations for this task against current HEAD: where the change lands, what touches it, candidate `files-in-scope`. Uncertainties come back to you with blast radius; you decide ask-versus-proceed — a wrong guess confined to one file is a fix, a wrong guess across a boundary is a mess.

**2. Write the ASKED stanza.** Use promptlint's engineer template (`promptlint/references/templates/engineer.md`) — its output is the stanza. Paste it to the top of `briefs/task-NN.md` and into the dispatch. Discipline that makes step 4 real: every AC is a runnable command or a checkable assertion with a location. "Works correctly" and "handles errors appropriately" are refused at write time — an uncheckable criterion turns verification into theater. Engineer tier comes from ticket.yml; bump one tier for a genuinely gnarly task, with the reason logged in the stanza.

**3. Dispatch the engineer.** Model from ticket.yml `subagent-models` (the agent file's pin is only the headless fallback). The dispatch names the brief path; the engineer's contract makes it append `## DONE` (≤65 lines) before reporting. Commit per dispatch; push only in remediation mode.

**4. Verify DONE against ASKED.** One scout-tier pass per task, criterion by criterion: run the AC's command or check its assertion, VERIFIED/UNVERIFIED each, with the evidence. An engineer report claiming `verified="true"` on a criterion the check contradicts gets called out by name — averaging a contradiction is how drift compounds. Then your own surface-level sanity read of the diff; it is the second opinion now, not the only one.

**5. Route residuals.**
- Bounded, mechanical, one-concern residual → **budgetron** (dispatch via its promptlint template; Fix:/Verify: verbatim). Two rounds max; its contract escalates on budget or scope excess, and an escalation routes to a full engineer dispatch.
- Scout verification fails **twice** on the same task → **whats-broken**. The third attempt is never another patch; repeated failure means the understanding is wrong, and patching a misunderstanding just relocates it.

**6. Close the task.** All ACs verified → check the task's box (issue checklist or plan), delete nothing, move on. A task with unverified ACs does not close — it routes (step 5) or escalates to the user with the evidence.

## Sprint end

Report the count: tasks completed, residuals fixed, anything escalated. Write `REPORT.md` (≤50 lines): what shipped per task, commits, open threads. Then **stop** — pushing and PR-opening belong to finish-assembly, so the user gets a look between "work done" and "work public".

## Rules that keep the loop honest

Models never hardcoded — ticket.yml decides. Briefs are written, never pasted wholesale into dispatches (paths travel, content doesn't). Caps are contracts: 80-line briefs, 50-line REPORT. And the loop never asks the user a question a blast-radius judgment could answer — but never guesses across a boundary either.

---
name: yolo
description: >-
  Fast ramp into the mightymodels work loop from whatever context exists: an active ticket, a
  pasted issue, or a task described in chat. One ask-user dialog covers the questions
  prepare-handoff would have asked and that the context has not already answered (slug, scope,
  branch, progress view), then two or three scouts confirm the claims at HEAD, the task
  checklist is written with a checkable acceptance criterion per task, and agents-assemble
  takes over. Writes the minimal ticket directory when none exists. Assumes no compaction, so
  there is no plan.md and no handoff file; the checklist is the only durable state.
  Auto-invoke at session start when the active ticket says scope sm and plan-first false; use
  explicitly on any scope for "/yolo", "yolo this", "just send it", "skip the plan and run the
  loop", "start on this without a ticket", with an ask-user confirmation on med or large
  scope. Not the ramp for work expected to survive a compaction (game-plan).
---

# yolo

The loop's value is the scout-and-engineer discipline: claims confirmed at HEAD, an ASKED
stanza written before the engineer starts, verification by a scout that did not write the
code. The plan exists for a different reason: surviving a compaction. When the user does not
expect one, the plan is ceremony, and this ramp skips it. The conversation is the memory, the
ticket directory holds the briefs, the checklist is the progress view.

That is an assumption, and yolo states it once at the start of every run: *no compaction
expected; if one happens, stop and re-ramp through game-plan, because the checklist alone
will not carry the intent.* Said once, then the work starts.

## Sequence

**0.** Invoke `using-mightymodels`.

**1. Take stock.** If `.mightymodels/<slug>/ticket.yml` exists, read it and the issue (or
`issue-body.md`); that is the target and most of the interview is already answered. Otherwise
the target is what the user gave: the chat so far, a pasted issue, a link. State the target in
one line and what done looks like in one more; if the second line cannot be written, the
interview's first question is what proves done.

**2. The short interview.** One ask-user dialog, containing only the questions the context
has not answered. The full set, in prepare-handoff's order, minus the one yolo answers itself:

- Slug for this unit of work (propose one derived from the target).
- Scope of each anticipated task: sm, med, or large. This derives the engineer model per the
  ticket schema, same as prepare-handoff.
- Branch: current, or a new one (propose the name).
- Progress view: a GitHub issue, or a local `issue-body.md` checklist.

Compaction is not asked. yolo answers it: `plan-first: false`. When scope comes back med or
large, one more dialog before anything is written: proceed under the no-compaction
assumption, or route to game-plan. A med or large ticket that hits a compaction mid-sprint
loses more than a sm one, so the user confirms that trade knowingly.

Answers already in the conversation or the ticket are confirmed in the target summary, not
re-asked.

**3. Materialize the minimum.** Only when no ticket exists: the ticket directory, the ignore
ritual from `prepare-handoff/references/mightymodels-dir.md` (`mm://ref/prepare-handoff/mightymodels-dir`), and `ticket.yml` per
`references/ticket-schema.md` (`mm://ref/prepare-handoff/ticket-schema`) with `plan-first: false`, the scope answer, and the derived
engineer model. The branch if one was asked for. The issue via `gh issue create` if one was
asked for, else `issue-body.md`. No `handoffs/SPRINT.md`, no `plan.md`; nothing is written
for a next session that is not expected to exist. Tell the user the file exists and that
their edits win, and keep going; the tweak pause is prepare-handoff's, and yolo's user asked
for speed.

**4. Confirm the claims.** Two or three scouts (models from ticket.yml), each verifying one
claim the target rests on still holds at HEAD: the file is at that path, the API has that
shape, the config key is where the description says. A claim that no longer holds is a delta
report to the user before anything starts, not something to adapt around silently. On a
freshly described task there may be no claims to confirm beyond "the thing exists"; one scout
is enough, and zero is not.

**5. Enumerate the tasks.** Write the checklist into the issue body (`gh issue edit`) or
`issue-body.md`. Each item is one thing agents-assemble can run through the loop, sized per
the scope answer, and carries its acceptance inline so the ASKED stanza lifts it:

```markdown
- [ ] T1: <one-line intent> | AC: <runnable command with expected result, or a checkable assertion naming a file or behavior>
```

Without a plan, the checklist is the only enumerable task list the loop has, and an item with
no acceptance makes the verification step theater. "Works correctly" is refused here for the
same reason it is refused in the ASKED stanza. Present the checklist and ask through the
dialog: go, or revise. Revise regenerates the list.

**6. Hand off.** Invoke agents-assemble. Nothing else is written; ticket.yml plus a checklist
with acceptance is what the small path needs, and the whole point of yolo is that it is enough.

## Boundaries

yolo writes the minimal ticket directory (when absent), the branch and issue if asked, and
the checklist. It never writes `plan.md` or `handoffs/`. It dispatches scouts and nothing
else before agents-assemble takes over. When the context shows the work is bigger than the
user thinks (five med tasks on a "sm" answer), that is a sentence to the user and a routing
offer to game-plan, not a quiet upgrade.

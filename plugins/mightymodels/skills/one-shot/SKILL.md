---
name: one-shot
description: >-
  Fast ramp into the mightymodels work loop from whatever context exists: an active ticket, a
  pasted issue, or a task described in chat. One AskUserQuestion dialog covers the questions
  open-ticket would have asked and that the context has not already answered (slug, scope,
  branch, progress view), then two or three scouts confirm the claims at HEAD, the task
  list is written with a checkable acceptance criterion per task, its commands are
  approved into the verification contract, and agents-assemble takes over. Stages the ticket
  through the ticket tool when none exists. Assumes no compaction, so there is no
  plan.md. Auto-invoke at session start when the active ticket says scope sm and plan-first
  false; use explicitly on any scope for "/one-shot", "one-shot this", "yolo this", "just
  send it", "skip the plan and run the loop", "start on this without a ticket", with an
  AskUserQuestion confirmation on med or large scope. Not the ramp for work expected to survive a compaction (game-plan).
---

# one-shot

The loop's value is the scout-and-engineer discipline: claims confirmed at HEAD, an ASKED
stanza written before the engineer starts, verification by a scout that did not write the
code. The plan exists for a different reason: surviving a compaction. When the user does not
expect one, the plan is ceremony, and this ramp skips it. The ticket directory holds the
briefs; the state database holds the ticket, the verification contract and the task rows, and
the `task` tool's rows are the progress view.

That is an assumption, and one-shot states it once at the start of every run: *no compaction
expected; if one happens, stop and re-ramp through game-plan, because the task list alone
will not carry the intent.* Said once, then the work starts.

## Sequence

**0.** Invoke `prompting-subagents`.

**1. Take stock.** If `.mightymodels/<slug>/ticket.yml` exists, read it and the issue (or
`issue-body.md`); that is the target and most of the interview is already answered. Otherwise
the target is what the user gave: the chat so far, a pasted issue, a link. State the target in
one line and what done looks like in one more; if the second line cannot be written, the
interview's first question is what proves done.

**2. The short interview.** One `AskUserQuestion` dialog (up to four questions a call, two to four
options each, and the user can always type an answer of their own), containing only the
questions the context has not answered. The full set, in open-ticket's order, minus the one one-shot answers itself:

- Slug for this unit of work (the options are one derived from the target and a shorter variant).
- Progress view: a GitHub issue, or a local `issue-body.md`; task progress is the `task`
  tool's rows either way.

The scope of each anticipated task and the branch are not asked here: the `ticket` `write` call
in step 3 leaves them out and asks the user itself. Compaction is not asked. one-shot answers it:
`plan-first: false`. When the scope the user chose comes back med or large (read `scope` in
ticket.yml after the write), one more `AskUserQuestion` before the loop starts: proceed under the
no-compaction assumption, or route to game-plan. A med or large ticket that hits a compaction
mid-sprint loses more than a sm one, so the user confirms that trade knowingly.

Answers already in the conversation or the ticket are confirmed in the target summary, not
re-asked.

**3. Materialize the minimum.** Only when no ticket exists: the issue via `gh issue create` if
one was asked for (else `issue-body.md`), then stage the ticket through the `ticket` tool, as
open-ticket does. Call `mcp__plugin_mightymodels_state__ticket` with action `write`, the answers
under `fields`, and no `scope` or `branch`; the tool asks the user for both:

```json
{"request": {"action": "write", "slug": "SLUG",
 "fields": {"summary": "...", "compaction": false, "context": ["..."]}}}
```

An answer starting `needs input` means no one could be asked through the tool: put each question
it names to the user in one `AskUserQuestion` dialog, then call again with those arguments in
`fields`. Then read `branch-name` from ticket.yml: when it is not the current branch, create that
branch from HEAD.

Then call it again with action `validate`, which stages the ticket as a row in the state
database:

```json
{"request": {"action": "validate", "slug": "SLUG"}}
```

open-ticket's schema reference,
`${CLAUDE_PLUGIN_ROOT}/skills/open-ticket/references/ticket-schema.md`, describes the fields. No `plan.md`; nothing is written for a next session that is not
expected to exist. Tell the user ticket.yml exists and that their edits win (call `validate`
again after one), and keep going; the tweak pause is open-ticket's, and this user asked for speed.

**4. Confirm the claims.** Two or three scouts (models from ticket.yml), each verifying one
claim the target rests on still holds at HEAD: the file is at that path, the API has that
shape, the config key is where the description says. A claim that no longer holds is a delta
report to the user before anything starts, not something to adapt around silently. On a
freshly described task there may be no claims to confirm beyond "the thing exists"; one scout
is enough, and zero is not.

**5. Enumerate the tasks.** Write the task list into the issue body (`gh issue edit`) or
`issue-body.md`. Each item is one thing agents-assemble can run through the loop, sized per
the scope answer, and carries its acceptance inline so the ASKED stanza lifts it. The list has
no boxes; progress is the `task` tool's rows, which the loop starts and marks:

```markdown
- T1: <one-line intent> | AC: <runnable command with expected result, or a checkable assertion naming a file or behavior>
```

Without a plan, the task list is the only enumerable list of work the loop has, and an item with
no acceptance makes the verification step theater. "Works correctly" is refused here for the
same reason it is refused in the ASKED stanza. Give every command-shaped AC a contract id
(`T1.AC-1`) and an argv list, and show the task list with its commands. The loop's runner
executes only contract commands, so approve them with one call to
`mcp__plugin_mightymodels_state__contract` with action `approve` and no `approved_by`; the tool
asks the user and records the commands only when the user approves:

```json
{"request": {"action": "approve", "slug": "SLUG",
 "commands": [{"id": "T1.AC-1", "argv": ["..."], "expect_exit": 0, "timeout": 300}]}}
```

An answer starting `not approved` means the user wants the list changed: change it and call
again. An answer starting `needs input` means no one could be asked through the tool: put the
question it names to the user in one `AskUserQuestion` dialog, and on approval call again with
`"approved_by": "user"` on each command.

Then baseline each one with `mightymodels verify run`, a bare Bash command (the plugin's
`bin/` is on the Bash PATH):

```bash
mightymodels verify run --slug SLUG --phase planning --id T1.AC-1
```

Revise regenerates the list.

**6. Hand off.** Invoke agents-assemble. Nothing else is written; a staged ticket plus a
task list with approved acceptance commands is what the small path needs, and the whole point
of one-shot is that it is enough.

## Boundaries

one-shot stages the ticket (when absent) through the `ticket` tool, the branch and issue
if asked, the task list, and the verification contract. It never writes `plan.md` or
`handoffs/`. It dispatches scouts and nothing
else before agents-assemble takes over. When the context shows the work is bigger than the
user thinks (five med tasks on a "sm" answer), that is a sentence to the user and a routing
offer to game-plan, not a quiet upgrade.

---
name: break-it-down
description: >-
  Split one mightymodels task that is too large into tasks of one reviewable unit of work each,
  and put the split to the user before anything changes. Use when the `task` tool's `start`
  refuses a task for more than four acceptance criteria or more than ten owned files, when an
  engineer or architect returns `too-large` with its cuts, or when a plan task is plainly several
  changes. Ends in one AskUserQuestion dialog showing every piece (id, intent, acceptance, owned
  files); only after the user answers is the original superseded and the plan updated. Not for
  revising the contract of one task (the architect's `replanned`), and not a way to get a large
  task past the refusal.
when_to_use: >-
  Use for "break this task down", "split T4", "this task is too big", and when agents-assemble
  routes a `too-large` report or a `start` refusal here.
argument-hint: "[task id]"
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_state__contract
  - mcp__plugin_mightymodels_state__task
---

# break-it-down

One dispatch is one reviewable unit of work. A task past that size fails in a known way: the
implementer runs out of room, the verification proves half of it, and the reviewer gets a diff
nobody can hold in their head. So the `task` tool's `start` refuses a task with more than four
acceptance criteria or more than ten owned files, and an engineer or architect that finds one
mid-task returns `too-large`. Both end here.

**Nothing changes before the user answers.** Until the dialog in step 4 is answered this skill
writes nothing: no `task` call that moves a task, no contract approval, no edit to the plan or to a
brief. The pieces are a proposal, and the plan is the user's. A dialog that timed out, was
dismissed or came back empty is not an answer: open it again. Do not decide for the user, do not
ask in prose instead, and do not start on a piece while you wait.

**Never fit a task under the bound by editing its lists.** Dropping a criterion, folding two into
one sentence or leaving a file out of `owned` gets a call past `start` and leaves the task exactly
as large. The gate then blocks the commit for the file that was left out.

**Argument:** the id of the task to split, given when the skill was started: "$ARGUMENTS". Empty
quotes mean none was given, and the task is the one `start` just refused or a worker just returned
as `too-large`.

**Preconditions:** a staged ticket and the task's entry in the task list (`plan.md`, or the
issue's task list after one-shot). Missing either: stop and name it.

## Steps

**1. Read the task as it stands.** Its entry in the task list (intent, acceptance, `depends-on`,
verify), the ASKED stanza of its brief when one was written, and its status from
`mcp__plugin_mightymodels_state__task` with action `show`:

```json
{"request": {"action": "show", "slug": "SLUG"}}
```

A worker's `cuts` are where to begin, because it has read the code. Check them against step 2
before you adopt them, and read the files it listed as already edited: that work is in the tree,
uncommitted, and the pieces have to account for it.

**2. Find the cuts.** Cut where the task already has a seam, trying these in order:

- by behavior: criteria that can be proven apart go to different pieces;
- by module: files that change for different reasons go to different pieces;
- by order: what must land first (a schema before its callers, a helper before its users) is a
  piece of its own, and the pieces that need it name it in `depends-on`.

Every piece has to stand alone, so hold each one to this:

- At most four acceptance criteria and ten owned files. Two to four criteria is the usual size.
- Every criterion of the original lands in exactly one piece, in its own words. None is dropped
  and none is invented. A criterion that two pieces each need half of is two criteria: write both
  out and say in the dialog that it was divided, because that changes the contract.
- Every file the original owned lands in a piece. Two pieces that edit the same file run in
  order, joined by `depends-on`, never side by side.
- The repository passes after each piece, not only after the last: the plan's invariants hold at
  every task boundary. A piece that cannot be verified alone is not a piece yet.

Some tasks do not cut: one rename across thirty files is one change. Say so in the dialog
and offer the task whole; the user decides, not the bound.

**3. Give the pieces ids.** The next free `T` ids of the task list, in dependency order. The
original's id is never reused, because its history and its contract commands stay under it. A
criterion that is a command gets an id under its new task (`T7.AC-1`) with the argv it had: an
approved id never changes its argv, so the old ids close with the original. Each task that named
the original in `depends-on` will name the piece that carries what it waited for.

**4. Ask the user once.** Write the pieces out in full in your message, then open one
`AskUserQuestion` dialog about them. Each piece shows its id, its intent, its acceptance and its
owned files:

```text
T7 (sm): <one-line intent: what and where>
  depends-on: []
  acceptance:
  - AC-1: <the criterion, as the original stated it> (was T4.AC-1; contract id T7.AC-1, argv [...])
  - AC-2: <...>
  owned: src/queue.py, tests/test_queue.py
```

Below the pieces, list what the split changes outside them: each `depends-on` that moves, each
criterion that was divided, and each file a worker already edited with the piece that takes it.
The dialog has one question with these options:

- **Split as shown.** The original is superseded and the pieces replace it.
- **Keep it as one task.** Nothing is split; the task starts whole on the user's approval.
- **Change the split.** The user says what to change, through the dialog's free text.

## After the answer

**Split as shown.** In this order, so that a session cut off halfway still has a true record:

1. Supersede the original with `mcp__plugin_mightymodels_state__task` and action `mark`, the
   reason naming the pieces. The tool takes this for a task `start` refused, which never
   started, as it does for one a worker returned:

   ```json
   {"request": {"action": "mark", "slug": "SLUG", "payload": {"task_id": "T4", "change": {"to": "superseded", "reason": "split into T7, T8 and T9"}}}}
   ```

2. Update the task list where it lives (`plan.md`, or the issue's task list as one-shot wrote
   it). Under the original's heading leave one line, `superseded: split into T7, T8, T9`, in place
   of its acceptance and verify. Add the pieces in dependency order, and repoint each `depends-on`
   as the dialog listed.
3. Record the pieces' commands with `mcp__plugin_mightymodels_state__contract` and action
   `approve`. The user approved each id and argv in the dialog, so each command carries that:

   ```json
   {"request": {"action": "approve", "slug": "SLUG", "commands": [{"id": "T7.AC-1", "argv": ["uv", "run", "pytest", "-q", "tests/test_queue.py"], "approved_by": "user"}]}}
   ```

4. Report one line per piece (id, size, intent) and the original as superseded, then hand back
   to agents-assemble. Each piece runs through its loop as a task of its own, from what-we-know
   onward; the original's brief is not reused.

**Keep it as one task.** Split nothing and change nothing in the task list. A task a worker
returned as `too-large` is still in progress, and `start` does not take one: `mark` it `blocked`
with that reason first. Then start the task with the call `start` refused and one more field,
which the tool accepts only as `user` (`mcp__plugin_mightymodels_state__task`, action `start`):

```json
{"request": {"action": "start", "slug": "SLUG", "payload": {"task_id": "T4", "change": {"by": "engineer", "owned": ["<files-in-scope>"], "acceptance": ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5"], "too_large_approved_by": "user"}}}}
```

This answer is the only thing that permits that field. It is never added because a refusal was in
the way, and never on a different task than the one the user was shown.

**Change the split.** Return to step 2 with what the user said and ask again with the new pieces.
The earlier answer approved nothing.

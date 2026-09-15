---
name: baton-pass
description: >-
  Hand the current session to the next one without losing what this session learned. Works
  from an active agents-assemble sprint (a task too big for one context) or from a session
  with no ticket at all. Runs what-we-know in interactive mode, asks the user in one ask-user
  dialog what the next session should focus on and what to do with uncommitted work, then
  readies the ticket directory: for an existing ticket it writes handoffs/BATON.md (facts
  that live nowhere else: state, settled decisions, dead ends, working commands, gotchas,
  parked threads) and refreshes ticket.yml context; with no ticket it runs prepare-handoff
  with the focus as the summary. Ends by printing a promptlint-built prompt in chat for the
  next session. Use for "pass the baton", "hand this off to a fresh session", "I'm about to
  compact", "carry this over", "the next session should pick up from here". Not the
  sprint-end handoff to review (stick-the-landing), not a ticket for work not yet started
  from a clean triage (prepare-handoff directly).
---

# baton-pass

A session that ends mid-work leaves two kinds of knowledge behind. One kind is already in
artifacts: ticket.yml, the issue checklist, the briefs, the commits. The other kind is only
in this conversation: the decision made at turn forty, the approach that failed and why, the
exact test invocation that finally worked, the thread the user said to park. The next agent
either receives that second kind or spends its first hour re-deriving it, and it will
re-derive some of it wrong. This skill captures the second kind and only the second kind,
then hands the next session a prompt that points at everything.

<important>Invoke `using-mightymodels` before the first dispatch.</important>

## 1. Establish the state

Two entry states, decided by whether `.mightymodels/<slug>/ticket.yml` exists for the work in
progress.

- **Active ticket.** Read ticket.yml, the checklist, and every brief. Establish, from
  artifacts and then from `git status` and `git log`: which task is in flight, whether its
  brief has a DONE half, whether the working tree is dirty, and the current branch and HEAD.
  Durable-before-advance applies: a commit with no DONE half is an incomplete task, and it is
  written down as one, not as "nearly done".
- **No ticket.** The state is the conversation: what was being worked on, what has been
  established, and what has changed on disk. Run `git status` to find out what this session
  touched.

Then invoke `what-we-know` in interactive mode, saying so explicitly in the dispatch so the
presence of a `briefs/` directory does not flip it into sprint mode. Its knowns table and
uncertainties are the evidence base; the interactive dialog is where uncertainties the user
can settle get settled now rather than inherited.

## 2. Ask what the next session is for

One ask-user dialog, two questions, options drawn from the state rather than generic:

**Focus.** Derived from what is open: continue the in-flight task; start the next unchecked
task; take a specific open thread the session surfaced (name it); re-plan because the picture
changed; something else. One recommended, with the reason in the parenthetical.

**Uncommitted work**, only when the tree is dirty: commit as a WIP on the branch; stash with a
named message; leave it in place and say so in the baton. Recommend the commit; an uncommitted
diff is the least durable thing a session can leave.

Act on the second answer before writing anything else. The baton describes the tree as it is
after that action, and a baton that describes a stash that was never made is worse than none.

## 3. Prepare the ticket directory

**Active ticket.** Write `handoffs/BATON.md`, 40 lines or fewer, then refresh the `context:`
lines in ticket.yml with any decision made this session that the next session cannot afford
to lose (three to six lines total, no `file:line`). The baton carries only what lives nowhere
else; a fact that is in ticket.yml, the issue, or a brief is a pointer here, not a copy.

```markdown
# Baton for <slug>

Focus: <the user's answer, one line>
State: branch <name> at <short sha>; in flight: <task, brief path, DONE half present or absent>; tree <clean | WIP commit sha | stash name>

## Settled this session
- <decision> (user, or dialectic rung n, or cross-examine round n)

## Do not retry
- <approach> | failed because: <one line>

## Works
- <exact command> | for: <what it proves or sets up>

## Gotchas
- <what cost time> | so: <what to do instead>

## Parked
- <thread> | why parked: <one line> | revisit when: <signal>
```

Every line is a fact from this session with its origin. "Consider refactoring X" is not a
baton line; "X was refactored and reverted because the test at Y depends on the old shape" is.
A next agent that receives advice reasons about it; one that receives facts acts on them.

**No ticket.** Invoke `prepare-handoff` with the focus answer as the summary. It runs the
interview for whatever the conversation has not answered, rolls the what-we-know findings
into the issue body and ticket.yml `context`, and creates the branch or records the current
checkout. When it returns, write `handoffs/BATON.md` in the same shape, since the dead ends
and working commands from this session are not part of a triage rollup.

## 4. Print the prompt

Invoke `promptlint` and build the next session's opening prompt for Claude Code, then print it
in chat inside a fenced block. It is a pointer prompt: read ticket.yml, read the issue or the
checklist, read `handoffs/BATON.md`, invoke `using-mightymodels`, then the one skill to invoke
for the focus (agents-assemble to continue or start a task; game-plan to re-plan; the ramp per
the routing table for a freshly prepared ticket). It carries the focus line verbatim and
nothing else that lives in a file, so it cannot drift from them.

Print it after the baton is written, never before. The prompt is the last thing this session
does, and a prompt that names a file that does not exist yet is the failure this ordering
prevents.

## Boundaries

Writes `handoffs/BATON.md`, the `context:` lines of ticket.yml, and whatever the user chose
for uncommitted work; through prepare-handoff, the ticket directory when none existed. Never
checks a task's box, appends a DONE half, or writes REPORT.md; those belong to the loop and
the engineer, and a baton that closes a task the loop did not verify is a lie the next
session inherits.

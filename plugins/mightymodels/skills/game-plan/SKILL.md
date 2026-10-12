---
name: game-plan
description: >-
  Large-scope ramp for a mightymodels ticket: read ticket.yml and the issue, verify the
  ticket's claims with scouts, run cross-examine so the user
  decides the design before drafting, interview the user (AskUserQuestion) on how each risk is handled, then
  write the ticket's plan.md as a compaction-safe ledger: intent, approach, invariants that
  must hold throughout, dependency-ordered tasks each with deterministic acceptance criteria
  and the commands that verify them, non-goals, and risks with the user's chosen handling. No
  file:line citations. Records every verification command in a user-approved contract and
  runs it at HEAD through a no-shell runner before approval, then invokes agents-assemble.
  Not for small tickets (one-shot), not a design
  document or ADR (the plan sequences work on a settled design).
when_to_use: >-
  Auto-invoke at session start for any scope/plan-first combination other than scope sm with
  plan-first false; use for "plan this ticket", "run the game plan", "write the plan for
  issue #N", "ramp the big one".
argument-hint: "[ticket-slug]"
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_state__contract
---

# game-plan

The large ramp. The plan it writes is read by a primary that has forgotten this conversation:
`plan-first: true` means at least one compaction is expected, and after compaction plan.md is
the only memory the sprint has. So the plan is a ledger, not an essay. Everything in it is
something the sprint cannot afford to lose; everything the sprint can rediscover is left out.

Two consequences follow, and the tension between them is where plans go inconsistent:

- **No file:line citations.** A plan written at commit A runs across commits B through K; a
  line number carried in it is stale by task three and trusted anyway. what-we-know compiles
  fresh citations per task, inside the loop, at dispatch time.
- **Deterministic acceptance and verification per task.** A task whose intent is one line and
  whose acceptance is left to the sprint gets re-interpreted at every dispatch, and the
  interpretations drift. Acceptance criteria and verification commands are not citations: a
  command is checkable at HEAD whenever it runs, and if it stops existing the engineer's
  `blocked` verdict names the plan mismatch, which is the contract working.

Altitude is not vagueness. A task says what and where, never how; it also says exactly what
proves it done.

## Sequence

**Argument:** the ticket's slug, given when the skill was started: "$ARGUMENTS". Empty quotes mean
none was given, and the ticket is the session's active one.

**0.** Invoke `prompting-subagents`.

**1. Read ticket.yml and the issue.** These are the only things you read without a scout. The
plan implements the ticket; a plan written from conversation memory instead of the ticket is
the drift this system exists to kill. `scope` sizes the ticket and sets no worker's model,
which routing fixes; `plan-first` tells you whether the reader will be a post-compaction primary
(assume yes either way).

**2. Verify the claims.** Models from ticket.yml. Each major claim the issue makes about the
codebase gets one code-scout confirmation at HEAD; a claim that rests on external
documentation goes to web-scout. When the ticket links an investigation, its `lead` rows are
where to look, not what to believe. Stale claims are a delta report to the user before you
plan on top of them. Also ask code-scout where the repository's own test, lint, and build
commands are declared (CI workflow, task runner, package scripts), so the commands in step 4
are the repository's, not guesses.

**3. Cross-examine the user.** Invoke `cross-examine` with the ticket's `summary` as the
target; the user picks the depth. `base-intent` is a plan field, written into plan.md in step
4, not a ticket key. Its decisions record is the input to the draft, and the
draft is not started until the record's closing dialog says shared understanding was reached.
This is the step that stops the plan being one the agent wrote and the user nodded at: the
approach, the boundaries, and what done looks like are the user's calls, and this is where
they make them. Under game-plan the questions bias toward what the plan needs: the outcome and
what proves it, the invariants, what is out of scope, the ordering constraints, and the
user's appetite for each trade-off.

**4. Draft the plan from the record, then run the consistency check.** Lift the decisions
record into the schema below before writing anything of your own:

- Decided lines become the approach, the non-goals, the invariants, and the acceptance
  criteria of the tasks they bear on. A decision that fits none of those is a task.
- Facts become the verified claims the plan rests on; they carry no locations into the plan.
- Open lines become Risks, with the signal being the thing that would resolve them.
- Assumed lines become Risks whose signal is the assumption proving false, so the risk
  interview covers every assumption the depth left unexamined.

Then read the draft as the post-compaction primary would and check every line of the list
under "Consistency check". Fix the draft until the list is clean. Do this before the user
sees it; the user's time is for direction, not for catching a task with no acceptance.

**4b. Approve and run the verification commands.** Every invariant's proving command and
every command-shaped acceptance criterion gets a contract id (`I1`, `T1.AC-1`) and an argv
list. Make one call to `mcp__plugin_mightymodels_state__contract` with action `approve`, the full
list, and no `approved_by`; the tool shows the user each id and argv and records the commands
only when the user approves them:

```json
{"request": {"action": "approve", "slug": "SLUG", "commands": [
  {"id": "I1", "argv": ["uv", "run", "pytest", "-q"]},
  {"id": "T1.AC-1", "argv": ["uv", "run", "pytest", "-q", "tests/test_queue.py"], "timeout": 120}
]}}
```

An answer starting `not approved` means the user wants the list changed: change it as they said
and call again. An answer starting `needs input` means no one could be asked through the tool: put
the question it names to the user in one `AskUserQuestion` dialog, and on approval call again with
`"approved_by": "user"` on each command.

Then run them at HEAD with a bare Bash command (the plugin's `bin/` is on the Bash PATH):

```bash
mightymodels verify run --slug SLUG --phase planning --id I1 --id T1.AC-1
```

The runner takes ids only, never an argv, so nothing unapproved runs through it; commands
are argv lists with no shell, so a check that needs a pipeline belongs in a script the
repository owns. An approved id never changes its argv; a different command gets a new id.
Record each command's planning outcome in the plan: an invariant that fails at HEAD is a
finding for the user before anything is built; an acceptance command that fails because the
thing it tests does not exist yet is the expected baseline. Read
`references/verification-contract.md` when a record or run is refused.

**5. Interview the user on risks.** Every risk in the draft gets a handling chosen by the user,
not by you. One `AskUserQuestion` dialog, risks batched up to four a call, each offering the same
four handlings (the user can always type a handling of their own):

- **Accept**: proceed; the signal is noted, nothing changes.
- **Mitigate**: add a task, or a criterion to an existing task, that reduces the risk; you
  propose which.
- **Gate**: the sprint stops and asks the user the moment the signal appears.
- **Re-plan trigger**: the signal means the plan is wrong; the sprint stops and game-plan runs
  again.

Record the choice in the Risks section verbatim. A risk without a user-chosen handling is a
risk the post-compaction primary will handle by improvising. When no dialog is available, ask
in chat with the four handlings spelled out, and wait.

**6. Get approval.** Write `plan.md` with the handlings folded in, present it, and ask through
`AskUserQuestion`: approve, revise, or abandon. This gate is the user's, and it is the last cheap
moment to change direction. On approve, invoke agents-assemble. On revise, regenerate the whole
plan (never append to it) and state in one paragraph what changed and why, so the user reviews
a delta rather than re-reading two hundred lines. A revision that contradicts a Decided line
is a new decision: put it back through one cross-examine round rather than editing the plan
around it. On abandon, leave no plan.md behind.

## plan.md schema (~200 lines max, contracts.md cap)

```markdown
# <slug> plan
base-intent: <what this unit of work changes, one paragraph>
approach: <the strategy, and why it beats the alternative considered>

## Invariants
- I1: <what must stay true across every task> | proves: <contract id I1: the command, and its outcome at HEAD>

## Tasks
### T1 (<tiny|sm|med|large>): <one-line intent: what and where, no how>
depends-on: []
acceptance:
- AC-1: <contract id T1.AC-1 with its command and planning outcome, or an assertion naming a file or behavior>
- AC-2: <...>
verify: <contract ids, in order; each run at HEAD in step 4b>

### T2 (<size>): <...>
depends-on: [T1]
acceptance:
- AC-1: <...>
verify: <...>

## Non-goals
- <explicitly out of scope> | why: <one line>

## Risks
- R1: <what could go wrong> | signal: <the early observable> | handling: <accept | mitigate: T-n AC-n | gate | re-plan> (user)
```

What each section is for, since the reader will not have this file:

- **Invariants** are the things that must hold at every task boundary, with the command that
  proves them: the test suite stays green, a public endpoint keeps its contract, a migration
  is never touched. They are the "cannot be forgotten under any circumstances" layer; a
  post-compaction primary reads them before every dispatch. Three to five is typical. An
  invariant without a proving command is a wish.
- **Tasks** are in dependency order, and `depends-on` makes the order checkable rather than
  implied. A task's size picks its worker: `tiny` goes to the intern and every other size to
  the engineer, which may also take a tiny task. `tiny` is a bound that can be checked, not a
  feeling: the task owns exactly one file and every acceptance criterion is a command with an
  expected result. A task that misses either half is `sm` or larger, and the dispatch hook
  refuses the intern on a started task that owns any other number of files. A ticket has one
  scope, its tasks do not.
- **acceptance** is lifted into the task's ASKED stanza at dispatch, so the same rule applies
  now: every criterion is a command someone runs or an assertion someone checks at a named
  location. "Works correctly", "handles errors appropriately", and "is consistent with the
  rest of the code" are refused at write time. Two to four criteria per task; a task needing
  more is two tasks.
- **verify** is the sequence of contract ids the engineer runs before appending DONE and the
  loop re-runs with `mightymodels verify run` afterwards. It is the same sequence in both places,
  which is what makes verification comparable across tasks.
- **Non-goals** are load-bearing: they are what keeps a long sprint from growing sideways while
  nobody is watching. Each carries its one-line why so a later session does not relitigate it.
- **Risks** carry the user's handling verbatim, tagged `(user)`, so the sprint knows the
  choice was made and by whom.

## Consistency check

Run this against the draft before the risk interview, and again against the final plan before
approval. Each item is a way plans have gone wrong; each is a yes/no question.

- Every task has at least one acceptance criterion that is a command or a located assertion,
  and none of the refused phrasings appear anywhere.
- Every command in any `verify` or `proves` line is a contract id the user approved in step
  4b, and the plan states its planning outcome at HEAD.
- Every Decided line in the cross-examine record appears in the plan as the approach, a task,
  an invariant, a non-goal, or an acceptance criterion, and no plan line contradicts one.
- Every Open and Assumed line in the record appears as a Risk with a signal.
- Every `depends-on` names a task that appears earlier in the file.
- No task's intent overlaps another task's intent; overlap means the split is wrong.
- No task does something a non-goal excludes, and no non-goal excludes something a task needs.
- Every invariant has a proving command.
- Every risk has a signal that is observable during the sprint, not only after it, and (after
  the interview) a handling tagged `(user)`. A mitigation names the task or criterion it
  added.
- Task sizes are plausible against the ticket's `scope`; five `large` tasks on a `med` ticket
  is a scope finding for the user, not a plan.
- Nothing in the file is a `file:line` citation or a path that only makes sense at this
  commit. Commands are fine; locations are not.
- The file is under the cap. Hitting it means content belongs in a task's future ASKED stanza
  or in the issue, not that the plan grows.

## Boundaries

game-plan writes `plan.md`, only after cross-examine and the risk interview, plus the
ticket's verification contract and its planning receipts. It dispatches scouts and runs
only approved contract commands; no engineer, no architect, no edits to the repository. If step 2
shows the ticket's claims are wrong enough that the approach changes, that is a report to the
user and possibly a return to open-ticket, not a plan built on a corrected premise the
ticket does not record.

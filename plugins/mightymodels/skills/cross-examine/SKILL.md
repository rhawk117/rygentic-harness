---
name: cross-examine
description: >-
  Interview the user about a plan, design, or decision until a shared understanding exists,
  at a depth the user picks first (Skim, Standard, or Relentless). Works the design tree in
  rounds: each round asks every decision whose prerequisites are settled, via the ask-user
  dialog only, two to four concrete options each, one recommended, pitched at a senior
  engineer with no rationale for asking. Facts go to scouts, decisions to the user, nothing
  assumed silently. Restates a decisions record after every round that game-plan lifts into
  approach, invariants, non-goals, acceptance, and risks. Runs inside game-plan between claim
  verification and drafting; also use standalone for "grill me", "cross-examine this plan",
  "stress-test my design", "interview me about the approach", "poke holes in this before I
  build it". Writes no files. Not for retrieving facts (scouts), a stuck judgment call
  (ask-an-adult), or breaking a tie the user cannot answer (dialectic).
---

# cross-examine

A plan written from a vague intent is a plan the agent wrote and the user nodded at. This
skill exists to move the deciding to the user before anything gets planned: every branch of
the design gets a question, every question gets a choice, and the choice is the user's. What
comes out tracks the quality of the answers, not the number of questions, so the user sets the
depth first and steers throughout.

<important>Invoke `using-mightymodels` before the first scout dispatch.</important>

## Round zero: target and depth

State the target in one line: the plan, design, or decision under examination. Inside
game-plan it is the ticket's base-intent; standalone it is whatever the user brought.

Then one ask-user dialog with two questions:

**Depth.** How far the interview goes before it stops.

- **Skim**: one round, top of the tree only. Everything below it is assumed and listed.
- **Standard**: up to three rounds, the whole frontier each round. Remaining branches are
  assumed and listed.
- **Relentless**: rounds until the frontier is empty. Nothing is assumed.

**Width.** Whole frontier per round (dialogs of up to three questions until the frontier is
covered), or one question per dialog. One at a time is slower and easier to steer; offer it
without recommending it.

Record both at the top of the decisions record. A plan reader needs to know how much was
decided and how much was assumed, and the depth is the honest summary of that.

## The design tree and the frontier

Map the target as a tree: every decision branches into the decisions that hang off it. The
**frontier** is every decision whose prerequisites are already settled, the questions you can
ask now without guessing at answers you have not heard. Ask the frontier; wait; recompute.

A question whose answer depends on another question still open this round belongs to the next
round, not this one. Asking it early forces the user to answer under an assumption they have
not made yet, and the answer has to be re-asked when the assumption resolves.

Three kinds of question arrive at the frontier, and only one goes to the user:

- **Facts** (what the code does, which table holds it, what the library defaults to, what CI
  runs) go to a scout. Finding facts is your job, never the user's. A running scout is an
  unsettled prerequisite: only the questions downstream of it wait; ask the rest of the
  frontier now.
- **Decisions** (which behavior, which boundary, which trade-off, what done looks like) go to
  the user through the dialog.
- **Feel** questions (how should the interaction feel, is this abstraction pleasant) do not
  grill well and get a prototype instead. Record them as Open with "needs a prototype" and
  move on rather than asking the user to imagine the answer.

## Asking a question

The user is a senior engineer who makes sound architecture decisions. Write for that reader.
A question is the decision point in one line, and each option is a choice with its
consequence in a few words. The dialog is the whole question: no preamble, no definition of a
term the user coined, no sentence explaining why the question is being asked. A rationale for
asking says the user could not have worked it out, which is both wrong and slow to read.

Explanatory means the options carry the trade-off, so the user decides from the dialog alone.
Terse means nothing else is there.

```
Retry bound for outbound webhooks?
  Attempt count, fixed at 5 (recommended: matches the client's own limit; simplest to test)
  Wall-clock deadline of 60s (survives slow endpoints; needs a clock in tests)
  Both, whichever trips first (safest; two knobs to document)
  Other / I don't know
```

Two to four options, written as the actual choices rather than yes/no on your framing.
Exactly one is marked `(recommended)` with its reason in the parenthetical; the other
parentheticals carry that choice's trade-off, not a reason to reject it. The last option is
always `Other / I don't know`, followed by a sentence in chat. "I don't know" is a real
answer; it means the question is either a fact (send a scout) or a prototype, and it is
recorded as Open, not guessed.

Pitch at the fidelity the plan needs. "Which bound" grills well; "should retries be bounded"
gets a yes without deciding anything. If the user says a question is pitched beneath what
they need, or is asking something the codebase could answer, that is steering, not pushback:
re-pitch it or send a scout.

When no dialog is available, ask in chat in the same shape (numbered, options listed, one
recommended) and wait for the answers before the next round.

## The decisions record

Restate it in full after every round. It is the only state the session has, and the final
one is what game-plan reads.

```markdown
## Decisions record, round N
Target: <one line>
Depth: <skim | standard | relentless>, width: <frontier | one at a time>

### Decided
- D1: <the decision> | options: <what was offered> | chose: <which> (user, round n)

### Facts
- F1: <fact> [<file:line> | <URL#heading> | command output]

### Open
- O1: <question> | why open: <fact pending | needs a prototype | user does not know> | plan impact: <what changes if it resolves the other way>

### Assumed
- A1: <the assumption made because depth ran out> | would change: <which decision or task>

### Frontier
- <the next round's questions, or "empty">
```

A Decided line carries the user's choice from a dialog and nothing else; your recommendation
is what was offered, not what was chosen. Assumed is empty under Relentless by definition.
Open items are handed forward, never resolved by the primary's best guess.

## Ending

The interview ends when the frontier is empty, when the depth's round cap is reached, or when
the user says stop. Close with one dialog: shared understanding reached, one more round, or
stop here. Only the first hands the record onward; inside game-plan that is a return to the
drafting step, standalone it is an offer of game-plan or prepare-handoff, never an invocation.

If the session has run long enough that questions are getting worse, say so and recommend
stopping with the record as it stands. A large scope is grilled as several smaller targets,
not as one two-hundred-question session.

## Boundaries

Read-only. Nothing is written to disk; scouts are the only dispatch. The skill asks, the user
decides, and a decision the user did not make in a dialog is not in Decided.

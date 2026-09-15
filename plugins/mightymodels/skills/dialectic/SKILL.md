---
name: dialectic
description: >-
  Break a tie between two or three viable options when the primary cannot separate them and
  the user does not know either. Frames the fork and its reversal cost, dispatches grumpy and
  sunny blind and in parallel per option, scores each option by the damage of what was found
  rather than the count, then walks a fixed tie-break ladder (found defects, reversal cost,
  conformance with the repository, surface touched, a bounded spike, then a recorded coin
  flip) until one rung decides. Writes a compact decision record with the rung that decided
  and the signal that would reopen it, and puts the decision to the user as a single
  accept-or-override dialog. Use when ask-an-adult came back with questions the user could
  not answer, when you are holding two options you rate equal, or when the user says "you
  pick", "I don't know, decide", "both seem fine". Not for a fact a scout can retrieve, a
  decision the user already made, a judgment call the user can answer (ask-an-adult), or a
  plan to be blessed.
---

# dialectic

Some forks have no answer in the code and no answer in the user's head. The agent rates the
options equal, ask-an-adult produced questions the user could not answer, and the sprint is
stalled on a choice that a coin could make. This skill exists so that the choice gets made by
a procedure rather than by whichever option was written first, and so the record says which
rung of the procedure made it. Two things it never does: keep arguing after the ladder has
decided, and hand the fork back to a user who already said they do not know.

<important>Invoke `using-mightymodels` before the first dispatch.</important>

## 1. Frame the fork

Write the fork as options, each in one line with what it costs, and one more line per option
stating how expensive it is to reverse: a schema, a public interface, a dependency, or a
deletion is expensive; a private module boundary is cheap. Two or three options; a fork with
five branches is a design problem for cross-examine.

Then look at the reversal costs before dispatching anything. When every option is cheap to
reverse, skip to the ladder at rung 2 without dispatching reviewers: a cheap decision that
costs four reasoning dispatches has been made expensive by the process meant to help. The
reviewers earn their cost only when picking wrong is hard to undo.

## 2. Examine each option

Each option becomes one claim that could be false: "Option A satisfies requirement R without
introducing X." For each claim, dispatch `grumpy` to break it and `sunny` to confirm it, blind
to each other and in the same turn, the shared dispatch linted through `promptlint` with the
full prompt architecture. The dispatch carries the claim, the files or plan it concerns, the
requirement, and the repository root, and nothing about which option you or the user lean
toward. Sequential dispatch lets the second worker inherit the first one's framing through
you; a leaked lean comes back from both sides looking like corroboration.

`sunny` gets the stronger model by default. `grumpy` wins by finding one hole, which a
mid-tier model can do; `sunny` wins only if the claim survives every attack it can construct,
and weaker models confirm after two attacks instead of six. Invert when the option is a
surface `grumpy` must sweep rather than a claim it must puncture. Set both in `ticket.yml`
per dispatch.

Both are read-only. A worker that starts fixing has stopped examining.

## 3. Score, then climb the ladder

Score each option by the worst thing found against it on the contracts.md severity table, not
by how many things were found. Three Lows lose to one High. Where `grumpy` reports a defect at
a line `sunny` reports confirmed, dispatch a `scout` to that line carrying both claims and let
the reading settle it; on that line you have less evidence than either of them.

Then take the rungs in order and stop at the first that separates the options:

1. **Found defects.** A Critical or High against one option and not the others decides it.
   Below High, a difference of one severity level decides it; equal worst-severity does not.
2. **Reversal cost.** The option cheaper to undo wins. Being wrong cheaply is a fix; being
   wrong expensively is a rewrite.
3. **Conformance.** The option that does what the repository already does elsewhere wins;
   one scout dispatch names the precedent or its absence. A codebase with two ways to do a
   thing has a maintenance cost neither option's author pays.
4. **Surface.** The option touching fewer files, interfaces, and dependencies wins.
5. **Spike.** When a bounded experiment would separate them (one command a scout can run, or
   one sm task an engineer can do on a throwaway branch and report), run it and score again
   from rung 1. Bounded means one dispatch; a spike that needs a plan is not a spike.
6. **Coin flip.** The options are equivalent by every measure available. Take the one the
   user listed first, and say in the record that this rung decided. Equivalent options mean
   the choice does not matter, and further argument is spending budget to feel better.

A rung that separates the options is the decision. Do not keep climbing to see whether a
later rung agrees; the ladder is ordered by how much each rung's evidence is worth.

## 4. Record

Write `.mightymodels/<task-slug>/dialectic-<fork-slug>.md`, 40 lines or fewer. The full
reports stay in the transcript; this file is what survives compaction.

```markdown
# <the fork, one line>

Options: <A: one line, reversal cost> | <B: ...>
Worst found: <A: severity, location> | <B: ...>
Decided by: rung <n> (<name>)
Decision: <A or B>, because <the rung's evidence in one sentence>
Reopen if: <the observable signal that would send this back to rung 1>
Unexamined: <what neither worker covered>
```

## 5. Put it to the user once

One ask-user dialog: the decision marked `(recommended: rung n, reason)`, each other option
as its own choice, `Run the spike first` when rung 5 was available and not taken, and
`Stop`. No preamble and no rationale for asking; the user already said they could not
separate the options, and the dialog's job is to let them accept or override in one tap. On
accept, the record stands and work resumes. On override, the record is rewritten with
`Decided by: user` and the reason they gave, if any. A user who picks the option the ladder
rejected has not made a mistake; they have information the ladder did not.

## Boundaries

Reasoning workers and scouts only; nothing in the repository changes, and a spike runs on a
branch that is deleted afterward. The only file written is the decision record. A fork whose
wrong branch would be Critical on the severity table is not tie-broken here: say so, and
route it to cross-examine or back to game-plan, because a ladder is the wrong tool for a
choice that must not be made by a coin.

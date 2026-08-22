---
name: dialectic
description: >-
  Stage a two-sided independent examination of a proposition you cannot settle by reading — dispatch grumpy to break it and sunny to confirm it, in parallel and blind to each other, then adjudicate from where their reports collide. Reach for this whenever you are stuck between two viable approaches, holding a root-cause hypothesis you have not proven, weighing whether a design or security decision is actually sound, or facing a review finding the engineer disputes. Also use it the moment you notice yourself arguing both sides of a question in your own head, which is the signal that one reasoner has run out of independent evidence — even if nobody used the words "review", "critique", or "second opinion". Not for questions a single file read settles.
---

# Dialectic

A proposition you generated is a proposition you are anchored on. Thinking harder about it runs the same priors through the same context and hands you back a more confident version of what you already believed.

This replaces that with evidence you did not produce. Two workers get the same proposition and no knowledge of each other: `grumpy` is paid to break it, `sunny` is paid to confirm it. Neither hedges, because neither is allowed to do the other's job. What you reason from afterward is not their opinions — it is the shape of their disagreement, which is checkable in a way introspection is not.

## When this is worth its cost

Reach for it when the question is genuinely undecidable from where you are standing:

- Two viable approaches, and the wrong one costs a rewrite.
- A root-cause hypothesis that explains the symptom but has not been shown to be _the_ cause.
- A safety, data-integrity, or security claim where being wrong is expensive and being right is invisible.
- A review finding the engineer disputes, where you have two competing readings of the same code.
- Any time you catch yourself writing "on the other hand."

Skip it when:

- A read, a grep, or a test settles it. Dispatch a `scout` instead — a fraction of the cost, and it returns fact rather than argument.
- You have already decided and want the decision blessed. Both cops will oblige in their own direction, you will keep the one you wanted, and you will have paid for the privilege. This is the most common way this skill gets wasted.
- The proposition is a matter of taste. Neither worker can confirm or refute a preference, and both will produce filler trying.

Pick a different tool when one fits better. `wingman` is the move when you want one stronger reasoner's judgment on a decision and there is nothing to verify in the code — it takes no tools and recommends. `review-circus` is the move when the work is finished and you want it graded. This skill sits between them: the work is not done, the question is not a matter of judgment, and there is code or a plan that can actually settle it.

## 1. Sharpen the proposition

Both workers get one proposition, stated as a claim that could be false. The exercise succeeds or fails here. Dispatched a topic, both sides write essays; dispatched a claim, both sides go find evidence.

A usable proposition names the thing, the property, and the scope.

**Weak:** "Is the caching approach right?"
**Strong:** "No caller of `store.Get` can observe stale data, given that invalidation runs on the write path at store.go:142."

**Weak:** "Should we put this behind a queue?"
**Strong:** "Moving `notify()` behind SQS introduces no user-visible ordering change, because the only ordering the UI depends on is per-conversation, and FIFO message groups preserve that."

The strong versions carry their own falsification condition — a worker can go find the caller that sees stale data, or the ordering dependency that isn't per-conversation. The weak versions can only be agreed with.

Write the dispatch once and send it to both verbatim: the proposition, the files or plan it concerns, the requirement it is meant to satisfy, and the repo root. Say nothing about which way you lean. A dispatch that leaks your prior gets it back from both sides, and you will mistake that for corroboration.

## 2. Tier the two sides

Their jobs are not equally hard, and the asymmetry runs the opposite way from intuition.

`grumpy` wins by finding one hole. That is an existence proof. A mid-tier model that surfaces a real defect has done the entire job, and the first flaw is usually the cheapest one to find.

`sunny` wins only if the proposition survives every attack it can construct. That is a universal claim, and universal claims are where weaker models fail silently — they confirm after two attacks instead of six and emit the same `<verdict>confirmed</verdict>` either way. A false confirmation is the single output of this exercise that can put a defect into the artifact.

So the default is asymmetric: **`sunny` gets the stronger model.** Invert it when the proposition spans a surface `grumpy` has to sweep rather than a claim it has to puncture — a whole plan, a large diff, a system-wide invariant — because then `grumpy` is the one carrying the exhaustiveness burden.

Set both per dispatch in `ticket.yml` rather than accepting the agent defaults. The right tier follows the proposition, not the worker.

## 3. Dispatch both at once

Run the shared dispatch through `promptlint` first, using the full prompt architecture because
grumpy and sunny have no dedicated templates. Send the linted prompts in the same turn. Sequential
dispatch is the quietest way to break this skill: whichever worker runs second inherits the first
one's framing through you, and you get one perspective wearing two hats at twice the price. Neither
worker is told the other exists.

Both are read-only. A worker that starts fixing things has stopped examining them.

## 4. Read the collision

Their reports meet in one of four shapes, and the shape tells you what to do.

**Both refute.** `grumpy` found a hole; `sunny` could not confirm that region. The proposition is dead. Do not spend a second pass rescuing it — return to step 1 with a different proposition.

**Both hold.** `grumpy` found nothing above its bar; `sunny` confirmed with evidence. This is weaker than it feels. Two workers can share a blind spot, especially having read the same files in the same order. Compare their `<checked>` blocks before you act: if the coverage overlaps tightly and both are narrow, you bought one perspective, not two, and the proposition is unexamined outside that band.

**They collide on one location.** `grumpy` reports a defect at `foo.py:88`; `sunny` reports the same line confirmed. This is the highest-information outcome in the exercise and the reason to run it at all — one of them misread the code, and which one is a cheap fact question. Dispatch a `scout` at that exact location carrying both claims and let it settle the reading. Do not adjudicate a collision from their prose; on that line you have less evidence than either of them.

**They pass in the night.** `grumpy` attacked the concurrency, `sunny` confirmed the ordering, and neither touched the other's ground. Common, and not a failure — it means the proposition was compound. Split it and run the half nobody examined, or accept that half as unexamined and say so in the record.

## 5. Adjudicate

Land on one position, in your own words:

- **Stands** — with the specific evidence it stands on, so the next agent can check you rather than trust you.
- **Falls** — with the failure path, which is now an input to whatever you do next.
- **Blocked** — on a named unknown, with what would resolve it. This is a real outcome, not a failure to decide.

"Both sides raise valid points" is not one of these. It is what synthesis looks like when the proposition was never sharp enough to be settled, and it means step 1 failed. Split the proposition and rerun rather than shipping the hedge.

Nothing in either report is authoritative because a worker said it. Their evidence is authoritative; their confidence is not. `sunny` confirming something does not clear it, and `grumpy` failing to break it does not either — both are bounded by whatever their `<checked>` blocks say they actually looked at.

## The record

Write `.mightymodels/<task-slug>/dialectic-<proposition-slug>.md`, 40 lines or fewer:

```markdown
# <the proposition, exactly as dispatched>

Position: stands | falls | blocked
Evidence: <what carries it — file:line, command, trace>
Unexamined: <what neither worker covered>
Next: <the action this decision unblocks, or the unknown that blocks it>
```

The full reports stay in the transcript. This file is what survives compaction and what the next agent reads, so write it for someone who was not here.

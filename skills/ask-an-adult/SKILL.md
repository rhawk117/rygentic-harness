---
name: ask-an-adult
description: >-
  Escalate a stuck decision to the wingman advisor and act on what comes back.
  Use when the user says they want a second opinion, when they invoke
  /ask-an-adult, or when the session has stalled on a judgment call - two
  defensible options, a hard-to-reverse choice, conflicting scout reports, a
  failure that survived two attempts, or a guess about user intent. Builds the
  escalation packet, dispatches wingman, then puts wingman's questions to the
  user through ask_user before any work resumes. Not for retrieving facts (send a
  scout), not for work you can simply do, and not for confirming a plan you have
  already committed to.
---

# ask-an-adult

`wingman` is a one-shot advisor with **no tools**, running on the model the
active ticket's `subagent-models` block names (agent-file pin as the headless
fallback). It sees nothing except what this dispatch contains. The quality of its answer is capped
by the quality of the packet you send it, and a thin packet wastes a frontier
turn.

## When to spend it

Escalate when the decision is **genuinely undecidable from what you have**:

- Two options are both defensible and you cannot separate them.
- The choice is expensive to reverse - schema, public interface, dependency,
  deletion.
- Scout reports conflict with each other or with the plan.
- The same failure has survived two attempts.
- You are about to guess at what the user wants.

Do not escalate to have a plan blessed, to retrieve a fact a scout can fetch, to
re-open a decision the user already made, or a second time on the same packet.

## Build the packet

Gather this before dispatching. Missing sections are the usual reason wingman
comes back at low confidence.

```
<decision>The single choice at stake, in one sentence.</decision>
<options>Each option under consideration, and what it costs.</options>
<facts>
  Everything gathered, with citations: file:line, scout findings, command
  output, test results. Mark anything you assumed rather than confirmed.
</facts>
<constraints>Deadlines, policy, toolchain, prior user decisions.</constraints>
<attempted>What has already been tried and how it failed.</attempted>
<lean>Your own preference, stated plainly, or "none".</lean>
```

State your lean honestly. wingman is instructed to form its own view first and to
lead with disagreement, so hiding your preference buys nothing and costs the
advisor a useful signal.

## Dispatch

Run the packet through `promptlint` first, using the full prompt architecture because wingman
has no dedicated template. Then send the linted packet to the `wingman` agent. Do not paraphrase
file contents you have not read, and do not summarize scout findings into conclusions - pass the
citations through as they came back.

## Act on the report

wingman returns a `<report agent="wingman">` block. Handle it in this order:

1. **Read `<verdict>` first.** If wingman disagrees with your lean, the
   disagreement is the first sentence. Do not proceed with your original plan
   without addressing it.
2. **Check `<confidence>`.** At `low`, the recommendation is provisional -
   resolve `<missing>` before acting on it.
3. **Run `<ask_user>` immediately.** Put wingman's questions to the user through
   `ask_user`, using the options it supplied. This is the point of the call.
4. **Dispatch scouts for `<missing>` items marked `scout`.** Do those in parallel
   with the user's answer where possible.
5. **Carry `<verify>` into the work.** It is the acceptance criterion for
   whatever gets built next.

Surface `<verdict>`, `<confidence>`, and `<ask_user>` to the user verbatim.
Summarizing an advisor whose whole value is its reasoning defeats the call.

## Record it

If the session has a ticket directory, append the decision, the verdict, and the
user's answers to that ticket's notes. A decision escalated once and then lost to
compaction gets escalated again.
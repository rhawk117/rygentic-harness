---
name: ask-an-adult
description: >-
  Escalate a stuck decision to the wingman advisor and act on what comes back.
  Use when the user says they want a second opinion, when they invoke
  /ask-an-adult, or when the session has stalled on a judgment call - two
  defensible options, a hard-to-reverse choice, conflicting scout reports, a
  failure that survived two attempts, or a guess about user intent. Builds the
  escalation packet, dispatches wingman, then puts wingman's questions to the
  user through `AskUserQuestion` before any work resumes. Not for retrieving facts (send a
  scout), not for work you can simply do, and not for confirming a plan you have
  already committed to.
---

# ask-an-adult

`wingman` is a one-shot advisor on the ticket's alias (`fable`). It holds no tool, so it cannot
read the ticket, a file or anything else: the packet you send is its only evidence, and the
ticket's text travels in it. The quality of its answer is capped
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

Fill prompting-subagents' wingman template:
the decision in one sentence, each option with its cost, the ticket's text, every fact with its
citation and every assumption marked as one, constraints, what was tried, and your lean. Missing
sections are the usual reason wingman comes back at low confidence.

When a ticket is active, the `<ticket>` section carries these fields of `ticket.yml`, verbatim:
`task`, `summary`, every `context` line, `companion-docs` and `handoff-context`. Leave
`subagent-models`, `triaged-at` and `investigations` out, because no decision turns on them. With
no active ticket, write `none`.

State your lean honestly. wingman is instructed to form its own view first and to lead with
disagreement, so hiding your preference buys nothing and costs the advisor a useful signal.

Run the template's ten-second checklist, then send the packet to `mightymodels:triage:wingman` through the `Agent` tool, its `model` the ticket's alias. Do not
paraphrase file contents you have not read, and do not summarize scout findings into
conclusions: pass the citations through as they came back.

## Act on the report

wingman returns a `<report agent="wingman">` block. Handle it in this order:

1. **Read `<verdict>` first.** If wingman disagrees with your lean, the
   disagreement is the first sentence. Do not proceed with your original plan
   without addressing it.
2. **Check `<confidence>`.** At `low`, the recommendation is provisional -
   resolve `<missing>` before acting on it.
3. **Run `<user_questions>` immediately.** Put wingman's questions to the user through
   `AskUserQuestion` (up to four questions a call, two to four options each), using the
   options it supplied. This is the point of the call.
4. **Dispatch scouts for `<missing>` items marked `scout`:** code-scout for repository
   facts, web-scout for external documentation. Do those in parallel
   with the user's answer where possible.
5. **Carry `<verify>` into the work.** It is the acceptance criterion for
   whatever gets built next.

Surface `<verdict>`, `<confidence>`, and `<user_questions>` to the user verbatim.
Summarizing an advisor whose whole value is its reasoning defeats the call.

The user decides; this skill is the only tie-break path. When the user cannot choose and
says so ("you pick", "either is fine"), adopt wingman's verdict and record it as the user's
decision to defer to it, in those words. Do not escalate the same packet again.

## Record it

A decision escalated once and then lost to compaction gets escalated again, so persist it
before any work resumes. When an investigation is active, or the ticket's `investigations`
list links one, append it through lets-investigate's ledger. Call
`mcp__plugin_mightymodels_state__investigation` with action `add`:

```json
{"request": {"action": "add", "investigation_id": "ID", "payload": {"request": {"round": 1}, "entries": [{"kind": "decision", "text": "<the choice> (wingman: <verdict, one line>; user: <answer>)", "source": "user"}]}}}
```

`ID` is the investigation's id and the `round` is the ledger's latest one (`investigation`
`render` shows it). With no investigation, say in chat that the decision is not
persisted yet; baton-pass records settled decisions when the session is handed off.

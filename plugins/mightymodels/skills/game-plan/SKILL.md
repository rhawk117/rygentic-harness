---
name: game-plan
description: >-
  Large-scope ramp for an mightymodels ticket: read ticket.yml and the issue, verify the ticket's task claims with scouts, then write .mightymodels/<slug>/plan.md — high-level strategy and enumerated tasks with size hints, deliberately free of code-level citations — and get the user's approval before invoking agents-assemble. Auto-invoke at session start for any scope/plan-first combination other than scope sm with plan-first false (the routing table in docs/workflow.md is canonical); use for "plan this ticket", "run the game plan", "write the plan for issue #N", "ramp the big one". Not for small tickets (inline-sendoff), not a design document or ADR (the plan sequences work on a settled design).
---

# game-plan

The large ramp. Its one structural conviction: **the plan is high-level because citations rot.** A plan written at commit A gets executed across commits B through K; any file:line it carried would be stale by task three and trusted anyway. So the plan carries strategy, sequence, and intent — and the per-task briefs carry fresh citations, compiled at dispatch time by what-we-know inside the loop. Altitude is not vagueness: tasks are still enumerated, sized, and ordered.

## Sequence

**0.** Invoke `using-mightymodels`

**1. Read ticket.yml and the issue first.** these are the ONLY things you are permitted to read without a scout. The plan implements the ticket; a plan written from conversation memory instead of the ticket is the drift you built this system to kill.

**2. Verify the task claims with scouts.** Models from ticket.yml. Each major claim the issue makes about the codebase gets one scout confirmation at HEAD — same discipline as inline-sendoff, scaled to the larger surface. Stale claims are a delta report to the user before planning on top of them.

**3. Write `plan.md`** (~200 lines max):

```markdown
# <slug> — plan
base-intent: <what this unit of work changes, one paragraph>
approach: <the strategy and why it beats the alternative considered>

## Tasks
- T1 (<sm|med|large>): <one-line intent — what and where, no how>
- T2 (<size>): <...>          # order is dependency order

## Non-goals
- <explicitly out of scope, with the one-line why>

## Risks
- <what could force a re-plan, and the early signal>
```

No file:line citations anywhere in it — if you feel the need to cite, that detail belongs in a task's future ASKED stanza, not here. Per-task size hints drive the engineer-tier bumps later. Non-goals are load-bearing: they are what keeps a long sprint from growing sideways while nobody is watching.

**4. Get approval.** Present the plan in chat and wait for the user's yes — this gate is theirs, and it is the last cheap moment to change direction. On approval, invoke agents-assemble. On pushback, revise; the plan is regenerated, not appended to.

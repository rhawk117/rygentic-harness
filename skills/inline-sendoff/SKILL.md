---
name: inline-sendoff
description: >-
  Small-scope ramp for an mightymodels ticket: read ticket.yml and the GitHub issue FIRST, confirm the ticket's claims still hold at HEAD with two or three scouts, write the task checklist into the issue body, then hand control to agents-assemble. Auto-invoke at session start when the active ticket says scope sm and plan-first false; use when picking up a small ticket — "pick up the ticket", "start on issue #N", "kick off the small one". Not the large ramp (scope large or plan-first true goes to plan-work), not for Jira operations, and not for tickets that don't exist yet (prepare-handoff creates them).
---

# inline-sendoff

The small ramp. A sm-scope ticket earned the right to skip plan.md — but not the right to skip confirmation, because the ticket was triaged at one commit and the session starts at another.

## Sequence

**0.** Invoke the `using-mightmodels` skill

**1. Read first, dispatch second.** `ticket.yml`, then the issue (or `.mightymodels/<slug>/issue-body.md` when no forge issue exists). The ticket's `triaged-at` and the claims in the issue are the things to confirm — you are not re-triaging from scratch; the triage session already happened and re-doing it disrespects both its work and this session's budget.

**2. Confirm the claims, bounded.** Two or three scouts (models from ticket.yml), each verifying one ticket claim still holds at HEAD: the cited file still exists at that path, the API still has the shape the issue assumes, the config key is still where triage found it. A claim that no longer holds — file renamed, symbol re-signed, behavior changed since `triaged-at` — is a **delta report to the user before anything starts**, not something to silently adapt around. The user staged this work against a world that has since moved; whether the ticket still makes sense is their call.

**3. Enumerate the tasks.** Write the task checklist into the issue body (`gh issue edit`, or edit `issue-body.md` in place when there is no forge issue). Items are task-sized per the ticket's scope answers — each one a thing agents-assemble can run through the loop with its own ASKED stanza. The issue becomes the progress view: agents-assemble checks items off as tasks close, and anyone watching the issue watches the sprint.

**4. Hand off.** Invoke agents-assemble. This ramp adds no other artifacts — the small path's whole value is that ticket.yml plus an issue checklist is enough.

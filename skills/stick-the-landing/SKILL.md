---
name: stick-the-landing
description: >-
  Close an mightymodels sprint: push the branch, dispatch gitty-up to open the PR with the repo's template and watch CI, route failures — mechanical fixes obvious from the log tail to budgetron, non-obvious causes to whats-broken — and on green offer to generate the thin handoffs/REVIEW.md for the review session. Use when all sprint tasks are done and the user says finish, wrap up, ship it up, push and open the PR — "finish the sprint", "stick the landing", "wrap up the ticket", "get the PR open". Not the deep review itself (review-circus), and not for mid-sprint work (agents-assemble owns the loop).
---

# stick-the-landing

The bridge from "work done" to "work reviewable". It exists as its own stage so the user gets a look between the sprint's last commit and anything public — and so CI failures get routed by *cause type*, not handled by whoever happens to be cheapest.

**Precondition:** `REPORT.md` exists and the sprint's tasks are checked off. Missing → this is a agents-assemble session that stopped early; say so rather than papering over it.

## Sequence

**1. Push.** The sprint's commits go up. Rejected push → report the rejection and stop; never force-push around it.

**2. Dispatch gitty-up** (model from ticket.yml) to open the PR — repo template, linking the issue — and watch CI. Its report comes back `pass`/`fail`/`error` with per-check buckets and the last-60-line log tails on failure. If `gh` is unavailable, write the PR body to `handoffs/pr-body.md` and surface the command; CI watching resumes when the PR exists.

**3. Route failures by the log-tail test.** For each failing check: *can the fix be stated as one Fix:/Verify: line from the log tail alone?*

- **Yes — mechanical.** Lint rule, formatter drift, missing import, trivially wrong assertion. Dispatch **budgetron** with the Fix:/Verify: verbatim; its commits push so CI re-runs.
- **No — non-obvious.** Behavioral test failure, flake that isn't obviously a flake, anything where you'd be guessing the cause. Invoke **whats-broken** — the phased protocol exists precisely so the cheapest worker doesn't symptom-patch CI into a worse state.

After any fix lands, gitty-up re-watches. Two failed fix rounds on the *same check* → stop and escalate to the user with both attempts' evidence; a third quiet round is thrash with better manners.

**4. On green:** notify the user, then offer to generate `handoffs/REVIEW.md` — thin per the handoff rule (point at ticket.yml, the issue, the PR; name review-circus and the reviewer models' source; nothing copied). The review session runs on a mid-tier primary; say so in the offer.

`error` from gitty-up (checks absent, unresolvable PR) is the user's news too — never treated as pass, never retried into meaninglessness.

---
name: review-circus
description: >-
  Endgame review session for an mightymodels ticket, a branch, or the whole codebase: scouts triage the review surface, uncle-bob and merge-vader run with models from ticket.yml writing reports under .mightymodels/<slug>/review/, findings are deduped and severity-unified through the shared table, an abridged human-friendly comment is ALWAYS posted to the PR — pass or fail — and worth-fixing triage routes remediation by risk first (Critical findings and High+ security findings to a full engineer regardless of source), then by source: remaining uncle-bob findings to a full engineer, remaining merge-vader findings to budgetron. Use when a PR is green and awaiting the deep pass — "run the review circus", "full review pass", "review the sprint", "both reviewers on this". For a single quick review, invoke merge-vader or uncle-bob directly instead.
---

# review-circus

The endgame. Two reviewers with different worldviews run in parallel, and this session's primary is the ringmaster: it aggregates, it translates severities into one language, it documents, and it routes fixes. It never reviews code itself and never invents findings — an empty `review/` directory means the reviewers haven't run, not that the primary should improvise.

Severity table and finding format come from `agents-assemble/references/contracts.md`. Read it before aggregating; the whole point of this session is that MV and UB findings land in one vocabulary.

## Sequence

**1. Scope.** Ask the user: this branch (against which base), or the entire codebase? Branch mode reviews the sprint; codebase mode is a health pass — the mechanics below are identical, only the reviewers' scope changes.

**2. Surface triage.** Scouts (models from ticket.yml) establish what the reviewers will want fast: diff stat, risk hotspots (auth, input handling, CI config, dependency manifests), test-file coverage of the changed area. This shortens the reviewers' own recon, not replaces their judgment.

**3. Dispatch both reviewers in parallel** — uncle-bob and merge-vader, models from ticket.yml's `subagent-models` block, reports to `.mightymodels/<slug>/review/`. Give merge-vader the plan/issue for its conformance check (a "not supplied" conformance section when the issue exists is a worse report for no reason). Wait for both.

**4. Aggregate.** Dedupe by file:line overlap; map severities through the contracts table (UB `Blocker` → Critical). Same defect at two severities → the higher wins, both noted; a gap of two-plus levels goes to the user's judgment rather than silent resolution. Every surviving finding keeps its provenance (MV-n / UB-n) and its Fix:/Verify: lines — a finding an engineer can't act on without re-deriving the analysis is a finding half-delivered.

**5. Comment the PR — always.** Pass or fail, low-findings-only or Critical-laden: an abridged, human-friendly summary goes on the PR (prose through humanizer; IDs preserved so the thread links back to the reports). The PR thread is the durable record; the review/ files are working state. `gh` unavailable → write `review/pr-comment.md` and surface the command.

**6. All-clear rule.** Only Low findings → report all clear, comment posted, session done.

**7. Worth-fixing triage** (anything Medium+). Per finding, scouts establish: pre-existing defect or regression from this branch? Blast radius and scope of the fix? Then the judgment — worth fixing now, ticketed for later, or accepted risk with the user's sign-off.

**8. Remediation, routed by risk first, then source.** Risk takes precedence: a **Critical** finding, or a **security finding at High severity or above** (severities per the contracts table), routes to a full **engineer** regardless of which reviewer found it — a defect that says "harm now" never waits on a budgeted fixer's escalation round trip. Below that line, source decides: uncle-bob findings → full **engineer** (abstraction and structure work needs judgment); merge-vader findings → **budgetron** (implicit-but-straightforward fixes with consumable Fix:/Verify: lines). A dual-provenance finding — one both reviewers flagged — routes to the engineer: when the structure judge saw it too, the fix is rarely mechanical. The budgetron contract remains the safety valve for everything routed to it: a merge-vader finding that turns out non-straightforward escalates on budget or scope and re-routes to an engineer. Remediation runs the normal loop with two deltas: engineer commits are **pushed** (CI must not regress silently) and gitty-up watches. Two remediation rounds per finding, then accepted-risk-or-escalate — never a third quiet round.

**9. Close.** Updated comment on the PR with remediation outcomes per finding ID. The human review comes after this session — say so, and stop.

---
name: stick-the-landing
description: >-
  Close an mightymodels sprint: gate the push on the task tool's ready action, push, open the PR
  with a checked body, have gitty-up watch CI, and route each failing check as a recorded C task
  (mechanical fixes to an engineer residual, then architect once; non-obvious causes to
  whats-broken), re-proving the whole verification contract at every new HEAD before re-pushing.
  On green, ask through AskUserQuestion whether to review now (review-circus) or hand off (baton-pass).
  Not for Jira sprint operations, not the review itself
  (review-circus), and not for mid-sprint work (agents-assemble owns the loop).
when_to_use: >-
  Only the user starts it, when the
  sprint's tasks are done: "finish the sprint", "wrap up the ticket", "push and open the PR",
  "get the PR open", "ship it up".
argument-hint: "[ticket-slug]"
disable-model-invocation: true
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_state__contract
  - mcp__plugin_mightymodels_state__task
---

# stick-the-landing

The bridge from "work done" to "work reviewable". It is its own stage so the user gets a look
between the sprint's last commit and anything public, and so CI failures are routed by cause,
not handled by whoever is cheapest.

Run from the repository root. Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}` in this file as
an absolute path:

- `mcp__plugin_mightymodels_state__task` for task state and the push gate.
- `mcp__plugin_mightymodels_state__contract` for the verification contract, and
  `mightymodels verify run` to run its commands.
- `python3 "${CLAUDE_PLUGIN_ROOT}/skills/open-ticket/scripts/humanize_tracker_body.py"` for the PR body.

Dispatch workers through prompting-subagents. Models are the fixed aliases `subagent-models`
lists, never memory.

**Argument:** the ticket's slug, given when the skill was started: "$ARGUMENTS". Empty quotes mean
none was given, and the ticket is the session's active one.

## 1. Gate

`REPORT.md` must exist: agents-assemble writes it as its last act, so its absence means the
loop stopped early. Say so and stop rather than papering over it. Then call
`mcp__plugin_mightymodels_state__task` with action `ready`:

```json
{"request": {"action": "ready", "slug": "SLUG"}}
```

It answers `ready` only when a plan task has been started, every plan task is verified or
superseded, no C or R task is failed or blocked, and every live contract command passed at the
current HEAD; otherwise it answers `not ready` and lists the reasons. When the only reasons are
receipts not at HEAD (commits landed after the last verification), run the whole contract once
and re-check:

```bash
mightymodels verify run --slug SLUG --all --phase landing
```

Any other reason is the loop's unfinished work: list the reasons and send the user back to
agents-assemble. Nothing is pushed on old evidence.

## 2. Push and open the PR

The primary pushes the branch. A rejected push is reported and the skill stops; never force-push around it.

Write the PR body to `.mightymodels/SLUG/pr-body.md`: the repository's pull request template
(`.github/pull_request_template.md` or `.github/PULL_REQUEST_TEMPLATE/`) filled from REPORT.md,
linking the issue (`Closes #N` for a GitHub issue; the Jira key where the repository's
convention puts it). Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/open-ticket/scripts/humanize_tracker_body.py" fix .mightymodels/SLUG/pr-body.md --shape comment
```

Reword what `fix` reports, then run `check` with the same shape until it exits 0. Open the PR
with `gh pr create --body-file .mightymodels/SLUG/pr-body.md`. When `gh` is unavailable or
fails, surface the exact command and stop; CI watching resumes once the PR exists.

## 3. Watch CI

Dispatch gitty-up with the PR number and nothing else ("Watch PR 214."); it resolves the rest
itself and never touches code. Its report is `pass`, `fail` with per-check findings and log
tails, or `error`. An `error` (no checks, still pending, unresolvable PR) is the user's news:
never treated as a pass, re-watched at most once.

## 4. Route each failing check

One C task per failing check (`C1`, `C2`, ...); checks that fail on the same log line share
one. Apply the log-tail test: *can the fix be stated as one Fix:/Verify: line from the log
tail alone?*

- **Yes, mechanical** (lint rule, formatter drift, missing import, a trivially wrong
  assertion). Record the attempt with `mcp__plugin_mightymodels_state__task` and action
  `start`, then dispatch an **engineer** with the residual variant of its template,
  Fix:/Verify: verbatim:

  ```json
  {"request": {"action": "start", "slug": "SLUG", "payload": {"task_id": "C1", "change": {"by": "engineer", "owned": ["<files the log tail names>"]}}}}
  ```

  When a local command reproduces the check, it is the Verify line and becomes contract id
  `C1.AC-1`, shown to the user in one `AskUserQuestion` dialog and recorded with `contract`
  `approve` before the dispatch. Otherwise the Verify line is the CI check
  itself, proven after the re-push.

- **No, non-obvious** (a behavioral failure, a flake that is not obviously a flake, anything
  where the cause would be a guess). Invoke **whats-broken**; the phased protocol exists so
  the cheapest worker does not symptom-patch CI into a worse state. Its fix dispatch is the C
  task's engineer attempt, recorded with `task` `start` the same way.

## 5. Re-prove, then re-push

A fix commit moves HEAD, so every receipt is stale. Before any push:

```bash
mightymodels verify run --slug SLUG --all --phase landing
```

Then `task` `ready`, as in step 1. A C task still in progress does not block `ready`, since its
proof is the CI run the push starts; a failing contract command does. When `run --all` fails on
a `T` or `I` id, the CI fix broke verified work: `task` `mark` with `payload` `task_id` `C1` and
`change` `to` `failed` and `reason` `"<id> regressed"`, and climb (step 6). Never push past it.

Push, then gitty-up re-watches.

## 6. Close or climb

- **The check passes.** Close the C task on the evidence of the check it repaired, with
  `mcp__plugin_mightymodels_state__task` and action `verify`:

  ```json
  {"request": {"action": "verify", "slug": "SLUG", "payload": {"task_id": "C1", "change": {"commit": "<fix commit>", "assertions": {"AC-1": "<check link from gitty-up>"}}}}}
  ```

  Any `C1.*` contract command must also have passed at HEAD; the commit must stay inside the
  owned set.

- **The check still fails**, or the engineer returns `failed` or `blocked`.
  `task` `mark` with `to` `failed` or `blocked` and a `reason` (a task the gate blocked already
  is `blocked`), then **architect** once (`task` `start` with `by` `architect`, the architect
  template with the trigger and the failing tail). The architect also failing goes to
  **whats-broken**; the `task` tool refuses a second architect implementation pass on its own. whats-broken's own stop rules end at the user,
  with every attempt's evidence.

After a compaction, `task` `show` and `contract` `status` (each with `slug`) and `gh pr view`
are the state; the conversation is not.

## 7. On green

Every check passes and `task` `ready` answers `ready` at the pushed HEAD. Tell the user, then
ask once through `AskUserQuestion` (up to four questions a call, two to four options each):

- **Review now**: invoke review-circus in this session. Recommended when this session runs a
  mid-tier primary and has context to spare.
- **Hand off**: invoke baton-pass, which prints the review session's prompt with review-circus
  as the skill to invoke.

## Boundaries

stick-the-landing pushes, opens the PR, and records C tasks. It never force-pushes, merges,
comments on the PR (review-circus owns that), or edits code itself: every fix is a dispatch
gated by the `task` tool. Every fallback (PR body drafted but not opened, push rejected, CI
`error`) is named in the closing summary.

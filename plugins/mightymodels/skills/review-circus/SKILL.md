---
name: review-circus
description: >-
  Review a diff, branch, ticket, or whole codebase with the mightymodels persona reviewers. One
  AskUserQuestion gate sets depth (quick runs its reviewers on sonnet, standard and deep on opus), persona
  emphasis, and scope; the `review` tool records the run, mightymodels review-metrics and review-signals
  measure, merge-vader and uncle-bob report, and the tool reads their reports
  and merges overlapping findings, presented by id through AskUserQuestion. Only the findings
  the user picks go to remediation, risk first, through the `task` tool; an abridged PR comment
  is always posted. Not for fixing CI (stick-the-landing) or mid-sprint work
  (agents-assemble).
when_to_use: >-
  Use for
  "run the review circus", "review the sprint", "full review pass", "both reviewers on this", and
  for a quick single-persona pass: "quick merge-vader on this branch", "uncle-bob this module",
  "is this safe to merge".
argument-hint: "[diff | branch | ticket <slug> | codebase]"
allowed-tools:
  - AskUserQuestion
  - mcp__plugin_mightymodels_state__review
  - mcp__plugin_mightymodels_state__task
---

# review-circus

Two reviewers with different worldviews, and this session's primary as the ringmaster: it
sets the profile, measures, dispatches, normalizes, and routes what the user chooses to fix.
It never reviews code itself and never invents a finding. An empty run means the reviewers
have not reported, not that the primary should improvise.

Run the scripts from the repository root. `${CLAUDE_SKILL_DIR}` is this skill's directory, which
Claude Code substitutes in this file as an absolute path. Subagents do not inherit it, so every
path a dispatch carries is absolute.

- `mcp__plugin_mightymodels_state__review` records the run, the findings, and the decisions.
- `mightymodels review-metrics` measures structure (fan-in, fan-out, cycles, sizes); it is a bare Bash command (the plugin's `bin/` is on the Bash PATH).
- `mightymodels review-signals` measures git history (churn, coupling, hotspots); it is a bare Bash command (the plugin's `bin/` is on the Bash PATH).

Read `references/profiles.md` and `references/review-state.md` before the first run in a
session, and `agents-assemble/references/contracts.md` for the severity table. Dispatch every
worker through prompting-subagents.

## 1. Profile

**Argument:** the scope to review (diff, branch, ticket with its slug, or codebase), given when the
skill was started: "$ARGUMENTS". Empty quotes mean none was given, and the scope is settled as
below.

The profile is the scope, the depth and the emphasis of the review. Say what each depth costs
(profiles.md): quick is one persona on sonnet, standard and deep run their reviewers on opus.
Then record the profile with `mcp__plugin_mightymodels_state__review` and action `start`,
carrying only what the conversation has already settled. The tool puts each of `scope`, `depth`
and `emphasis` that the payload leaves out to the user and starts the run with the answers:

```json
{"request": {"action": "start", "payload": {"scope": "ticket", "slug": "SLUG", "base": "main"}}}
```

An answer starting `needs input` means no one could be asked through the tool: put each question
it names to the user in one `AskUserQuestion` dialog, then call again with those arguments in the
payload. A scope of branch needs `base`, a scope of ticket needs `slug`, and an emphasis of custom
needs `weights`; a refusal naming one of them means: ask the user for it, then call again.

For a quick review with balanced weights, ask the user which persona and pass it as `persona`.

It answers with the run id, the run directory, and each persona's model. Every later step
names the run with `run_id`.

A run may spend one override on its heavier-weighted reviewer (the first persona, merge-vader, on equal weights), moving it to fable. Ask for it only when the user wants the strongest reviewer, with action `override`:

```json
{"request": {"action": "override", "run_id": "20261005-103000"}}
```

The answer names the reviewer and says to dispatch it with effort high; a second request on the run is refused. A ticket's reviewer keys change no review.

## 2. Measure

When uncle-bob is in the run, measure structure into the run directory:

```bash
mightymodels review-metrics <repo root> --out RUNDIR/uncle-bob-metrics.json
```

Add `--package-depth 2` when the repository is one top-level package. When the languages are
ones it does not parse (it reads Python, JavaScript, and TypeScript), skip it and say so in
the dispatch.

At standard and deep, pick the history window for `mightymodels review-signals` per profiles.md
(`--baseline-ref BASE_REF` for branch and ticket scope). At standard and deep, a code-scout
surface triage also runs first: diff stat, risk hotspots (auth, input handling, CI config,
dependency manifests), tests covering the changed area. Quick skips both unless the persona
names a specific gap.

## 3. Dispatch the personas

Dispatch each persona in the run, in parallel, with prompting-subagents' reviewer template
and the model the run recorded. Each persona preloads its doctrine as a skill of its own
(`becoming-merge-vader`, `becoming-uncle-bob`) and is passed no doctrine path. The packet carries
`${CLAUDE_SKILL_DIR}/references/profiles.md`, `${CLAUDE_SKILL_DIR}/references/idiom-evidence.md`,
the run directory, the depth and the persona's role (the heavier weight leads), the metrics
path, the signals history window (which the persona hands qualitylens), and for a ticket,
ticket.yml, the issue, and the plan
(merge-vader's conformance check needs them). The `${CLAUDE_SKILL_DIR}` paths are absolute once substituted.

Personas gather their own evidence through code-scout, web-scout, and qualitylens, and
nothing else. Write each response unchanged to `RUNDIR/MERGE-VADER-REPORT.md` or
`RUNDIR/UNCLE-BOB-REPORT.md`, the files `add` reads. Wait for every persona in the run.

## 4. Record the reports

Call `mcp__plugin_mightymodels_state__review` with action `add`, once per persona in the run:

```json
{"request": {"action": "add", "run_id": "20261005-103000", "payload": {"persona": "merge-vader"}}}
```

The tool reads that persona's report itself, so no step retypes a finding, and one finding it
refuses rejects the batch with the reason and stores nothing. A quality finding at Medium or
above needs typed evidence (idiom-evidence.md): lower it to Low or find the evidence, never
relabel it a defect. A security question a reviewer left UNKNOWN-BLOCKED belongs in its report
as a High finding in the `security` dimension whose Fix is to answer it, since CLEAR is
impossible while it stands. Overlapping findings merge in the tool, and a two-level severity
gap is flagged for the user. When `add` answers that findings are `back to undecided`, show
the gate again and call `dispose` for them again before any remediation continues.

## 5. The finding gate

Always, when any finding exists. Show the user the `review` answer to action `gate`: findings
by severity, security first, then by persona weight, with sources, location, any severity
conflict, and the decision so far. Then take the findings one at a time, in gate order. For each
`Fn`, call `mcp__plugin_mightymodels_state__review` with action `dispose` and `finding` and no
`decisions`; the tool asks the user what to do with that finding and records the answer. Two of
the choices need a reason, which the tool asks with the choice. A severity conflict is settled
here by the decision the user makes about it:

```json
{"request": {"action": "dispose", "run_id": "20261005-103000", "payload": {"by": "user", "finding": "F1"}}}
```

The answer says which findings are still undecided. An answer starting `needs input` means no one
could be asked through the tool: put the question it names to the user in one `AskUserQuestion`
dialog, then call again with `decisions` for that finding (several findings may go in one call):

```json
{"request": {"action": "dispose", "run_id": "20261005-103000", "payload": {"by": "user", "decisions": {"F1": {"decision": "fix"}, "F2": {"decision": "accept-risk", "reason": "..."}}}}}
```

Nothing the user did not pick is remediated.

## 6. Comment the PR, always

Pass or fail, one finding or twenty: render the report and the abridged comment, check the
comment, and post it. `mcp__plugin_mightymodels_state__review` with action `report` returns
text and writes no file, so the primary writes the full report (the call without `payload`) to
`RUNDIR/report.md` and this call's answer to `RUNDIR/pr-comment.md`:

```json
{"request": {"action": "report", "run_id": "20261005-103000", "payload": {"shape": "comment"}}}
```

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/open-ticket/scripts/humanize_tracker_body.py" fix RUNDIR/pr-comment.md --shape comment
gh pr comment <PR> --body-file RUNDIR/pr-comment.md
```

Reword whatever `fix` still reports; the finding ids stay so the thread links back to the
report. Without `gh` or a PR, keep the file and surface the command. With nothing chosen for
fixing, the session ends here with the verdict `report` returned.

## 7. Remediate, risk first

Remediation needs a ticket, because its proof lives in the ticket's verification contract. In
a codebase or branch run without one, offer open-ticket with the chosen findings as the
rollup, and stop.

Order: Critical findings and High security findings first, then the rest in gate order. For
each finding `Fn` chosen for fixing:

1. `task` `start` with `payload` `task_id` `Rn` and `change` `by` `engineer` and `owned` the
   files the Fix touches (agents-assemble's call).
2. The finding's Verify command goes to the user as contract id `Rn.AC-1` in one
   `AskUserQuestion` dialog, then `contract` `approve` with it as a `commands` entry (game-plan's call).
3. Dispatch an **engineer**: the residual variant for a single-concern merge-vader finding
   with usable Fix and Verify lines; the full template for uncle-bob findings, findings both
   personas raised, and anything Critical or High security.
4. `mightymodels verify run --slug SLUG --phase review --id Rn.AC-1`, then `task` `verify` with
   `payload` `task_id` `Rn` and `change` `commit`, then `review` `resolve` with `payload`
   `finding` `Fn`, `result` `fixed` and `commit` (it takes only a finding the user chose to fix).
5. Failed or blocked: `task` `mark` (a task the gate blocked already is `blocked`), then
   **architect** once, then whats-broken, as in agents-assemble. Record `resolve` with `result`
   `failed` or `blocked` and a `reason` when a finding stops.

A finding whose reviewer wrote an Architect escalation line (a design decision beyond its
Fix) is a question for the user first. On their yes, dispatch architect in diagnose-replan
mode; its revised plan goes back to agents-assemble as new tasks, not into this loop.

Before every push: `mightymodels verify run --slug SLUG --all --phase review` and `task`
`ready`, as stick-the-landing does, then push (only the primary pushes) and dispatch gitty-up
with the PR number to watch CI.

## 8. Close

Re-render with `report` in both shapes, rewrite the two files, and replace the PR comment
(`gh pr comment <PR> --edit-last --body-file RUNDIR/pr-comment.md`) so it shows each finding's
outcome by id. The human review comes after this session; say so, and stop.

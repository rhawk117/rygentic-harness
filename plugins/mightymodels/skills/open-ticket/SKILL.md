---
name: open-ticket
description: >-
  Turn an understood problem into a staged unit of work: one AskUserQuestion interview (slug,
  tracker GitHub / Jira / both / none), then the
  ticket directory, a Findings rollup from the lets-investigate ledger or what-we-know, the
  GitHub issue and/or Jira ticket (a draft file when the CLI is absent) with a checked tracker
  body, the branch, ticket.yml with derived model routing, and a validated ticket row in the
  state database. Ends by asking whether to plan now (game-plan), go straight to one-shot, or
  hand off (baton-pass). Use when triage is done: "cut a ticket for this", "open a ticket",
  "make a jira ticket under this epic", "turn this investigation into a ticket", "stage this
  for the next session", "get this ready to implement". Not for starting the implementation
  itself (game-plan or one-shot), and not for handing off an existing ticket (baton-pass).
---

# open-ticket

Turn an understood problem into a unit of work that this session or a later one can pick up
cold. Everything durable lands in `ticket.yml`, the ticket's row in the state database, and the
tracker; what happens next is the user's call, asked at the end.

Read `references/ticket-schema.md` and `references/mightymodels-dir.md` before the first run
in a session; they are the contract this skill instantiates. State goes through the plugin's MCP
tools, called by full name: `mcp__plugin_mightymodels_state__ticket`, `..._investigation`.

Nothing under `.mightymodels/` is ever tracked by git. The state server adds `.mightymodels/`
to the repository's local exclude file when it starts, so a `git add -A` cannot ship briefs,
reports, or the database, which may carry raw command output.

## The interview

One `AskUserQuestion` dialog containing only the questions the conversation has not already
answered. Each
question carries two to four options, and the user can always type an answer of their own.
Answers already given are confirmed in the summary, not re-asked.

1. **Name** this unit of work; options: a slug proposed from the triage target, a shorter one.
2. **Tracker**: GitHub issue, Jira ticket, both, or none.

The branch, the compaction and the scope of each anticipated task are not asked here: the
`ticket` `write` call (step D) leaves them out and asks the user itself.

When the tracker answer includes Jira, ask once, in chat, for the fields in one line: project
key, parent epic, issue type, story points, labels. Take whatever the user gives ("under
PLAT-40, story, 3 points" is a complete answer) and leave the rest unset; the CLI's defaults
and the project's own scheme fill them.

When the caller is baton-pass, the next step is already decided (hand off); do not ask it at
the end.

## The rollup

The tracker body is built from the triage, not from memory of it. Take the findings in this
order of preference:

1. **The investigation ledger.** Call `mcp__plugin_mightymodels_state__investigation` with
   action `knowns`:

   ```json
   {"request": {"action": "knowns", "investigation_id": "ID"}}
   ```

   With action `list` when the id is unknown:

   ```json
   {"request": {"action": "list"}}
   ```

   Rows marked `current` are findings. Rows marked `lead` were cited at an older HEAD: they go
   under Open questions as "unverified at HEAD", never under Findings, because the ramp would
   otherwise re-verify the wrong things.
2. **The final what-we-know output** in the conversation.
3. **Cited facts** scattered in the conversation.

From it:

- **Findings**: each current known with its citation, and each user decision. A claim without
  a citation goes under Open questions.
- **`context`** in ticket.yml: one to six lines carrying the knowns and decisions the next
  session cannot afford to lose, without `file:line` (locations rot; the tracker body keeps
  them and the ramp re-verifies them at HEAD).
- **`reference_urls`**: the ledger's resources, external documentation only.
- **`investigations`**: the investigation id, so the work unit links its ledger.

If no triage exists, say so and write the body from what the user has stated, with every
unverified claim marked as such. A ticket that presents guesses as findings sends the next
session confirming the wrong things.

## The actions

**A. Tracker body.** Fill `assets/tracker-body.md` from the rollup into
`.mightymodels/SLUG/issue-body.md`: Summary, Findings, Open questions, Acceptance as checkable
criteria where the triage established them, and a Security surface section only when the
change crosses a trust boundary, adds an input source, or touches authz or secrets (two to five
abuse cases phrased as candidate acceptance criteria; omit the section otherwise, since
inventing threats for a docs change teaches readers to skip the section that matters). Then:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/humanize_tracker_body.py" fix .mightymodels/SLUG/issue-body.md
```

`fix` repairs dashes and filler openers itself and reports what still needs rewording (tell
words, uncited findings, placeholders, missing sections). Reword those, then run `check` until
it exits 0. No body reaches a tracker before it passes.

**B. Tracker.**

- *GitHub issue.* Discover the repo's conventions first: templates under
  `.github/ISSUE_TEMPLATE/`, labels in recent issues, title style from `gh issue list`. Create
  with `gh issue create --body-file .mightymodels/SLUG/issue-body.md`. If `gh` is unavailable
  or fails, keep the file and surface the exact command.
- *Jira ticket.* Check for the `jira` CLI with `command -v jira`. When present, discover the
  create command's flags from `jira issue create --help` rather than assuming them (custom
  fields such as story points are mapped per installation), then create with the fields the
  user gave and the checked body. When the CLI is absent or the create fails, write
  `.mightymodels/SLUG/jira-ticket.md` carrying the fields as a header block, the body, and the
  exact command, and say so in the summary.
- *Both.* Create the GitHub issue first, then the Jira ticket with the issue URL in its body,
  so the two link one way and the sprint's task list has one home (the GitHub issue).

**C. Branch.** Do this after D, because the branch is the user's answer to D's question: read
`branch-name` from ticket.yml. When it is not the current branch, create it from HEAD and push
it; a rejected push (no remote, no auth) is a note in the summary, not a blocker, since the
branch exists locally. When it is the current checkout, create nothing. A detached HEAD is not a
checkout the sprint can run on; the tool refuses it, so ask the user for a branch name and call
`write` again with `branch` in `fields`.

**D. ticket.yml.** Call `mcp__plugin_mightymodels_state__ticket` with action `write` and
the rollup and tracker answers under `fields`, and no `scope`, `compaction` or `branch`; the tool
asks the user for those three:

```json
{"request": {"action": "write", "slug": "SLUG",
 "fields": {"summary": "...", "context": ["...", "..."], "issue": 42, "jira": "PLAT-41",
            "reference_urls": ["https://..."], "investigations": ["20260928-..."]}}}
```

An answer starting `needs input` means no one could be asked through the tool: put each question
it names to the user in one `AskUserQuestion` dialog, then call again with those arguments in
`fields` (`scope`, `compaction`, and `branch` as the current branch name or the new branch name).

The tool derives the model routing from the scope and `plan-first` from the compaction answer,
per the schema, and refuses to overwrite an existing ticket.yml. Tell the user the file exists
and pause: they tweak it by hand before anything else happens, and their
edit wins over the derivation.

**E. Validate and stage.** After the tweak pass:

Call `mcp__plugin_mightymodels_state__ticket` with action `validate`:

```json
{"request": {"action": "validate", "slug": "SLUG"}}
```

It parses ticket.yml in the canonical subset the schema describes, checks every field and every
linked investigation, and stages the ticket as a row in the state database. A hand edit outside
the subset is reported with its line; fix it rather than working around it. The ticket is not
staged until this passes.

## What next

Ask once, through `AskUserQuestion`:

- **Plan now**: invoke game-plan in this session. Recommended when `plan-first` is true and the
  context has room for it.
- **One-shot now**: invoke one-shot in this session for a small, well-understood ticket.
- **Hand off**: invoke baton-pass, which writes the next session's prompt.

Close with a summary of what exists and every fallback taken.

## Failure honesty

Every fallback gets surfaced in the closing summary: issue drafted-not-created, Jira ticket
drafted-not-created, branch unpushed, template not found, no triage found to roll up, body
checks still failing, validation not passed. A ticket that silently pretends its side effects
happened strands the next session; the summary is part of the artifact.

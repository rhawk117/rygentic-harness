---
name: prepare-handoff
description: >-
  Bridge from an understood problem to a ready-to-start unit of work. One ask-user interview
  (slug, tracker: GitHub issue / Jira ticket / both / none, branch: current checkout or new,
  compaction likely, per-task scope), then: the ticket directory, a triage rollup lifted from
  what-we-know or the lets-investigate ledger into the issue's Findings section and
  ticket.yml context lines, the GitHub issue via gh and/or the Jira ticket via the jira CLI
  (epic, type, points, labels as the user gives them; a draft file when the CLI is absent),
  every body run through the humanizer skill, the branch created or the current checkout
  recorded, ticket.yml with derived model routing, and a thin handoffs/SPRINT.md. Use whenever
  triage is done and the user wants to stage the next session: "prepare the handoff", "cut a
  ticket for this", "make a jira ticket under this epic", "set this up for the next session",
  "get this ready to implement". Not for starting the implementation (that is the next
  session's ramp: yolo or game-plan).
---

# prepare-handoff

Turn an understood problem into a unit of work another session can pick up cold. Everything
durable lands in `ticket.yml` and the tracker; the handoff prompt stays thin because the next
session reads those first.

Read `references/ticket-schema.md` and `references/mightymodels-dir.md` before the first run in
a session; they are the contract this skill exists to instantiate.

## The interview

One ask-user dialog, batched where the tool allows (five sequential dialogs is an
interrogation), containing only the questions the conversation has not already answered.
Answers already given are confirmed in the summary, not re-asked.

1. **Name** this unit of work; propose a slug from the triage target.
2. **Tracker**: GitHub issue, Jira ticket, both, or none.
3. **Branch**: use the current checkout as-is, or create a new branch (propose a name; base
   defaults to HEAD).
4. **Compaction**: would implementing this likely cause at least one compaction?
5. **Scope** of each anticipated task: sm, med, or large.

Answers 4 and 5 derive `plan-first`, the primary-tier hint, and the engineer model per the
schema's rules.

When the tracker answer includes Jira, ask once, in chat, for the fields in one line: project
key, parent epic, issue type, story points, labels. Take whatever the user gives ("under
PLAT-40, story, 3 points" is a complete answer) and leave the rest unset; the CLI's defaults
and the project's own scheme fill them, and a second dialog for fields the user did not care
to name is the interrogation the batching rule exists to prevent.

## The rollup

The issue or ticket body is built from the triage, not from memory of it. Take the findings
in this order of preference: the final what-we-know output; the last lets-investigate ledger;
cited facts scattered in the conversation. From it:

- **Findings** (body section): each known with its citation, each decision the user made
  with the round it was made in, each open question that would change the approach. A claim
  without a citation goes under open questions, not findings.
- **`context:`** in ticket.yml: three to six lines carrying the knowns and decisions the next
  session cannot afford to lose, without `file:line` (locations rot; the issue body keeps them
  and the ramp re-verifies them at HEAD).
- **`companion-docs.reference-urls`**: the Resources list from the ledger, external
  documentation only.

If no triage exists in the conversation, say so and write the body from what the user has
stated, with every unverified claim marked as such. A handoff that presents guesses as
findings sends the next session confirming the wrong things.

## The actions

**A. Ticket directory.** `mkdir -p .mightymodels/<slug>/handoffs`, then the ignore ritual
from mightymodels-dir.md (idempotent; run it every time).

**B. Tracker.** Draft one body: summary, Findings from the rollup, acceptance as checkable
criteria where the triage established them, and a **security surface** section only when the
change touches a trust boundary, a new input source, or authz/secrets handling (boundaries
crossed and two to five abuse cases phrased as candidate acceptance criteria; when there is
no surface delta, omit the section, since inventing threats for a docs change teaches readers
to skip the section that matters). Invoke the `humanizer` skill on the body prose before it
goes anywhere; every tracker body, GitHub or Jira, drafted or created, passes through it.

- *GitHub issue.* Discover the repo's conventions first: templates under
  `.github/ISSUE_TEMPLATE/`, labels in recent issues, title style from `gh issue list`. Create
  with `gh issue create`; record the number in `companion-docs.issue-number`. If `gh` is
  unavailable or fails, write the body to `.mightymodels/<slug>/issue-body.md` and surface
  the exact command.
- *Jira ticket.* Check for the `jira` CLI with `command -v jira`. When present, discover the
  create command's flags from `jira issue create --help` rather than assuming them (custom
  fields such as story points are mapped per installation), then create with the fields the
  user gave: project, parent epic, type, points, labels, the humanized body. Record the key in
  `companion-docs.jira-key`. When the CLI is absent or the create fails, write
  `.mightymodels/<slug>/jira-ticket.md` carrying the fields as a header block and the body,
  plus the exact command the user would run, and say so in the summary.
- *Both.* Create the GitHub issue first, then the Jira ticket with the issue URL in its body,
  so the two link one way and the sprint's checklist has one home (the GitHub issue).

**C. Branch.** *New*: create and push it; a rejected push (no remote, no auth) is a note in the
summary, not a blocker, since the branch exists locally. *Current checkout*: record the
current branch name in `branch-name` and create nothing. A detached HEAD is not a checkout the
sprint can run on; say so and ask for a branch.

**D. ticket.yml.** Emit per `references/ticket-schema.md`: `engineer`, `plan-first`, and
`scope` from the answers, `context` and `reference-urls` from the rollup, the tracker keys
from step B, `branch-name` from step C. Tell the user the file exists and pause: they tweak it
by hand before anything else happens, and their edit wins over your derivation.

**E. handoffs/SPRINT.md.** Written last, after the tweak pass.

## The handoff

After the user is done tweaking, offer: "Generate a prompt to begin the next session?" On yes,
invoke the `promptlint` skill and write `handoffs/SPRINT.md`, reading the tweaked yaml, never
your original draft. The thinness rule from mightymodels-dir.md applies absolutely: the file
points at ticket.yml and the tracker item(s), names the ramp per the routing table in
`docs/workflow.md` (`yolo` only for sm with plan-first false), and stops. Any fact copied into
it is a fact that can drift.

```markdown
# Handoff for <slug>

<important>YOU MUST invoke `using-mightymodels`</important>

## Handoff Content

<!-- The next session reads these first, so they must be correct. -->
```

Close with "the task is ready for handoff", and when plan-first is true add "switch models in
your next session" (the plan gets written by a low-tier primary; the yaml carries the hint).

## Failure honesty

Every fallback gets surfaced in the closing summary: issue drafted-not-created, Jira ticket
drafted-not-created, branch unpushed, template not found, no triage found to roll up. A
handoff that silently pretends its side effects happened strands the next session; the
summary is part of the artifact.

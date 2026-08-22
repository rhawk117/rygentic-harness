---
name: prepare-handoff
description: >-
  Bridge from an understood problem to a ready-to-start unit of work: a five-question interview (name it, GitHub issue?, branch?, compaction likely?, per-task scope), then create the .mightymodels/<slug>/ ticket directory, ticket.yml with derived model routing, the optional issue using the repo's own template with humanizer-cleaned prose, the branch, and a thin handoffs/SPRINT.md prompt for the next session. Use whenever triage is done and the user wants to stage the next work session — "prepare the handoff", "cut a ticket for this", "set this up for the next session", "create the mightymodels ticket", "get this ready to implement". Not for starting the implementation itself (that is the next session's ramp), and not for Jira ticket operations (the jira skill owns those).
---


# prepare-handoff

Turn an understood problem into a unit of work another session can pick up cold. Everything durable lands in `ticket.yml` and the issue; the handoff prompt stays thin because the next session reads those first.

Read `references/ticket-schema.md` and `references/mightymodels-dir.md` before the first run in a session — they are the contract this skill exists to instantiate.

## The interview

Ask exactly these five, via the ask-user dialog when available (in chat otherwise). Batch them in one dialog when the tool supports multiple questions — five sequential dialogs is an interrogation:

1. Name this unit of work (becomes the slug).
2. Create a GitHub issue? If yes, a name for it.
   2a. Have the jira cli? If yes ask the user if they'd like to create a Jira issue too, and if yes, a name for it.
3. Create a branch? If yes, a name for it and the base branch (default: HEAD).
4. Would implementing this likely cause at least one compaction?
5. How large is the scope of each anticipated task? (sm / med / large)

Answers 4 and 5 are not trivia — they derive `plan-first`, the primary-tier hint, and the engineer model per the schema's rules. If the user already supplied an answer in conversation, don't re-ask it; confirm it in the summary instead.

## The actions

**A — ticket directory.** `mkdir -p .mightymodels/<slug>/handoffs`, then the ignore ritual from mightymodels-dir.md (idempotent — run it every time, it's one line).

**B — issue (optional).** Discover the repo's issue conventions first: templates under `.github/ISSUE_TEMPLATE/`, labels in recent issues, title style from `gh issue list`. Draft the body from the triage findings, pass the prose through the humanizer skill, and include a **security surface** section ONLY when the change touches a trust boundary, a new input source, or authz/secrets handling — one short list of boundaries crossed and 2–5 abuse cases phrased as candidate acceptance criteria. When there is no surface delta, omit the section entirely; inventing threats for a docs change teaches readers to skip the section that matters. Create with `gh issue create`; if `gh` is unavailable or fails, write the body to `.mightymodels/<slug>/issue-body.md` and surface the exact `gh` command for the user to run.

**C — branch.** Create and push it. A rejected push (no remote, no auth) is a note in your summary, not a blocker — the branch exists locally.

**D — ticket.yml.** Emit per `references/ticket-schema.md`, deriving `engineer`, `plan-first`, and `scope` from the answers. Then tell the user the file exists and pause: they tweak it by hand before anything else happens. Their edit wins over your derivation — that is the point of the pause.

**E - handoffs/SPRINT.md.** Invoke the `promptlint` skill and use that to create a thin prompt for the next session, pointing at the ticket.yml and the issue, naming the ramp (`inline-sendoff` when scope is sm and plan-first false, `plan-work` otherwise), and stopping. Any fact copied into it is a fact that can drift.

```markdown
# Handoff for <slug>

<important>YOU MUST invoke `using-mightmodels`</important>

## Handoff Content

<!-- The next session reads these first, so they must be correct. -->
```

## The handoff

After the user is done tweaking, offer: "Generate a prompt to begin the next session?" On yes, write `handoffs/SPRINT.md` — reading the _tweaked_ yaml, never your original draft. Thinness rule from mightymodels-dir.md applies absolutely: the file points at ticket.yml and the issue, names the ramp (`inline-sendoff` when scope is sm and plan-first false, `plan-work` otherwise), and stops. Any fact copied into it is a fact that can drift.

Close with "the task is ready for handoff" — and when plan-first is true, add: "switch models in your next session" (the plan gets written by a low-tier primary; the yaml carries the hint).

## Failure honesty

Every fallback gets surfaced in the closing summary: issue drafted-not-created, branch unpushed, template not found. A handoff that silently pretends its side effects happened strands the next session — the summary is part of the artifact.

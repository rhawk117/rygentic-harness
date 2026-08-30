# ticket.yml schema

The per-ticket source of truth, written once by prepare-handoff from the interview answers, then hand-tweaked by the user. Every later session reads it before doing anything else; agent-file model pins are only the fallback for headless runs where nobody answered.

```yaml
task: <slug>                    # directory name under .mightymodels/
summary:                        # one sentence
triaged-at: <ISO datetime>
context:                        # optional free-text lines from triage worth carrying
companion-docs:
  issue-number:                 # optional
  reference-urls:               # external documentation used during triage ONLY —
    - example.com               # never issues
subagent-models:
  primary-agent:                # user hint, not source of truth
  scout: claude-haiku-4-5       # default; user-overridable
  budgetron: claude-sonnet-5    # default; user-overridable
  engineer:                     # DERIVED — see rules below
  gitty-up: claude-haiku-4-5    # default; user-overridable
  grumpy: claude-sonnet-5       # default; user-overridable
  sunny: claude-opus-5          # default; user-overridable
  wingman: claude-opus-5        # default; user-overridable
  merge-vader: claude-opus-5    # default; user-overridable
  uncle-bob: claude-opus-5      # default; user-overridable
handoff-context:
  scope: <sm|med|large>         # from the per-task scope answer
  plan-first: <bool>            # from the compaction answer
  branch-name:
  worktrees-okay: false         # default; dormant until engineers run in parallel
```

## Derivation rules

**engineer**: from the task-scope answer — `large` → `claude-opus-5`; otherwise `claude-sonnet-5`. The ticket value is the default for every task; the primary may bump a single gnarly task one tier at dispatch, logging the reason in that task's ASKED stanza. A ticket has one scope value; its tasks do not.

**plan-first**: `true` when the user expects at least one compaction. `true` also means the SPRINT.md handoff carries the switch-models reminder, and the next session's low-tier primary writes the plan before any dispatch.

**Reviewer split** (decision of record, 2026-08-29): both reviewers run `claude-opus-5`. The split is by role and report, not model — uncle-bob grades abstraction and structure, merge-vader runs the adversarial pre-merge pass, and their reports land separately so neither hedges the other. User-overridable per ticket like everything else in this block.

## Field discipline

No `review-weight` block — nothing consumes it (cut 2026-08-20). No key enters this schema without a named consumer in the flow; unused yaml is landfill with indentation.

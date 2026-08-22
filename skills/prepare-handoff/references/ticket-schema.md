# ticket.yml schema

The per-ticket source of truth, written once by prepare-handoff from the interview answers, then hand-tweaked by the user. Every later session reads it before doing anything else; agent-file model pins are only the fallback for headless runs where nobody answered.

```yaml
task: <slug>                    # directory name under .mightymodels/
summary:                        # one sentence
triaged-at: <ISO datetime>
context:                        # optional free-text lines from triage worth carrying
companion-docs:
  issue-number:                 # optional
  jira-tickets: []              # optional, omitted by default
  reference-urls:               # external documentation used during triage ONLY —
    - example.com               # never issues or jira tickets
subagent-models:
  primary-agent:                # user hint, not source of truth
  scout: gpt-5.6-luna           # default; user-overridable
  budgetron: gpt-5.6-luna       # default; user-overridable
  engineer:                     # DERIVED — see rules below
  gitty-up: gpt-5.6-luna        # default; user-overridable
  grumpy: gpt-5.6-luna          # default; user-overridable
  sunny: claude-opus-5          # default; user-overridable
  wingman: claude-opus-5        # default; user-overridable
  merge-vader: gpt-5.6-sol      # default; user-overridable
  uncle-bob: claude-opus-5      # default; user-overridable
handoff-context:
  scope: <sm|med|large>         # from the per-task scope answer
  plan-first: <bool>            # from the compaction answer
  branch-name:
  worktrees-okay: false         # default; dormant until engineers run in parallel
```

## Derivation rules

**engineer**: from the task-scope answer — `large` → `sonnet-5` or `gpt-5.6-terra`; otherwise `gpt-5.6-luna`. The ticket value is the default for every task; the primary may bump a single gnarly task one tier at dispatch, logging the reason in that task's ASKED stanza. A ticket has one scope value; its tasks do not.

**plan-first**: `true` when the user expects at least one compaction. `true` also means the SPRINT.md handoff carries the switch-models reminder, and the next session's low-tier primary writes the plan before any dispatch.

**Reviewer split** (decision of record, 2026-08-20): uncle-bob on `claude-opus-5` — abstraction and structure judgment gets the frontier Claude; merge-vader on `gpt-5.6-sol` — cross-vendor diversity on the adversarial pass. User-overridable per ticket like everything else in this block.

## Field discipline

No `review-weight` block — nothing consumes it (cut 2026-08-20). No key enters this schema without a named consumer in the flow; unused yaml is landfill with indentation.

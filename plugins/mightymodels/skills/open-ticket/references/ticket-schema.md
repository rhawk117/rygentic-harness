# ticket.yml schema

The per-ticket source of truth, written once by open-ticket (the `ticket` tool's `write`) from the interview answers, then hand-tweaked by the user and checked by the `ticket` tool's `validate`, which stages the ticket as a row in the state database. Every later session reads it before doing anything else; agent-file model pins are only the fallback for headless runs where nobody answered.

```yaml
task: "<slug>"                   # directory name under .mightymodels/
summary: "<one sentence>"
triaged-at: "<ISO datetime>"
context:                         # 1-6 lines: the knowns and decisions the next session
  - "<line>"                     # cannot afford to lose; no file:line
companion-docs:
  issue-number:                  # optional; GitHub issue number
  jira-key:                      # optional; Jira ticket key, e.g. "PROJ-123"
  reference-urls:                # external documentation used during triage only
    - "https://..."
subagent-models:
  primary-agent:                 # user hint, not source of truth
  code-scout: "haiku"
  web-scout: "haiku"
  qualitylens: "haiku"
  engineer: "sonnet"             # sonnet at every scope
  architect: "<derived>"         # see derivation rules
  intern: "haiku"
  gitty-up: "haiku"
  wingman: "fable"
  merge-vader: "opus"            # ignored: a review run sets reviewer models
  uncle-bob: "opus"              # ignored: a review run sets reviewer models
handoff-context:
  scope: "<sm|med|large>"
  plan-first: <true|false>       # derived from the compaction answer
  branch-name: "<branch>"
  worktrees-okay: false          # dormant until engineers run in parallel
investigations:                  # lets-investigate ids whose ledgers this ticket came from
  - "<id>"
```

## The subset

The `ticket` tool writes this file and reads back exactly this YAML subset, so hand edits validate as long as they stay inside it:

- mappings indented by two spaces (the tool writes them two levels deep and checks keys, not depth);
- scalars: double-quoted strings (JSON escapes), plain words, integers, `true`/`false`, or empty for null;
- lists of scalars, one `- item` per line;
- `#` comments on their own line or after a value.

Anchors, flow collections (`[a, b]`, `{a: b}`), single quotes, and block scalars (`|`, `>`) are refused with the line number. `validate` refuses unknown keys too, at the top level and under `companion-docs`, `handoff-context` and `subagent-models`, including retired worker keys such as `scout` or `budgetron`, because a key nobody reads is a setting that silently does nothing. It also requires a non-empty `summary`, a `task` equal to the slug, one to six `context` lines, a `scope` of sm, med or large, a boolean `plan-first`, a non-empty `branch-name`, a numeric `issue-number`, a model for `engineer` and `architect`, no model for a fixed worker (every worker but the two reviewers) other than the one routing fixes, and a ledger for every linked investigation.

## Derivation rules

**engineer**: `sonnet` at every scope. The primary may bump a single gnarly task one tier at dispatch, logging the reason in that task's ASKED stanza. A ticket has one scope value; its tasks do not.

**architect**: `opus` at every scope. Architect recovers a failed engineer task, one tier above the engineer.

**plan-first**: `true` when the user expects at least one compaction. `true` also means the baton-pass handoff prompt carries the switch-models reminder, and the next session's low-tier primary writes the plan before any dispatch.

**Reviewers**: a review run sets its reviewers' models from its depth, `sonnet` for quick and `opus` for standard and deep, and the run's one override moves the heavier-weighted reviewer to `fable`. The two reviewer keys are written for completeness and change no review. The other workers are fixed: `validate` refuses a value that differs from `code-scout`, `web-scout`, `qualitylens`, `intern` and `gitty-up` on `haiku`, `engineer` on `sonnet`, `architect` on `opus` and `wingman` on `fable`.

## Field discipline

No `review-weight` block — nothing consumes it (cut 2026-08-20). No key enters this schema without a named consumer in the flow; unused yaml is landfill with indentation. Consumers of record: `context` is read by every ramp before dispatch; `investigations` by what-we-know in sprint mode and by prune-ticket; `jira-key` is read by stick-the-landing (PR description link) and prune-ticket (archive header), alongside `issue-number`.

# The .mightymodels/ directory

Per-ticket files, sparse, organized by unit of work, at the git toplevel whichever directory the session started in. The unit of deletion for files is the unit of work: `/prune-ticket` removes a whole ticket directory, so file rot cannot outlive its ticket. The ticket's rows stay in the database.

The state itself is rows in one SQLite database, `mightymodels.db`, and that file is not in this directory. It is in the plugin data directory, the one Claude Code names in `CLAUDE_PLUGIN_DATA`, it serves every repository, and each row carries the key of the repository it belongs to: the origin remote's `owner/name`, or a hash of the toplevel path when there is no origin or the origin is not exactly `owner/name` on a host. The database holds tickets, tasks, the contract, ledgers, reviews, crashouts and closings. A database an earlier version left inside this directory is not read, imported or changed, and can be deleted.

```
.mightymodels/
├── <task-slug>/
│   ├── ticket.yml                     source of truth (see ticket-schema.md)
│   ├── plan.md                        game-plan ramp only; high-level, citation-free
│   ├── toolchain.md                   game-plan ramp only; terry-toolchain's survey, ≤80 lines
│   ├── issue-body.md                  when no forge issue was created, or as the local draft
│   ├── pr-body.md                     stick-the-landing's checked PR body
│   ├── handoffs/snapshot.{json,md}    baton-pass writes what the snapshot tool returns: objective state from the database
│   ├── handoffs/BATON.md              mid-work handoff, ≤40 lines, facts that live nowhere else
│   ├── briefs/task-NN.md              two halves, ≤80 lines (contracts.md)
│   ├── review/<run>/                  one review-circus run: persona reports, metrics, the rendered report
│   ├── whats-broken.md                only while a debug is live; regenerated per attempt
│   └── REPORT.md                      ≤50 lines, sprint summary
├── .runtime/reviews/<run>/            review runs with no ticket
└── archives/<task-slug>.{md,json}     ≤30-line archive plus bounded JSON record, written by prune-ticket from the close tool's text
```

The decision and subagent recorder hooks record rows in the database; they arrive with the hooks (surface.md "Hooks").

## Writer/reader matrix: one writer per file class

The database's only writers are the state server's eight tools and `mightymodels verify run`. Each group of tables has one.

| Path or tables                                                       | Writer                                                                                              | Readers                                                  |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| `tickets`                                                            | the `ticket` tool (`validate` and `update-context` stage the row); the `task` tool moves a staged ticket to in-progress and refuses a closed one, and the `close` tool moves the ticket to closed                                   | every session                                            |
| `tasks`, `task_attempts`, `task_transitions`, `task_failed_fixes`  | the `task` tool, called by agents-assemble; the `failed_fix` tool for `task_failed_fixes`, called by an engineer |  agents-assemble, stick-the-landing, baton-pass           |
| `contract_commands`                                                  | the `contract` tool's `approve`, called by game-plan and one-shot                                   | the `task` tool, every skill that proves work            |
| `receipts`                                                           | `mightymodels verify run`                                                                           | the `task` and `snapshot` tools, every skill that proves work |
| `ledger_entries`                                                     | the `investigation` tool                                                                            | what-we-know, open-ticket, the `snapshot` tool           |
| `review_runs`, `review_findings`, `review_dispositions`, `review_outcomes` | the `review` tool                                                                             | review-circus, stick-the-landing, the `close` tool       |
| `crashouts`                                                          | the `crashout` tool                                                                                 | crashout                                                 |
| `closings`                                                           | the `close` tool                                                                                    | prune-ticket, future sessions                            |
| ticket.yml                                                           | open-ticket's `ticket` `write`, or one-shot when ramping without a ticket (then the user's hand)    | every session                                            |
| plan.md                                                              | game-plan primary, after user approval                                                              | primary, dispatch compilation                            |
| toolchain.md                                                         | game-plan primary, verbatim from terry-toolchain's report                                           | primary, dispatch compilation                            |
| briefs/ ASKED half                                                   | primary at dispatch                                                                                 | engineer, verifying scout                                |
| briefs/ DONE half                                                    | engineer                                                                                            | primary, verifying scout                                 |
| review/<run>/ directory                                              | the `review` tool's `start` creates it; the primary writes persona reports, metrics and the rendered report | review-circus, stick-the-landing, prune-ticket, the user |
| issue-body.md, pr-body.md                                            | open-ticket or one-shot (issue-body.md), stick-the-landing (pr-body.md)                             | `gh issue create`, `gh pr create`                        |
| handoffs/                                                            | baton-pass, from the `snapshot` tool's text; BATON.md is the primary's own                          | the next session's primary                               |
| whats-broken.md                                                      | the whats-broken primary                                                                              | the `close` tool, which blocks closing while it exists   |
| REPORT.md                                                            | agents-assemble primary                                                                             | stick-the-landing, review-circus, prune-ticket           |
| archives/                                                            | prune-ticket, from the `close` tool's text                                                          | future humans and sessions                               |

## Thinness rule for handoffs

`BATON.md` carries only facts that live nowhere else. It is a bootstrap pointer — read ticket.yml, read issue #N, your role, what to invoke — plus nothing. Duplicated facts drift, and the next session reads ticket.yml first anyway.

## Never tracked

Nothing under `.mightymodels/` is ever committed. The state server at start and `mightymodels verify run` add `.mightymodels/` to the repository's local exclude file (`info/exclude` in the common git dir, so worktrees share it). `briefs/`, `review/`, and the database carry raw command output that can hold secrets, and local-only exclusion means a careless `git add -A` cannot ship them. A later session that finds `.mightymodels/` missing from the exclude file restarts the server, which restores it before anything is written there.

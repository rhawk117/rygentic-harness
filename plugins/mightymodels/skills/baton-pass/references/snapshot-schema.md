# Snapshot schema

Read before another component writes a table the `snapshot` tool reads, and when a snapshot carries warnings. The snapshot is objective state, read from the database and git; BATON.md adds only what no table holds.

## Output

The tool writes no file. Its answer holds `record` (the JSON below), `markdown`, and the two paths `record_path` and `markdown_path`, which are `.mightymodels/SLUG/handoffs/snapshot.json` and `snapshot.md` relative to the repository root. The agent writes both whole on every run; never tracked by git. Each list holds at most `limit` entries (default 20, at most 100), the most recent kept, except `tasks` and `checks`, which list every task and every contract command. The changed paths in `repository` are cut to `limit` too; `dirty_count` is not.

| Key                           | Source                                                    | Holds                                                                                                         |
| ----------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `ticket`                      | `tickets` row                                             | summary, status, scope, tracker                                                                               |
| `repository`                  | git: branch, HEAD, `status --porcelain`                   | branch, HEAD, count and list of changed paths                                                                 |
| `tasks`                       | `tasks`, `task_attempts` rows, plan tasks of the contract | every started task with status, attempts, reasons; plan tasks with contract commands never started as `not started` |
| `checks`                      | `contract_commands`, `receipts` rows                      | each command: the latest receipt's outcome at HEAD, `stale (OUTCOME at OLD-HEAD)`, or `never-run`                     |
| `works`                       | the same                                                  | commands whose latest receipt passed, at any HEAD, with their argv                                            |
| `decisions`, `open_questions` | `ledger_entries` of the linked investigations             | live `decision` and `open` entries, superseded ones dropped, each with its investigation and entry under `from` |
| `do_not_retry`                | `task_transitions` rows                                   | transitions into `failed` or `blocked`, with the reason and HEAD                                              |
| `review`                      | the latest `review_runs` row and its findings            | run, depth, finding count, undecided ids, remediation still open, non-fix decisions with reasons              |
| `answers`, `subagents`        | none yet                                                  | present and empty: the snapshot reads no table for them yet                                                  |
| `warnings`                    | the reader                                                | git not consulted (no git binary, or not a repository), linked investigations with no ledger                  |

A section with nothing to show reads as one line in the Markdown saying so. With no git, `repository` is empty and a warning says why.

## Hook receipts

The `answers` and `subagents` sections stay in the record and read empty. The database holds no row for a user's answer, and the scout reports the recorder hooks spool are stored in `scout_reports`, which the snapshot does not read. The snapshot does not infer them.

## Writers of what it reads

The snapshot reads rows other tools own. `ticket` writes `tickets`, and `task` (in progress) and `close` (closed) move its status; `task` writes the task rows; `contract` writes `contract_commands`; `mightymodels verify run` writes `receipts`; `investigation` writes `ledger_entries`; `review` writes the review rows. The row shapes are the contract, so a change to one of them updates this reader in the same change.

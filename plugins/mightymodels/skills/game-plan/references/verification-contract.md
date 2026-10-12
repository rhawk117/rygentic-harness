# Verification contract (schema version 1)

Read when recording or extending a contract, when a run is refused, or before another skill reads the receipts. The `contract` tool writes the approved commands and `mightymodels verify run` writes the receipts; nothing else writes either table.

## Storage

Rows in the state database, `mightymodels.db` in the plugin data directory, in two tables: `contract_commands` and `receipts`. The database is outside the repository, so git never sees it, and its rows are keyed by repository. The task, snapshot and close tools read both tables; the closing archive lists each command with its latest outcome, HEAD and digest.

## Approved commands

One `contract_commands` row per approved command, keyed by `slug` and `command_id`:

| field | meaning |
| --- | --- |
| `command_id` | the id, such as `T1.AC-1` |
| `task_id` | the task the id belongs to, read from the id's prefix (`T1` in `T1.AC-1`), or null (`I1`) |
| `argv` | the command as a list of strings |
| `expect_exit` | the exit code that proves the criterion, default 0 |
| `timeout` | seconds, default 300 |
| `approved_by` | who approved it |
| `approved_at` | UTC timestamp, ISO 8601 |
| `head` | the commit the repository was at when it was approved, null outside a repository |

- **ids** are letters, digits, `.`, `_` and `-`. By convention `I<n>` is an invariant and `T<n>.AC-<n>` a task acceptance criterion; the task tool finds a task's commands by the task id before the first dot (`T`, `C` or `R` and a number, such as `C<n>.AC-<n>` for a local reproduction of a failing CI check).
- **argv** is a list, never a shell string: no pipes, redirection, globbing, `&&`, or variable expansion. A check that needs a pipeline belongs in a script the repository owns, and the contract runs that script.
- **expect_exit** is the completion expectation, not the planning baseline: a test that does not exist yet fails at planning time and that is recorded, not refused.
- **timeout** is 1 to 3600 seconds. A hang is a failure, never a pass.
- **approval**: `contract` `approve` refuses a command with no `approved_by` and stamps the time and HEAD. A command that names no approver is put to the user by the tool, which shows the full id and argv list and records the commands as approved by `user` only when the user approves. When the tool cannot ask (it answers `needs input`), the skill asks in one `AskUserQuestion` dialog and calls again with `approved_by` on each command; the tool cannot see that dialog, so a call that names an approver the user never gave is a skill violation, not a tool bypass.
- An approved id never changes its argv. `approve` skips an id that is already recorded with the same argv, keeping its row (a new `expect_exit` or `timeout` for it is not stored), and refuses an id recorded with a different argv: a different command gets a new id and a new approval.

## Running

`mightymodels verify run --slug SLUG (--id ID ... | --all) [--phase PHASE]` looks each id up in the ticket's rows and executes its argv, without a shell, from the repository root. `--all` runs every approved id, which is how stick-the-landing re-proves the ticket after a CI fix moves HEAD. `--id` repeats; it and `--all` are exclusive and one is required. An id not approved, or a ticket with no approved commands, is refused before anything runs; the caller can never pass an argv, which is what keeps the runner from being a general shell. It is refused too when git or the repository is missing, since every receipt records a HEAD. `--phase` is `planning`, `task`, `review`, or `landing`, default `task`.

It prints one line per command, `ID outcome exit=N 1.2s`, and for a command that did not pass, the tail of its stderr (its stdout when stderr is empty). It exits 0 when every command passed, 1 when any did not, and 2 when the run was refused.

## Receipts

One `receipts` row per run, appended: `id` (a serial number), `slug`, `command_id`, `argv`, `outcome` (`pass`, `fail`, `timeout`, `not-found`, `refused`, `undecodable`), `exit` (null for `timeout`, `not-found`, `refused` and `undecodable`), `duration_ms`, `stdout_tail` and `stderr_tail` (last 40 lines, at most 4000 characters), `digest` (SHA-256 of the full stdout plus stderr), `head`, `phase`, `at`. A run that HEAD moved under is recorded as `fail`. `not-found` means the program in argv does not exist, `refused` that it could not be launched (it is not executable, or the argv holds a NUL), and `undecodable` that its output is not text in the default encoding.

## Status

`contract` `status` reports the HEAD, then each approved command with its latest receipt: `pass` or `fail` and its phase and `expect=N` when the receipt is at the current HEAD, `stale (outcome at SHA)` when it ran at another HEAD, `never-run` otherwise. It takes no prefix and lists every command of the ticket. `passing` is true only when every listed command passed at the current HEAD, which is the check the loop relies on; with no approved commands it reports `no matching commands` and `passing` is true, since nothing listed failed.

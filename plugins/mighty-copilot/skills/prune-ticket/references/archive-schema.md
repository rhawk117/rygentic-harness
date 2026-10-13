# Archive schema

Read before closing a ticket and before changing the `close` tool, the only writer of a ticket's closing.

## Files

The `close` tool returns the archive and writes no file: the agent writes `.mightymodels/archives/SLUG.md` (30 lines at most) from `markdown` to `markdown_path`, and `SLUG.json` from `record` to `record_path`. Never tracked by git. A slug that was archived before gets `SLUG-2`, `SLUG-3`: the tool takes the first name whose Markdown file is absent. The `closings` row holds the Markdown path in its `archive` column and the closing as given.

## Live work (`check`, and `close` before it writes)

- a task that is not `verified` or `superseded` (plan `T`, CI `C`, and review `R` tasks alike);
- a plan task with contract commands that was never started, and, when no task has been started at all, `no verified task work is recorded`;
- `whats-broken.md` in the ticket directory;
- in the latest review run: a finding with no decision, or one chosen for fixing and not fixed;
- the ticket's branch, while it exists locally, with commits on no remote, or checked out with uncommitted changes to tracked files.

`check` returns these as a result that says `blocked`, never as an error, and answers for a closed ticket too. With no git, or outside a repository, the branch is not asked about and the text says git was not consulted.

REPORT.md open threads and the issue's open items are in no row the tool reads; the skill checks those.

## The JSON record

`ArchiveRecord`, in `tools/close/schema.py`:

| Key                                    | From                                                                                                     |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `slug`, `closed_at`, `head`            | the call, the clock and the repository at close                                                          |
| `shipped`, `pr`, `gotchas`             | the closing input (redacted, one line each; `shipped` required, `pr` optional, at most 3 gotchas)        |
| `summary`, `tracker`, `investigations` | the ticket's row                                                                                         |
| `tasks`                                | each task's final status and attempts per worker                                                         |
| `verification`                         | every contract command with argv, `expect_exit`, and its latest outcome, HEAD, and digest                |
| `decisions`                            | the last 4 live `decision` entries of the linked ledgers, each with its investigation and entry (`from`) |
| `review`                               | the latest run: id, depth, finding count, ids grouped by outcome or decision, the recorded reasons       |
| `agents`                               | `runs` 0, `by_status` empty and `recent` empty: the close tool reads no worker rows yet                     |
| `answers`                              | `recorded` 0 and `recent` empty: the database holds no answer rows yet                                    |

A call with more than 3 gotchas, or with no `shipped`, is refused and stores nothing.

## Pruning

The tool has no prune. Once the ticket is closed and both archive files are written and read back, the skill removes `.mightymodels/SLUG` with Bash after the user's yes, and nothing else. The ticket's rows stay in the database, its linked ledgers included, and so do the archive files. Review runs outside a ticket and other tickets' state are never touched.

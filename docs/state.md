# Ticket state: the .mightymodels/ directory

Everything a ticket knows lives in one directory named after it. The design rule is sparseness:
files exist because a named consumer reads them, each file class has exactly one writer, and
`/prune-ticket` deletes the whole directory when the work merges. The unit of deletion is the
unit of work, which is what stops working state from turning into a landfill of stale evidence.

## Layout of a live ticket

```text
.mightymodels/
├── <task-slug>/
│   ├── ticket.yml                source of truth: scope, routing, companion docs
│   ├── plan.md                   game-plan ramp only; high-level, citation-free
│   ├── toolchain.md              game-plan ramp only; terry-toolchain's survey, at most 80 lines
│   ├── issue-body.md             local draft, or the issue when no forge issue exists
│   ├── pr-body.md                stick-the-landing's checked PR body
│   ├── handoffs/snapshot.{json,md}  recorded state, as the snapshot tool returns it
│   ├── handoffs/BATON.md         mid-work handoff, at most 40 lines
│   ├── briefs/task-NN.md         two halves, at most 80 lines
│   ├── review/<run>/             one review-circus run: persona reports, metrics, the report
│   ├── whats-broken.md           only while a debug is live
│   └── REPORT.md                 sprint summary, at most 50 lines
├── .runtime/reviews/<run>/       review runs with no ticket
└── archives/<task-slug>.{md,json}  at most 30 lines plus a JSON record, written by prune-ticket
```

## The state database

The rows behind a ticket are not in this directory: the staged ticket, its tasks, the
verification contract and its receipts, review runs, investigation ledgers, crashouts and
closings. They are in one SQLite file, `mightymodels.db`, in the plugin data directory, the
directory Claude Code names in `CLAUDE_PLUGIN_DATA` for the plugin's state server. One file
serves every repository. Each row carries a repository key, the `owner/name` of the origin remote
or, with no origin, a hash of the checkout's toplevel path, and a read finds only the rows of the
repository it runs in. An origin that is not exactly `owner/name` on a host gets the path hash
too: a subgroup path such as `group/sub/name`, a path of one name, a local path or a `file://`
URL. Clones of one `owner/name` share their rows, whatever the host or the URL form. Checkouts
keyed by their path each keep their own, and a checkout that moves starts empty.
`.mightymodels/` itself sits at the git toplevel, whichever directory the session started in.

A command run through the Bash tool does not get `CLAUDE_PLUGIN_DATA`. The plugin's SessionStart
hook exports the same directory as `MIGHTYMODELS_DATA_DIR`, and `mightymodels verify run` reads
that one. With its variable unset, or outside a git work tree, the server answers every tool call
with what is missing, and `verify run` exits 2 with the same on standard error.

Every session of every repository writes that one file. It is kept in SQLite's write-ahead log
mode, so `mightymodels.db-wal` and `mightymodels.db-shm` sit beside it while a session has it
open, and a write waits up to 10 seconds for another session's write before it is refused as
locked.

This breaks with earlier versions, which kept the database inside the repository, under
`.mightymodels/`. That file is not read, not imported and not changed, so state recorded in it
does not carry over: stage the ticket again. The old file can be deleted. The new file is stamped
with a schema version, and a file with another stamp is refused by name instead of read, and
nothing is written to it.

## Tasks

The `task` tool keeps one row per task, and a task's status is `pending`, `in-progress`,
`verified`, `failed`, `blocked` or `superseded`. A plan task has a `T` id, a residual fix an `R`
id, and a fix for a failing CI check a `C` id. `start` opens an attempt and takes who works it
(`by`: `engineer`, `architect` or `intern`), the files the task owns (`owned`) and the ids of
its acceptance criteria (`acceptance`). `acceptance` is required, so a task's size is always
counted: a start with more than four criteria or more than ten owned files is refused, and the
refusal names `break-it-down`. When the user keeps such a task whole in that skill's dialog, the
same call with `too_large_approved_by: "user"` is accepted and the approval is recorded with
the start.

`verify` moves a task to `verified`, and `mark` moves it to `failed`, `blocked` or `superseded`.
A task that was never started can be marked `superseded` and nothing else, which is how
`break-it-down` closes a task it replaced with smaller ones. A residual takes the next `R<n>`
that `show` does not list, whoever starts it, so it is not numbered after the finding it fixes.
The intern gets one attempt at a task, and the architect one implementation pass.

When an implementer stops, the completion gate, a `SubagentStop` hook, looks at the tasks it
started that are still in progress. A plan task is held once while its brief has no DONE half
naming a commit. A residual has no brief and is held once while it lacks a commit after its
base, a passing receipt at HEAD for each contract command of its own, or a diff inside its owned
files. A `C` task is not held.

## Failed fixes

The `task_failed_fixes` table holds the hypothesis behind each fix that failed on a task, written by
the `failed_fix` tool, whose one action is `record`; it asks the task service, which keeps the
count. The hypothesis is redacted on its way in. A task holds at most `FAILED_FIX_LIMIT` = 3 of
them, counted per repository key, ticket and task, and a fourth is refused with an error that says
the task is blocked and lists the three in order; nothing is stored for it. The limit is what stops
a stuck engineer after three fixes.

## Similarity and the scout-report spool

The same file holds one `similarity` table with a `kind` column: `ledger-entry`, `scout-report`,
`review-finding` and `crashout`. Writing an investigation entry, a review finding or a crashout
stores its text there in the same transaction (the entry's text, the finding's title, the
crashout's root cause), and so does a scout report, whose full text is also kept in `scout_reports`.
The text is redacted on its way in. An FTS5 index, `similarity_index`, reads the table's text, and
SQLite triggers keep it current. The index is created after the schema stamp is accepted, so a file
stamped with another version is still refused untouched. The schema version is 1.

A write answers with a line when the text resembles a row stored earlier, of any kind:
`near-duplicate: <written> resembles <kind> <reference> (overlap 0.75): <start of the earlier text>`.
The write is stored all the same. A match is a hint that this has probably been recorded already,
and it is found by words, so it misses a duplicate that shares no wording with the earlier row.
The `similarity` tool's `search` action takes a `query` and an optional `kind` and returns the
rows that share a content word with the query, best BM25 rank first, each with its overlap.

How a match is decided, with both constants in `tools/similarity/matching.py`: a text is reduced to
its content words (lowercase letters and digits, less common English words). BM25 ranks the rows of
the same repository that share one, and the best `CANDIDATE_CAP` = 20 are read. BM25 scores are
relative to the whole index, so no score says two texts are alike; instead a candidate is a match
when the share of the words of both texts that are in each (Jaccard overlap) reaches
`MATCH_OVERLAP` = 0.6. A text with only common words has no candidate. Every read filters on the
repository key, since FTS5 keeps one set of term statistics for all repositories.

Scout reports reach the database through a spool, so a hook can leave one without calling the
server. The spool is the directory `scout-spool` in the plugin data directory, beside
`mightymodels.db`. A report is one file `<digest>-<unique part>.json` directly in it, whose content is one
JSON object with exactly these keys:

```json
{"repository_key": "owner/name", "scout": "code-scout", "target": "...", "report": "..."}
```

`repository_key` is the key described above (`owner/name`, or `local:` and 64 hex digits),
`scout` is `code-scout` or `web-scout`, `target` is at most 255 characters and `report` is
non-blank text of at most `REPORT_LIMIT` = 60000 characters, and the file is at most
`SPOOL_FILE_BYTES` = 724,996 bytes. `REPORT_LIMIT` is the limit of a scout report and of the text of
every similarity row, in `declarative.py`, and the byte cap follows from it: the cap allows for the
longest spelling a JSON writer gives a character, the escaped one, at most 12 bytes (a four-byte
character is a surrogate pair of two six-byte escapes), and the cap is (`REPORT_LIMIT` + 255 for
the target + 140 for the key) x 12 bytes plus 256 for the keys and braces. The plugin's own writer
writes a character outside ASCII as itself in UTF-8, which never takes more. A report at the limit
is therefore stored whole, never cut, whatever its characters, and one over it is set aside. A file
over the cap is set aside the same way.
A writer creates the file under a name that does not end in `.json` and
renames it, so a half-written file is never read. `<digest>` is the SHA-256 hex digest of the repository key's text in UTF-8 and the
`spool_file_prefix(key)` function in `repository_key.py` gives `<digest>-`. The directory is
shared by every repository, so the server lists only the names that begin with its own digest
and a file under any other name is never opened, read or moved: other repositories' files cannot
keep it from its own. It takes in those files on its next tool call, stores each as a scout report
with a similarity row, and deletes the file; a file under its digest whose content names another
key is set aside. It ignores symlinks and directories, and takes in at most 100 files per call. A scout that hands
its report back leaves two files, the `handback-` one (the `PostToolUse` hook on
`SubagentHandback`) and a `stop-` one (its closing text, from the `SubagentStop` hook). They wait in
name order, so the hand-back is listed first, and the server drops a `stop-` file when a report of
the same scout and target is stored: one report per agent, the handed-back one. A file under any
other part of the name is stored as it is. A file that is not valid, or whose text
redaction lengthens past its column, is moved to `scout-spool/rejected/` under a new name and kept;
the call goes on. A path holds the digest and never the key.

## ticket.yml

Written once by open-ticket through the `ticket` tool's `write`, from the interview answers, then
hand-tweaked by the user. Every later session reads it before doing anything else.

```yaml
task: rate-limit # directory name under .mightymodels/
summary: requests over the cap return 500 instead of 429
triaged-at: 2026-08-20T14:02:00Z
context:
  - the limiter is keyed per API token, not per IP
companion-docs:
  issue-number: 214
  reference-urls:
    - docs.example.com/rate-limiting # external docs from triage only
subagent-models:
  primary-agent: null
  code-scout: haiku
  web-scout: haiku
  qualitylens: haiku
  fact-checker: haiku
  engineer: sonnet # sonnet at every scope
  architect: opus # opus at every scope
  intern: haiku
  gitty-up: haiku
  wingman: fable
  terry-toolchain: sonnet
  merge-vader: opus # ignored: a review run sets reviewer models
  uncle-bob: opus # ignored: a review run sets reviewer models
handoff-context:
  scope: sm # sm | med | large
  plan-first: false # true when a compaction is expected
  branch-name: fix/rate-limit
  worktrees-okay: false
  auto-escalate: true # optional; off when the key is absent
investigations:
  - rate-limit-ledger-id # lets-investigate ids this ticket came from
```

Three rules matter day to day. Every worker but the two reviewers has one fixed model, and
`validate` refuses a ticket whose value differs. The engineer's `sonnet` is the default for
every task; the primary may bump one gnarly task a tier at dispatch, logging the reason in that
task's ASKED stanza. `plan-first: true` means the next session writes `plan.md` before any
dispatch.

`auto-escalate` decides who hears of a blocked or failed task first. Absent or `false`, the task
goes to the user before the architect or the wingman is dispatched for it: `agents-assemble`
asks, and the dispatch hook answers a main-thread dispatch of either with `ask` and the block's
reasons. `true` lets a block go to the architect without the question. `game-plan` asks for it
in one dialog question and writes the line only on `true`.

The schema is deliberately closed: no key enters it without a named consumer in the flow, and
`validate` refuses an unknown key. A `review-weight` block existed briefly and was cut for
exactly that reason.

## Handoffs stay thin

`BATON.md` contains zero facts that already live in `ticket.yml`, the issue or the snapshot
beside it. It is a bootstrap pointer: read the ticket, read issue N, here is your role, invoke
this skill. Duplicated facts drift, and the next session reads `ticket.yml` first anyway.

## Briefs

`briefs/task-NN.md` holds the two-half contract for one task. The primary writes the ASKED half
at dispatch; the implementer appends the DONE half on completion; fact-checker checks one
against the other. A finding of the fact-checker that does not hold the task is recorded in the
brief under `## FINDINGS`, where `review-circus` picks it up. The 80-line cap is load-bearing: a
brief that needs more space is a task that should have been split. Field-level detail is in
`plugins/mightymodels/skills/agents-assemble/references/contracts.md`.

## Reports and reviews

`REPORT.md` closes a sprint in at most 50 lines: what shipped, what deviated, what remains.
Each review run gets a directory under `review/`, so its reports live and die with their ticket
instead of littering the repo root; a run with no ticket writes to
`.mightymodels/.runtime/reviews/` instead.

`whats-broken.md` exists only while a debug is live. It carries the current falsifiable
hypothesis and its test, gets regenerated per attempt, and its presence blocks `prune-ticket`.

## Archives and pruning

`/prune-ticket` compresses a finished ticket into `archives/<slug>.md`: what shipped, the PR
link, key decisions, and any gotcha the next person would want. Thirty lines is the cap, and the
point. During pruning the skill also proposes cascading documentation updates as diffs, README
claims the change invalidated, for the user's approval, then deletes the ticket directory.

## Git hygiene

Nobody runs an ignore step by hand. Whenever the plugin opens the state database (the state
server at its start, `mightymodels verify run`, and the hooks that read state), it adds the line
`.mightymodels/` to `info/exclude` in git's common directory, unless the line is already there.
It does so after the database is open and before anything is written under the directory.

`info/exclude` is local and needs no commit, and it is the safer default: `briefs/` and
`review/` carry raw command output that can hold secrets, so local-only exclusion means a
careless `git add -A` cannot ship them. The line covers the whole directory, `archives/` and
every `ticket.yml` included.

## The canonical definitions

This page orients; the references define.
`plugins/mightymodels/skills/open-ticket/references/ticket-schema.md` is the schema with its
derivation rules, `plugins/mightymodels/skills/open-ticket/references/mightymodels-dir.md`
is the layout with the writer/reader matrix, and
`plugins/mightymodels/skills/agents-assemble/references/contracts.md` holds the severity table
and verdict vocabularies. Agents read those files; nothing reads this
one.

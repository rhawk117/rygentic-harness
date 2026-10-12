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
│   ├── issue-body.md             local draft, or the issue when no forge issue exists
│   ├── handoffs/SPRINT.md        thin session bootstrap
│   ├── handoffs/REVIEW.md        thin review-session bootstrap
│   ├── briefs/task-NN.md         two halves, at most 80 lines
│   ├── review/MERGE-VADER-REPORT.md
│   ├── review/UNCLE-BOB-REPORT.md
│   ├── whats-broken.md           only while a debug is live
│   └── REPORT.md                 sprint summary, at most 50 lines
└── archives/<task-slug>.md       at most 30 lines, written by prune-ticket
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
  architect: sonnet # derived: large scope would pull opus
  intern: haiku
  gitty-up: haiku
  wingman: opus
  terry-toolchain: sonnet
  merge-vader: opus
  uncle-bob: sonnet
handoff-context:
  scope: sm # sm | med | large
  plan-first: false # true when a compaction is expected
  branch-name: fix/rate-limit
  worktrees-okay: false
investigations:
  - rate-limit-ledger-id # lets-investigate ids this ticket came from
```

Three derivation rules matter day to day. The engineer is `sonnet` at every scope, and the ticket
value is the default for every task; the primary may bump one gnarly task a tier at dispatch,
logging the reason in that task's ASKED stanza. The architect comes from the scope answer: `large`
gives `opus`, `sm` or `med` gives `sonnet`. `plan-first: true` means the next
session writes `plan.md` before any dispatch and the SPRINT.md handoff carries the switch-models
reminder.

The schema is deliberately closed: no key enters it without a named consumer in the flow. A
`review-weight` block existed briefly and was cut for exactly that reason.

## Handoffs stay thin

`SPRINT.md` and `REVIEW.md` contain zero facts that already live in `ticket.yml` or the issue.
They are a bootstrap pointer: read the ticket, read issue N, here is your role, invoke this
skill. Duplicated facts drift, and the next session reads `ticket.yml` first anyway.

## Briefs

`briefs/task-NN.md` holds the two-half contract for one task. The primary writes the ASKED half
at dispatch; the engineer appends the DONE half on completion; fact-checker checks one against the
other. The 80-line cap is load-bearing: a brief that needs more space is a task that should have
been split. Field-level detail is in `plugins/mightymodels/skills/agents-assemble/references/contracts.md`.

## Reports and reviews

`REPORT.md` closes a sprint in at most 50 lines: what shipped, what deviated, what remains.
Review reports land under `review/` so they live and die with their ticket instead of littering
the repo root; both review skills fall back to the repo root with an ignore guard when no active
ticket exists, which keeps them usable outside mightymodels repos.

`whats-broken.md` exists only while a debug is live. It carries the current falsifiable
hypothesis and its test, gets regenerated per attempt, and its presence blocks `prune-ticket`.

## Archives and pruning

`/prune-ticket` compresses a finished ticket into `archives/<slug>.md`: what shipped, the PR
link, key decisions, and any gotcha the next person would want. Thirty lines is the cap, and the
point. During pruning the skill also proposes cascading documentation updates as diffs, README
claims the change invalidated, for the user's approval, then deletes the ticket directory.

## Git hygiene

Ticket creation runs an idempotent ignore ritual:

```bash
git check-ignore -q .mightymodels 2>/dev/null || echo '.mightymodels/' >> .git/info/exclude
```

`info/exclude` is local and needs no commit, and it is the safer default: `briefs/` and
`review/` carry raw command output that can hold secrets, so local-only exclusion means a
careless `git add -A` cannot ship them. A team adopting mightymodels can promote the entry to a
committed `.gitignore`; when tracking is wanted, track `archives/` and `*/ticket.yml` only.

## The canonical definitions

This page orients; the references define.
`plugins/mightymodels/skills/open-ticket/references/ticket-schema.md` is the schema with its
derivation rules, `plugins/mightymodels/skills/open-ticket/references/mightymodels-dir.md`
is the layout with the writer/reader matrix, and
`plugins/mightymodels/skills/agents-assemble/references/contracts.md` holds the severity table
and verdict vocabularies. Agents read those files; nothing reads this
one.

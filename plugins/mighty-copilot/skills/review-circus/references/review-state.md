# Review state

Read before the first `review` call in a session, and before another skill reads a review run. The `review` tool (`state/review`) is the only writer of a run's rows; `snapshot` and `close` read a ticket's latest run and write none.

## What a run keeps

A run is rows in the state database, `mightymodels.db` in the plugin data directory, and a directory of files under `.mightymodels/`. `start` writes the run's row and creates the directory. The server and `mightymodels verify run` add `.mightymodels/` to the repository's local exclude file, so the files are never tracked, and the database is outside the repository.

With a ticket: `.mightymodels/SLUG/review/RUN/`. Without one: `.mightymodels/.runtime/reviews/RUN/`. `RUN` is the UTC start time, `YYYYMMDD-HHMMSS`; a second `start` in the same second is refused.

| Table                 | Written by                                  | Holds, one row per run, finding, decision or outcome                                                                                                          |
| --------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `review_runs`         | `start`                                     | `run_id`, `slug`, `scope`, `base`, `head` (HEAD at the start), `depth`, `emphasis`, `weights`, `personas`, `models`, `created_at`                             |
| `review_findings`     | `add`                                       | `finding_id` (`F1`, `F2`, ...), `sources`, `severity`, `kind`, `security`, `title`, `location`, `fix`, `verify`, `evidence_kind`, `evidence_cite`, `conflict` |
| `review_dispositions` | `dispose` writes; `add` deletes (see below) | `decision`, `reason`, `by`, `at`                                                                                                                              |
| `review_outcomes`     | `resolve` writes; `add` deletes (see below) | `result`, `commit`, `reason`, `at`                                                                                                                            |

| File                                           | Written by                                                   | Holds                      |
| ---------------------------------------------- | ------------------------------------------------------------ | -------------------------- |
| `MERGE-VADER-REPORT.md`, `UNCLE-BOB-REPORT.md` | the primary, from the persona's response unchanged           | the reports `add` reads    |
| `uncle-bob-metrics.json`                       | `mightymodels review-metrics`                                | the structure measurements |
| `report.md`                                    | the primary, from the `report` answer                        | the full report            |
| `pr-comment.md`                                | the primary, from the `report` answer with `shape` `comment` | the abridged PR comment    |

`report` returns text and writes no file. The primary writes `report.md` and `pr-comment.md` from its answers, and posts the second with `gh pr comment`. A persona report that is a symlink is read as missing. `list` answers one line per run: run id, slug, depth, finding count, verdict.

## What `add` reads

`add` reads one persona's report from the run directory. Only the `## Findings` section counts, up to the next `##` heading. Under a severity heading (`### Blocker`, `Critical`, `High`, `Medium` or `Low`) each finding is one block:

```markdown
#### MV-2 | security | Session token compared with ==

- Evidence: `src/auth/session.py:88` `if token == stored:`
- Fix: Use `hmac.compare_digest` for the comparison.
- Verify: `uv run pytest -q tests/test_session.py`

#### UB-3 | [F1] Output argument in drain - `src/queue/worker.py:101`

- Evidence (idiom): https://docs.python.org/3.14/tutorial/controlflow.html#defining-functions
- Fix: Return the results from `drain`.
- Verify: `rg -n 'def drain' src/queue/worker.py`
```

- The id is the persona's own, `MV-n` in merge-vader's report and `UB-n` in uncle-bob's.
- `location` is the first word of merge-vader's untyped `Evidence:` bullet, and for uncle-bob the backticked path after the dash in the heading. It must be `path:line` or `path:start-end`.
- `title` is the heading text, and the `Fix:` and `Verify:` bullets are required. A bullet's continuation lines join it. Bullets the tool does not read (Why it matters, Confidence, Signals, Architect escalation) stay in the report file.
- `kind` and `security` come from the dimension, never from another label: merge-vader's `quality` is a quality finding, `security` is a defect with the security mark, and `sdlc`, `docs` and `plan` are defects. Every uncle-bob finding is a quality finding.
- A quality finding at Medium or above needs a typed bullet naming one kind (`Evidence (metric): <cite>`, or `idiom` or `convention` in its place; idiom-evidence.md); at Low it needs none.
- `severity` is the heading's, with uncle-bob's Blocker recorded as High.
- Every text field is scanned for secrets and redacted before it is stored.

One bad finding rejects the whole batch, and nothing is written. `add` refuses a missing report, a report without `## Findings`, an unknown severity heading, a finding before any severity heading, a heading it cannot read, an id that is not the persona's own, an unknown dimension or evidence kind, an empty title, location, Fix, Verify or evidence cite, a location of another shape, and a quality finding at Medium or above without typed evidence.

Each new finding takes the next id, `F1`, `F2`, and so on. A finding whose location overlaps a recorded one on the same file, in this report or an earlier one, merges into it: the sources join, the higher severity wins together with its title, location, Fix, Verify and kind, the security mark stays if either had it, and a gap of two or more levels records a `conflict` the user decides in the gate.

## Dispositions

`dispose` takes `by` and either `finding`, one finding id the tool asks the user about, or `decisions`, a map from finding id to `decision` and `reason`. Decisions: `fix`, `defer` (ticketed for later), `accept-risk`, `dismiss`. The last two need a non-blank reason, and an unknown finding id rejects the call. A later `dispose` replaces a finding's decision, and the answer lists the findings still undecided. Only `fix` routes to remediation.

A decision stands for the finding as the user saw it. When a later `add` merges into a decided finding and changes it, the finding's decision and outcome rows are deleted and `add` answers that it is `back to undecided`; the gate shows it again.

## Outcomes and verdict

`resolve` takes `finding`, `result`, `commit` and `reason`, and only for a finding the user chose to fix. `fixed` needs `commit`, and `failed` or `blocked` need `reason`. A later `resolve` replaces the outcome.

The verdict is computed from the findings, the decisions and the outcomes, never written by hand. A finding is open until its outcome is `fixed` or its decision is `dismiss`: undecided, deferred, accepted and failed findings are all open.

- **BLOCK**: an open Critical, or an open High the user did not accept as risk.
- **MERGE WITH CONDITIONS**: anything else open at Medium or above, including accepted and deferred findings.
- **CLEAR**: only Low findings remain open.

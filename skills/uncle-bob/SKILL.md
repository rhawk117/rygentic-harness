---
name: uncle-bob
description: >
  Analyze a codebase and grade its code quality against Robert C. Martin's
  ("Uncle Bob's") published principles: SOLID, the Clean Code rules and
  smells catalog (C/E/F/G/N/T), and the Clean Architecture component
  principles and metrics (dependency cycles, Instability, Abstractness,
  Distance from the Main Sequence). Produces UNCLE-BOB-REPORT.md with letter
  grades, severity-ranked findings, file:line evidence, and a repair
  sequence. Use this skill whenever the user asks about code quality,
  cleanliness, maintainability, SOLID compliance, "clean code", technical
  debt level, refactoring priorities, or wants a codebase reviewed, graded,
  audited, or assessed — even if they never say "Uncle Bob". Also triggers
  on "how bad is this code", "is this codebase well structured", "review my
  repo", or any request to evaluate an entire project rather than a single
  diff.
---

# Uncle Bob Codebase Grader

Grade a codebase the way Robert C. Martin's books say to grade it: findings
tied to named principles, mechanical metrics computed deterministically,
judgment applied only where the doctrine requires judgment, and a letter
grade whose arithmetic the reader can check.

Two modes. **Pure** (default): the book as written — 20-line function limit,
comments as failures, one switch per selection type. **Calibrated** (only
when the user asks, with words like "calibrated", "pragmatic", "less
dogmatic"): same analysis, but contested-doctrine findings are tagged and
capped per references/report.md. Never silently downgrade pure mode; the
user chose a skill named uncle-bob.

## Workflow

### 1. Recon (five minutes, no judgments yet)

Inventory the repo: languages, size (`git ls-files | wc -l`, LOC), directory
layout, README, how it builds and how tests run. Two catalog items are
checkable right here: E1 (build requires more than one step) and E2 (tests
require more than one step). Note the top-level directory names for the
Screaming Architecture test later. If the target is huge (>~150k LOC),
agree with yourself on a subsystem scope and say so in the report rather
than sampling everything thinly.

### 2. Mechanical pass

Run the bundled script (stdlib-only, py/js/ts):

```bash
python3 scripts/metrics.py <repo_root> --out <repo_root>/uncle-bob-metrics.json
```

Write the output INSIDE the repo under review, never to a shared temp path —
concurrent reviews collide on `/tmp/metrics.json` and you will quote another
repo's numbers. Remove the file after reporting if the user doesn't want it.
Use `--package-depth 2` when the repo is one top-level package. The script
computes the layer that must not drift between runs: function LOC/params/
flag-args/nesting, file sizes, long lines, test-to-source ratio, the module
import graph, dependency cycles (ADP), and per-package Ca/Ce/I/A/D.

For languages the script doesn't parse (Go, Java, Rust, C#...), skip it and
gather the same facts by reading — mark every such number as estimated in
the report. JS/TS function metrics are approximate by design; the import
graph is reliable.

The script's output is a *map, not a verdict*: it tells you where to read.
Never convert a metrics row straight into a finding without opening the
file — the false-positive lists exist because mechanical matches lie.

### 3. Read the doctrine, then read the code

Read all three rubric references before judging (they are the rubric —
do not grade from memory):

- `references/solid.md` — the five principles: detection signatures AND
  the false-positive list for each. The false positives are Martin's own
  carve-outs; applying the principles without them produces a caricature.
- `references/clean-code.md` — chapter rules, numeric thresholds, and the
  complete ch. 17 smells catalog (cite findings by ID: G23, F3, N7...).
- `references/components.md` — component principles, how to interpret
  I/A/D and cycles, the Dependency Rule, Screaming Architecture, and the
  testability probe.

Then read code in priority order:

1. Worst offenders from metrics.json (longest functions, biggest files,
   most params) — confirm or dismiss each candidate.
2. Every member of every dependency cycle.
3. Entry points / main / composition roots (is construction confined
   there?).
4. Highest fan-in modules — the code everything rests on deserves the
   closest read.
5. The test suite: F.I.R.S.T. properties, one concept per test, assert
   density, whether tests reach use cases without frameworks.
6. A spread of ordinary files for names, comments, error handling, and
   consistency (G11) — pick across packages and authors, not just hotspots.

Under ~25 source files: read everything, no sampling. Larger: read the
priority set plus enough ordinary files that a naming/comment/error-handling
judgment rests on at least a dozen files from different areas. Track what
you read — the report's coverage section states it.

While reading, collect findings as you go: principle ID, file:line, the
evidence line(s), severity per references/report.md. Check every candidate
against the relevant false-positive list before recording it.

### 4. Architecture pass

With metrics.json and your reading: apply the Dependency Rule checks and
Screaming Architecture test from components.md; interpret the package table
(SDP inversions, Zone of Pain candidates — remember volatility qualifies
them); run the testability probe. On git repos, `git log --stat` on the
worst files is cheap evidence for CCP/SRP (does one change ripple across
packages? does one file change for five unrelated reasons?).

### 5. Grade and write

Follow `references/report.md` exactly: severity model, category grades,
weighted overall grade, the no-tests cap, and the report template. Write
`UNCLE-BOB-REPORT.md` to `.mightymodels/<task-slug>/review/` when an active
ticket directory exists (the one the user names, else the newest
`.mightymodels/*/ticket.yml` on this branch); otherwise at the repo root
unless told otherwise.

### 6. Verify before delivering

For every Blocker and High finding: reopen the file, confirm the line
number, the quote, and that no false-positive carve-out applies. Recompute
the overall grade from the category table by hand. Confirm no finding
cites code you never read. Delete anything that fails. A wrong file:line
in a report that grades other people's rigor is a self-inflicted F.

## Honesty rules

- Findings require read evidence. Metrics alone go in "The numbers", not
  in "Findings".
- A clean codebase gets an A and a short report. Do not manufacture
  findings to look thorough; Needless Complexity findings exist for
  over-engineered code, so both failure directions are covered.
- Grade the code, not the developers. No sarcasm at anyone's expense.
- State scope limits plainly (files unread, languages unparsed, metrics
  estimated). An overclaimed review is itself a G26 violation — be precise.

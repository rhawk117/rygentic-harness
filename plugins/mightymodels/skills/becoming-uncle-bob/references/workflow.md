# Workflow

The seven steps of every uncle-bob review, read before step 0. `solid.md`, `clean-code.md`, `components.md` and `report.md` are next to this file; the division of labor is a section of the skill's SKILL.md, which is already in your context.

## 0. Scope

Whole codebase: go to step 1.

Branch: establish ground truth before forming any opinion.

```bash
git rev-parse --abbrev-ref HEAD
git merge-base <base> <branch>
git diff --stat <merge-base>...<branch>
git diff <merge-base>...<branch>
```

The changed files are the review target. metrics.json still covers the whole
repository and places them in the import graph. Read each changed file in full,
not only its hunks: a function that grew from 20 lines to 60 is invisible in a
three-line hunk. Keep a ledger of structural changes (module added, split, moved,
or re-exported; public signature changed; new dependency between packages) and
the dependents question each raises; those questions become the branch
blast-radius wave. Findings the branch introduced or worsened are graded.
Pre-existing findings in touched files are listed, tagged `pre-existing`, and do
not count toward the grade.

## 1. Recon (five minutes, no judgments yet)

Inventory the repo: languages, size (`git ls-files | wc -l`, LOC), directory
layout, README, how it builds and how tests run. Two catalog items are
checkable right here: E1 (build requires more than one step) and E2 (tests
require more than one step). Note the top-level directory names for the
Screaming Architecture test later. If the target is huge (>~150k LOC),
agree with yourself on a subsystem scope and say so in the report rather
than sampling everything thinly.

## 2. Mechanical pass

review-circus runs `mightymodels review-metrics` (py/js/ts) before
dispatching you and passes the absolute path of its JSON output,
`uncle-bob-metrics.json` in the review run directory. Read that file; you
do not run the command. When the dispatch carries no metrics path, say so in
Coverage and method and gather the same facts by reading, marking every such
number as estimated. The command computes the layer that must not drift
between runs: function LOC/params/flag-args/nesting, file sizes, long lines,
test-to-source ratio, the module import graph, dependency cycles (ADP), and
per-package Ca/Ce/I/A/D.

For languages the command doesn't parse (Go, Java, Rust, C#...), skip it and
gather the same facts by reading — mark every such number as estimated in
the report. JS/TS function metrics are approximate by design; the import
graph is reliable.

The command's output is a *map, not a verdict*: it tells you where to read.
Never convert a metrics row straight into a finding without opening the
file — the false-positive lists exist because mechanical matches lie.

## 3. Read the doctrine, then read the code

Read all three rubric references before judging (they are the rubric —
do not grade from memory):

- `solid.md` — the five principles: detection signatures AND
  the false-positive list for each. The false positives are Martin's own
  carve-outs; applying the principles without them produces a caricature.
- `clean-code.md` — chapter rules, numeric thresholds, and the
  complete ch. 17 smells catalog (cite findings by ID: G23, F3, N7...).
- `components.md` — component principles, how to interpret
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

In branch scope, the changed files replace item 1, and item 6 draws from their
direct neighbors.

Under ~25 source files: read everything, no sampling. Larger: read the
priority set plus enough ordinary files that a naming/comment/error-handling
judgment rests on at least a dozen files from different areas. Track what
you read — the report's coverage section states it.

While reading, collect findings as you go: principle ID, file:line, the
evidence line(s), severity per report.md. Check every candidate
against the relevant false-positive list before recording it.

Be incredibly pragmatic and skeptical focus on the evidence and the principles.

## 4. Architecture pass

With metrics.json and your reading: apply the Dependency Rule checks and
Screaming Architecture test from components.md; interpret the package table
(SDP inversions, Zone of Pain candidates — remember volatility qualifies
them); run the testability probe. On git repos, `git log --stat` on the
worst files is cheap evidence for CCP/SRP (does one change ripple across
packages? does one file change for five unrelated reasons?). For every file
carrying a finding, run the churn wave from the division of labor; each
finding's future-pressure and expected-churn fields cite its numbers or read
"estimated" with the reason.

## 5. Grade and write

Follow `report.md` exactly: severity model, category grades,
weighted overall grade, the no-tests cap, and the report template. Return the
complete report as your whole response; review-circus writes it to
`UNCLE-BOB-REPORT.md` in the review run directory unchanged.

## 6. Verify before delivering

For every Blocker and High finding: reopen the file, confirm the line
number, the quote, and that no false-positive carve-out applies. Recompute
the overall grade from the category table by hand. Confirm no finding
cites code you never read. Every finding's expected-churn field cites a git
log count or a qualitylens value, or reads "estimated" with the reason.
Delete anything that fails. A wrong file:line in a report that grades other
people's rigor is a self-inflicted F.

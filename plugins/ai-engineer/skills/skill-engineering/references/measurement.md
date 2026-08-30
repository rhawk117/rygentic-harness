# Measurement

How to get a number you can defend, and how to know when you cannot get one.

## Contents

- [Why calibration comes first](#why-calibration-comes-first)
- [Arms](#arms)
- [Tiers](#tiers)
- [Assertion kinds](#assertion-kinds)
- [Execution quality](#execution-quality)
- [Triggering](#triggering)
- [What a sample size can resolve](#what-a-sample-size-can-resolve)
- [Comparing iterations](#comparing-iterations)
- [Reading a benchmark honestly](#reading-a-benchmark-honestly)

## Why calibration comes first

Run `skilleng calibrate` before anything else, every session, on every host.

It installs two control skills — one whose description claims every request, one about
recalibrating submersible ballast manifolds — and runs your queries against both. If the
harness cannot separate them, it stops and says so.

This catches the failure that has no other symptom. When the CLI is missing, the model id is
wrong, auth has expired or hooks are not attached, every run fails identically, and on a
balanced trigger set that produces a score near 50% — every should-not-trigger query
"passes" because nothing triggered. That is indistinguishable from a mediocre working
description, and it will absorb an afternoon.

The separation between controls is also the number you should quote when someone asks how
much to trust a difference. If the controls separate by 60 points, a 5-point difference
between two skill versions is below the instrument's resolution.

## Arms

| Arm | Setup | Answers |
|---|---|---|
| `baseline` | skill absent | Would the model have done this anyway? |
| `available` | installed, unmentioned | Does it fire when it should? |
| `forced` | invoked explicitly as `/skill-name` | Given that it fires, does it help? |

Both hosts support explicit `/skill-name` invocation, which is what makes `forced` portable.

**lift** = forced − baseline. Execution quality with trigger variance removed. This is the
causal question: does following these instructions produce better work?

**realized** = available − baseline. What a person actually gets, triggering included.

The gap between them is the diagnosis. Strong lift and weak realized means the instructions
are good and the description is not — do not rewrite the body. Weak lift means the
instructions are the problem and no amount of description tuning will save them.

Deltas are computed by arm role, never by directory order. A tool that sorts config
directories and subtracts the first from the second inverts its sign whenever the baseline
happens to sort first, which is how a skill that went 0% → 100% gets reported as −1.00.

## Tiers

| Tier | Runs/eval | Adds | Use when |
|---|---|---|---|
| `quick` | 1 | raw data, error rate, MDE. **No intervals.** | drafting, fast loops |
| `standard` | 3 | paired bootstrap intervals, blinded grading | making a decision |
| `rigorous` | 8 | confirmation run on fresh sample, grader reliability, ablation | before shipping or sharing |

Tiers change sample size and which analyses run. They never change the schema, and controls
run at every tier. A `quick` result is comparable-with-caveats to a `standard` one, not from
a separate universe.

The gate is mechanical: at `quick` the report cannot render an interval even if you ask. This
is deliberate. Reporting `± 0.06` from three samples is not a small overstatement; it is a
claim about sampling error that three samples cannot support.

## Assertion kinds

Every assertion declares how much it can be trusted.

**`mechanical`** — a shell command run in the outputs directory. Exit 0 passes. Deterministic,
cheap, trustworthy at any n. Prefer these; a check like `test -f report.csv && head -1
report.csv | grep -q margin` beats any amount of judgement.

**`judged`** — decided by the blinded grader in `agents/grader.md`. Necessary for anything
about quality, and it carries grader noise. At `rigorous` a sample is double-graded and
Cohen's κ is reported, so you know the noise floor under your pass rate.

**`human`** — surfaced for review, never auto-scored. The right home for taste. Forcing an
assertion onto a judgement call does not make it objective; it makes the subjectivity
invisible.

A mechanical assertion with no `check` command is rejected at load. An assertion that
declares determinism it does not have is worse than an honest judged one.

## Execution quality

Runs are paired: the same prompt in every arm, so the natural unit is the per-eval delta, and
the interval comes from bootstrapping those deltas. Pooling every run from every eval into one
mean ± stddev — the predecessor's approach — conflates between-eval variance with
between-run variance and throws away the pairing that gives the design its power.

Grading is blinded at `standard` and above: skill-identifying lines are stripped from
transcripts before the grader sees them. An unblinded grader on the primary endpoint is the
single largest validity problem in most skill harnesses, and it is nearly free to fix.

Errors are excluded from scores and reported as a rate. A benchmark with a 40% error rate
may be arithmetically correct and still worthless.

## Triggering

This is classification, so it gets a confusion matrix rather than a pass count. Precision,
recall and accuracy come with Wilson intervals, which are correct at the small n this
always has.

**Competitive mode is the real measurement.** Pass `--roster` with the other skills the
person actually has installed. Isolated mode — one skill, nothing to compete with — is an
optimistic upper bound and cannot see cannibalisation, the case where a broad description
starts taking invocations from a neighbour. The report names the neighbours it stole from.

**Query hygiene.** A query that names the skill is a forced invocation, not a trigger test;
the harness detects and excludes those. Good queries look like real messages: file paths,
company names, column names, a little backstory, occasional typos and lowercase. Weak
negatives are the commonest defect — "write a fibonacci function" as a negative for a PDF
skill tests nothing. The valuable negatives are near misses that share vocabulary with the
skill but need something else.

**Comparing two descriptions** uses exact McNemar on the paired per-query outcomes. Comparing
raw pass counts across a re-run confuses trigger noise with a real difference.

Selection is where trigger optimisation goes wrong. Taking the best of five candidates on a
fixed held-out set of eight queries is fitting to that set, whatever it is called, and the
winning score is upward-biased. At `rigorous` the selected description gets a confirmation
run on fresh queries and *that* number is the headline; the selection score is a diagnostic.

## What a sample size can resolve

Every report prints its minimum detectable effect, before you spend anything. Some numbers
worth internalising:

- A 20-query trigger eval resolves differences of roughly **40 points**. It cannot tell 70%
  from 80%. Most published description tuning is inside its own noise.
- Five paired evals at typical variance resolve about **0.30**. Resolving 0.10 needs around
  50 evals.
- 7/8 on a held-out set has a 95% interval of roughly **[53%, 98%]**.

None of this means small runs are useless. It means a small run answers "is this obviously
broken?" and not "is version B better than version A?", and the two questions deserve
different amounts of confidence.

## Comparing iterations

Provenance records the model, host, skill content hash and assertion set hash. `skilleng
bench --compare-to N` refuses the comparison when any of those changed, naming which.

The assertion hash is the important one. Sharpening assertions between iterations always
produces apparent improvement, because assertions get sharpened toward what the current
version already does well. If the ruler moved, either re-grade the earlier iteration under
the new assertions or start the trend line over.

## Reading a benchmark honestly

Read the diagnostics before the table. They carry the error rate, the resolving power,
non-discriminating assertions, missing instrumentation, and low trigger rates that explain an
apparently weak result.

An assertion that passes in every arm is not evidence the skill helps — it cannot
distinguish, so it dilutes the score toward the middle regardless of what the skill does.

Note what is *not* reported: cost per run in money, quality drift over long sessions, and any
outcome nobody wrote an assertion for. The last one is the dangerous omission — a skill can
score well on every assertion and still be unpleasant to use.

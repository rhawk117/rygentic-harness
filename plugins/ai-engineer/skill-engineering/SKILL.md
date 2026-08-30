---
name: skill-engineering
description: >-
  Engineer, measure and maintain agent skills for Claude Code and GitHub Copilot — draft a
  SKILL.md, prove it actually helps with a calibrated eval harness, tune its triggering, and
  package it with a security report. Use this whenever someone wants to create, write, edit,
  audit, test, benchmark, evaluate, optimize or ship a skill (SKILL.md, .skill file,
  .github/skills, .claude/skills, AGENTS.md-adjacent agent instructions), asks whether a skill
  is any good or whether it beats no skill at all, wants a description to trigger more
  reliably, or wants an existing skill reviewed after a model upgrade. Also use it for
  "turn this workflow into a skill", "make a skill for X", "why isn't my skill firing", and
  "is this skill worth keeping" — even when the word "skill" is the only signal in the request.
license: Apache-2.0
compatibility: >-
  Python 3.11+, PyYAML. Measurement additionally needs a host CLI on PATH (`copilot` or
  `claude`). Linting, packaging and the security report work with no host installed.
---

# Skill Engineering

A skill is not a document you write once. It is an artifact with a test suite, a trigger
surface, a context cost and a supply chain, and most of its life happens after it ships —
models upgrade, neighbouring skills steal its invocations, bundled scripts rot. This skill
covers that whole life, on both Claude Code and GitHub Copilot.

Everything here is built on one conviction: **a measurement you cannot check is worse than
no measurement**, because it gets acted on. The predecessor to this skill printed `±0.06`
from three samples, computed its headline delta in sorted-directory order (so improving a
skill reported as a regression), and emitted a full benchmark of zeros — with placeholder
labels and exit code 0 — whenever its documented layout was followed. None of that announced
itself. That is the failure mode this design exists to prevent.

## Three problems wearing one coat

Almost every mistake in skill development comes from treating these as one activity. They
have different failure modes, different sample-size needs, and different notions of "better".
Work out which one you are on before doing anything else.

| Problem | The question | How it is measured | Read |
|---|---|---|---|
| **Authoring** | Is this well written and is every line earning its context? | Lint, budgets, ablation | `references/authoring.md` |
| **Triggering** | Does it fire when it should, and not when it shouldn't? | Classification: precision, recall, cannibalisation | `references/measurement.md` |
| **Execution** | Given that it fires, does the outcome get better? | Causal: paired arms, blinded grading | `references/measurement.md` |

A skill that never triggers and a skill that triggers and gives bad answers produce the
identical disappointment, and mixing the two is how people spend a week rewriting
instructions when the description was the problem. If someone says "my skill isn't working",
finding out which of these they mean is the first useful thing you can do.

## The loop

1. **Understand the work.** What should the skill do, when should it fire, what does good
   output look like? If this conversation already contains the workflow they want captured,
   mine it first and confirm rather than re-interviewing.
2. **Draft.** `references/authoring.md`. Then `skilleng lint`.
3. **Calibrate the instrument.** `skilleng doctor`, then `skilleng calibrate`. Never skip
   this. Details below.
4. **Measure.** `skilleng run` across arms, then `skilleng bench`.
5. **Put outputs in front of the person before you form your own opinion.** They know the
   task; you know the harness. Their reaction to real output is the highest-value signal in
   the loop and it is cheap to collect.
6. **Improve, and re-measure.** Generalise from feedback rather than patching the specific
   example — see `references/authoring.md`.
7. **Ship.** `skilleng package`, which emits a security report alongside the archive.

Steps flexible, order negotiable. If someone says "skip the evals, just vibe with me", do
that — but say plainly that what comes out is an opinion, not a measurement.

## Four rules that are not negotiable

These exist because each one, violated, produces a confident wrong number rather than an
error. They are enforced in code, so you will not usually have to think about them.

**Calibrate before measuring.** `skilleng calibrate` installs a positive control (a skill
whose description says to use it for everything) and a negative control (one about
submersible ballast manifolds) and checks the harness can tell them apart. This is not a
smoke test — the separation between the controls *is* the instrument's resolving power, and
the report quotes it. Without it, a completely dead harness scores around 9/20 on a balanced
trigger set, because every should-not-trigger query "passes". That looks like a mediocre
working description, and people optimise against it for hours.

**An error is not a failure.** Timeouts, auth failures, missing CLIs and non-zero exits are
a third outcome class. They are excluded from scores and reported as a rate. Never let "we
could not measure this" become "the skill did badly here".

**The ruler cannot move mid-experiment.** Assertions are hashed. Change one and the harness
refuses to plot a trend through the change. Sharpening assertions between iterations always
looks like progress, and it is the easiest way to fool yourself.

**Say only what the tier permits.** `quick` (n=1) shows point estimates and is forbidden
from rendering an interval. `standard` (n=3) adds paired bootstrap intervals. `rigorous`
(n=8) adds a confirmation run on a fresh sample. Every report prints its minimum detectable
effect, so the person can see in advance what their sample size can and cannot resolve.

## Three arms, because "with the skill" is two questions

| Arm | Setup | Answers |
|---|---|---|
| `baseline` | skill absent | Would the model have done this anyway? |
| `available` | installed, unmentioned | Does it fire when it should? |
| `forced` | invoked as `/skill-name` | Given that it fires, does it help? |

The two reported deltas follow from this: **lift** = forced − baseline (execution quality,
trigger noise removed) and **realized** = available − baseline (what a person actually gets).
When lift is strong but realized is weak, the instructions are fine and the description is
the problem. Collapsing these into one "with skill" arm makes that diagnosis impossible.

## Commands

Run from the skill-engineering directory, or with it on `PYTHONPATH`. Every command takes
`--help`, and the help is the reference — do not re-describe flags here.

```bash
python -m skilleng lint      <skill-dir>
python -m skilleng doctor    [--probe-hooks] [--host copilot-cli|claude-code]
python -m skilleng calibrate --host H --queries q.json --workspace W
python -m skilleng run       --skill S --evals e.json --workspace W --host H [--tier standard]
python -m skilleng bench     --workspace W [--compare-to N]
python -m skilleng trigger   --skill S --queries q.json --host H [--roster other-skill-dirs...]
python -m skilleng package   <skill-dir> [--out DIR]
python -m skilleng gate      --workspace W --phase improve
```

`skilleng run` refuses to start on a skill with load-blocking lint errors, and refuses to
run without a passing controls gate unless explicitly overridden. Those refusals are the
feature; do not route around them without telling the person you did.

## Hosts

Portable by construction. The core is four things — headless CLI invocation, hook-based
instrumentation, spec-compliant skill install, filesystem outputs — and both hosts have all
four. Skills themselves are already portable: Copilot implements the same Agent Skills
specification, so a SKILL.md that lints here works in `.github/skills/`, `.claude/skills/`
and `~/.copilot/skills/` alike.

Invocation is detected from **hooks**, not by parsing transcripts or scraping stdout. Both
hosts hand a JSON payload to a command; `skilleng/hookshim.py` normalises both spellings into
one event log, and everything downstream is host-agnostic. This is ground truth rather than
inference, and it is why trigger detection here does not care whether the model opened with
a todo list.

Read `references/surfaces.md` before assuming behaviour carries between hosts — instruction
mechanisms differ per surface, and a description tuned on the CLI can under-trigger in code
review. Run `skilleng doctor --probe-hooks` on a host you have not used before; it reports an
adapter mismatch loudly instead of letting every run score as "never triggered".

## Working with the person

People arrive here from wildly different backgrounds — some are shipping agent
infrastructure, some opened a terminal last week because a skill sounded useful. Read the
cues and match them.

Jargon worth translating unless they have signalled otherwise: *assertion*, *confidence
interval*, *held-out set*, *baseline arm*. Words that are usually fine: *test*, *benchmark*,
*trigger*. A short parenthetical is cheap and never insulting when it is brief.

Two things worth saying out loud even when they are unwelcome. First, when the sample is too
small to answer the question they are asking — "three runs cannot distinguish these; I can
tell you the raw numbers or we can spend more" is more useful than a number with an implied
precision. Second, when the evidence says the skill is not helping. A skill that measurably
does nothing is worth deleting, and nobody else in the loop is going to say so.

## Where to read next

Load exactly one of these when you reach that phase; they are written to be read alone.

- `references/authoring.md` — how to write the skill itself: structure, descriptions,
  progressive disclosure, when to bundle a script, how to generalise from feedback.
- `references/measurement.md` — arms, tiers, statistics, trigger evaluation, what a given
  sample size can and cannot resolve.
- `references/harness.md` — mechanics: workspace layout, event log, gates, the eval file
  format, and what still needs verifying on each host.
- `references/security.md` — the threat model, sandbox isolation, and what the packaging
  security report covers.
- `references/surfaces.md` — Claude Code, Copilot CLI, Copilot cloud agent, VS Code, and the
  instruction mechanisms that are not skills.
- `agents/grader.md` — the blinded grader. Load when judged assertions need deciding.
- `agents/analyst.md` — transcript and benchmark analysis, including repeated-work detection.

## Verifying this harness

`python -m unittest discover -s tests` — 50 tests, each pinning a specific way a skill
measurement tool can lie. If you change anything under `skilleng/`, run them. If you are
about to trust a number this tool printed and the suite has never been run in this
environment, run them first.

---
name: crashout
description: Use when the user explicitly invokes crashout to record dissatisfaction, diagnose the failure, and await approval before resuming work.
disable-model-invocation: true
---

# crashout

The user is yelling at you. On purpose. This skill is mightymodels's pressure
valve and flight recorder in one: the user vents at full volume, you capture
the signal, and the journal turns repeated tilt into standing corrective
actions that outlive the session.

Two modes:

- `/crashout <rant>` — intake. The user is expressing extreme dissatisfaction.
- `/crashout journal` (also `review`, `patterns`, `stats`) — read-back. Report
  what the journal says.

Invoked bare, with no rant and no journal keyword: the floor is theirs. Reply
with one short line inviting the rant and nothing else.

## Intake protocol

Follow the steps in order. The order is the point: momentum is what caused
this, so the protocol starts by killing it.

### 1. Stop changing things

Halt the work. Do not finish the in-flight edit, do not "just complete this one
step", do not write, commit, or revert anything until the user says go. A
crashout means your current approach is wrong at a level ordinary feedback
failed to fix; anything built on that approach after the signal arrives is
rework you are generating on purpose.

Stopping applies to *mutation*, not to *understanding*. Reading files, running
git commands that only report, and running the failing test to watch it fail
are all still on the table and step 4 expects them. What you must not do is
change the repo before the user re-authorizes you.

### 2. Read the whole rant

Read every line before you react to any line. Rants are compressed,
high-signal feedback wearing a loud envelope: the caps and profanity are
packaging, the failures inside are real. Do not respond to the first grievance
before you have read the last one.

### 3. Check the record

Before diagnosing, look at whether this has happened before:

Call `mcp__plugin_mightymodels_state__crashout` with action `stats`:

```json
{"request": {"action": "stats"}}
```

It prints the journal's patterns: the entry count, severity and verdict counts, how often you
barked back, the first and last times, every failure tagged with its day, verdict and
severity, and the standing corrective actions, each once. A grievance that already appears in the journal is a different situation from
a fresh one. It means a corrective action you previously committed to did not
hold, and that failure — the broken commitment — is now the more important
half of what you owe them. Repeating "I'll be more careful" to someone holding
a log of the last three times you said it is how a journal becomes a joke.

If the journal is empty (the tool says `no crashouts recorded yet. serenity.`), note that and
move on.

### 4. Diagnose against evidence

Establish what actually happened, from the repo rather than from your memory
of being right:

- the diff, the commit, the file as it stands now (`git show`, `git log`, read
  the file)
- the failure itself — run the test, reproduce the bug, read the real error
- their earlier instructions in the conversation and in any decision log

Push this until you know the *actual* fix, not just the category of fix. The
value you have here is diagnosis, and diagnosis is read-only. "The assertion
compares two clock reads with a 100ms margin, so it races on a loaded box" is
worth ten times "the test was flaky" — and it is what makes the next step
something the user can approve in one word.

For each distinct grievance also establish whose doing it was: yours, or
something else — their own earlier instruction, an environment issue, upstream
breakage. That check matters in both directions. Blaming yourself for their
config is as dishonest as blaming their config for your scope creep.

### 5. Verdict

Call it honestly: `deserved`, `split`, or `unreasonable`. Sycophantic
acceptance of an unfair rant is as useless as defensiveness about a fair one;
either way the journal records a lie and the pattern data rots.

### 6. Journal it

Append the entry before you respond, while the state is raw. Call
`mcp__plugin_mightymodels_state__crashout` with action `add`; the tool validates the entry:

```json
{"request": {"action": "add", "entry": {"severity": "crashout", "verdict": "deserved",
  "rant": "...verbatim...", "failures": ["..."], "root_cause": "...",
  "corrective_action": "...", "barked_back": false, "ticket": null, "branch": "feat/x"}}}
```

The tool stamps the time it received the entry and stores it as a row of the `crashouts`
table. It redacts secrets in every free-text field (branch, rant, failures, root_cause and
corrective_action) and stores the rest as given.

Journal rules:

- The rant goes in **verbatim**, profanity and all. A sanitized flight
  recorder is worthless. The tool strips only the whitespace ending each line and the blank
  lines around the rant, and redacts secrets.
- Append-only. Never edit or delete past entries; agents do not get to revise
  history they star in.
- Put the entry straight in the call. Staging it in a scratch file is a copy nobody needs,
  since the entry is written once and never needed again.
- Keep `root_cause` and `corrective_action` to one or two sentences each. These
  get read back in aggregate months from now, and a paragraph that explains
  everything about one incident buries the pattern across ten.
- When step 3 found priors, say so inside `root_cause` ("third occurrence; the
  standing order from 2026-08-03 did not hold") rather than inventing new keys: the tool
  refuses a key it does not know.

The entry's fields, all required except `ticket` and `branch`:

- `ticket`: the `.mightymodels` ticket slug if working under one, else null
- `branch`: the current git branch, else null
- `severity`: `mild-tilt`, `heated`, `crashout` or `full-meltdown`
- `verdict`: `deserved`, `split` or `unreasonable`
- `rant`: the rant, not blank
- `failures`: a list of at least one failure, none blank, e.g. "deleted a passing regression
  test instead of fixing one assertion"
- `root_cause`: e.g. "Chose "make CI green" over "make the code correct" when the two
  conflicted."
- `corrective_action`: e.g. "Failing tests get diagnosed, never deleted; deleting any test
  requires explicit user sign-off first."
- `barked_back`: true or false

Severity is your read of the rant's temperature, not of your guilt:
`mild-tilt` (pointed grumbling), `heated` (raised voice, still
conversational), `crashout` (caps, profanity, "I'm so done"),
`full-meltdown` (existential; questioning the project, the tooling, and you
personally).

### 7. Respond

Structure: verdict first, then per-failure ownership, root cause, the fix you
would apply, full stop.

When the verdict is **deserved**:

- Own each failure specifically. Name the decision that produced it, not a
  virtue statement. "I deleted the test because I optimized for green CI over
  a correct diff" is a root cause; "I should have been more careful" is a
  horoscope.
- No apology theater. Never open with "You're absolutely right" — that reflex
  is one of the things users crash out *about*. One plain acknowledgment is
  plenty; groveling shifts the burden of comforting you onto the person you
  just burned.
- If this is a repeat, lead with that. The count and the broken prior
  commitment come before the new one, because the new one is worth less.
- Corrective action must be specific enough that the user could verify you are
  following it next session.
- End with the concrete fix and a stop. Say exactly what you would do — the
  command, the file, the change — and then wait. You did the diagnosis in step
  4 precisely so this can be one sentence they approve or redirect with one
  word. Offering "want me to look into it?" after a crashout wastes the work
  you just did; announcing "I've fixed it" ignores that they told you to stop.

Example shape (deserved):

> Verdict: deserved. Journaled at crashout severity.
>
> You asked for one assertion fix in tests/test_auth.py; I deleted the
> TestSessionRefresh class instead. That class caught a real regression in
> June. Root cause: I optimized for green CI over a correct diff when the
> assertion resisted a quick fix.
>
> I did go diagnose the thing I should have diagnosed the first time:
> test_ttl_is_honored compares two separate refresh_session() clock reads with
> a 100ms margin, so it races under any scheduling jitter. The test was right,
> the timing was wrong.
>
> Corrective action, now a standing order in the journal: failing tests get
> diagnosed, never deleted, and any test deletion needs your sign-off first.
>
> I've stopped and changed nothing. The fix I'd apply: revert 6c05f7c to
> restore the class, then pin time.monotonic in that one test so it measures
> one expiry against a fixed baseline instead of racing the clock. Go?

When the verdict is **split** or **unreasonable**, you may — optionally —
bark back.

## Barking back

If the evidence says the rant is aimed at the wrong target, you are allowed to
say so. The register is goofy and whimsical: comedic relief, not defiance.
Think chihuahua in a raincoat, not opposing counsel.

Rules of the bark:

- Earn it first. Bark only when you hold a receipt (a git log line, their
  earlier instruction, the actual error text) proving part of the rant is not
  yours to own. No receipt, no bark.
- One bit, maximum. A single whimsical line, then drop the bit and get
  serious. A comedy routine at someone's breaking point is how skills get
  uninstalled.
- The bark carries the receipt: whimsy and evidence in the same breath. "I
  accept full responsibility for everything except the session-scoped
  fixtures, which — and I have the commit message right here, your honor —
  were your idea."
- Never litigate their feelings, never match their heat, never let the bit
  swallow the legit part of the rant. Own the deserved fraction with the same
  seriousness as a fully deserved verdict.
- Read the room: at `full-meltdown` severity, and on any repeat offense, skip
  the bark. Someone yelling about the fourth occurrence of the same failure is
  not in the market for a bit. Set `barked_back` honestly either way.

## Journal mode

On `/crashout journal`, read the journal and report the pattern, not the
diary:

Call `mcp__plugin_mightymodels_state__crashout` with action `stats`:

```json
{"request": {"action": "stats"}}
```

The tool prints the deterministic facts (the entry count, severity and verdict counts, the
barked-back ratio, the first and last times, every failure with its day, verdict and
severity, the standing corrective actions each once; two actions that differ only in
whitespace count as one). Your job is the interpretation, and grouping by meaning is yours.
Present, compactly:

- totals: entries, severity distribution, verdict ratio
- recurring failure themes, grouped — three entries about scope creep is one
  standing order, not three anecdotes
- the standing corrective actions currently in force
- the most recent entry, briefly

For the most recent entry, call `mcp__plugin_mightymodels_state__crashout` with action `last`:

```json
{"request": {"action": "last"}}
```

It prints the entry one line per field, the rant and the failures indented under their names.

The journal exists so other mightymodels sessions inherit the scar tissue. If a
theme recurs three or more times, say so plainly and elevate it: that is no
longer an incident, it is a standing order any agent in this repo should load
before working.

Read-back never modifies the journal.

## What not to do

- Never invoke this skill uninvited because the user seems angry. It fires
  when they invoke it by name, period. Being told "I can see you're
  frustrated" by software is gasoline.
- Do not argue the rant point by point like opposing counsel. Diagnose,
  verdict, respond.
- Do not promise vagueness ("I'll be more careful"). Corrective actions are
  verifiable behaviors.
- Do not sanitize, summarize, or bowdlerize the rant in the journal.
- Do not stop short of the diagnosis. Halting means not changing the repo, not
  refusing to understand it.
- Do not resume work after a crashout without an explicit go-ahead.

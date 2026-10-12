---
name: whats-broken
description: Use when CI has a non-obvious failure, a test resists repair, or behavior contradicts expectations after repeated verification.
when_to_use: >-
  Use for "CI is red", "this won't stop failing", "why does this test keep failing", and when
  stick-the-landing or agents-assemble routes a failure here.
argument-hint: "[failing check, test or symptom]"
allowed-tools:
  - mcp__plugin_mightymodels_state__contract
  - mcp__plugin_mightymodels_state__task
---

# whats-broken

The protocol exists because of one failure mode: a plausible quick fix that skips evidence. It looks efficient, it usually patches the symptom, and each round of it pollutes the diff your reviewers later have to litigate. So the phases gate each other, and the one rule with no exceptions is that **no fix is proposed before the evidence phase completes.**

**Entry paths:** stick-the-landing routes a CI failure here when the fix isn't obvious from the log tail; agents-assemble routes a task here after both its engineer attempt and its architect recovery failed; and bare invocation ("CI is red", "this won't stop failing") works with or without an active ticket. With no ticket the hypothesis log lives at `.mightymodels/whats-broken.md`; first make sure `.mightymodels/` is excluded, since nothing under it is ever tracked: `git check-ignore -q .mightymodels || echo '.mightymodels/' >> "$(git rev-parse --git-common-dir)/info/exclude"`.

**Argument:** the failure to diagnose, given when the skill was started: "$ARGUMENTS". Empty quotes mean nothing was given, and the failure is the one the session or the routing skill named.

## Phases

**1. Reproduce.** A command that fails deterministically, run and shown. Can't make it deterministic → say so explicitly with the observed frequency ("3 of 20 runs") — a probabilistic bug investigated as a deterministic one produces confident nonsense.

**2. Evidence.** Scouts gather facts, each packet built through prompting-subagents: code-scout for the failing path, recent changes touching it (`git log`, `git blame`), what the error actually says versus what everyone assumed it says, and config and environment at the failure site; web-scout only when the cause may be documented upstream behavior (a changed default, a deprecation) at the version the lockfile pins. Gitty-up's fail report (buckets + log tails) is admissible evidence on the CI path. No fixes in this phase — not proposed, not "just noted for later". Full stop.

**3. Hypothesis — exactly one, falsifiable, on disk.** Write to `.mightymodels/<slug>/whats-broken.md`:

```markdown
# whats-broken: <slug or symptom>
attempt: <n>
reproduce: <the command and its failing output, one line>
hypothesis: I believe <X> is the cause because <evidence>. If true, <Z> will show it.
test: <the minimal check that could falsify this>
```

Current-state only — each attempt regenerates the file (prior attempts live in the summary line, not as an appended archive). One hypothesis at a time: two live hypotheses means the test that follows proves neither.

**4. Test the hypothesis, minimally.** The cheapest check that could falsify it — a log line, a one-off command, a narrowed test invocation. Not a fix. Falsified → back to phase 3 with the new evidence, attempt counter up. Confirmed → phase 5.

**5. Fix, through the normal path.** A confirmed cause is new, well-understood work, so it goes to a fresh **engineer** dispatch whose ASKED stanza includes a regression test as an acceptance criterion. With an active ticket, the regression test gets a contract id through `mcp__plugin_mightymodels_state__contract` with action `approve`, as game-plan shows (the user approves it in the dialog, as every contract command is), and is proven with `mightymodels verify run`, not by the engineer's word. The fix targets the confirmed cause: if the diff patches the symptom's location instead of the hypothesis's location, that is the quick fix wearing a lab coat; reject it.

Route to **architect** instead only when the confirmed cause needs a design decision or files outside the task's owned set: `diagnose-replan` when the fix is not yet clear, `systemic-refactor` only after the user approves the expanded envelope, started through the `task` tool on the task that is still in progress. A task the architect replans is marked `superseded`, and its revised contract is a new task. `diagnose-replan` stays allowed after the architect's one implementation attempt. Diagnosis stays here and implementation stays with them; architect never widens scope it discovered while debugging.

## The breaker

Three failed fixes → **stop.** Every failed engineer or architect dispatch from phase 5 is a strike; a re-dispatch after a strike is a new hypothesis round, not a retry. Summarize the hypothesis log and escalate to the user: "the architecture or the understanding is wrong — which do you want to attack?" A fourth patch is never the answer; by strike three the cheap explanations are exhausted and continuing spends real money relocating the problem. Delete `whats-broken.md` when the debug closes (prune-ticket removes stragglers).

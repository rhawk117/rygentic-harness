---
name: whats-broken
description: >-
  Phased debugging protocol: reproduce, gather evidence with scouts (no fixes proposed during the evidence phase), one named falsifiable hypothesis at a time written to the ticket's whats-broken.md, a minimal hypothesis test, then the fix through a normal engineer dispatch with a regression test — and a hard three-strike breaker that stops and escalates instead of attempting a fourth patch. Use when CI is red with a non-obvious cause, a test won't stop failing, behavior contradicts expectations, or scout verification keeps failing on the same task — "what's broken", "why is CI red", "debug this", "this test keeps failing and I don't know why". Not for mechanical lint/format failures (budgetron takes those) and not for open-ended investigation of non-broken behavior (lets-investigate).
---

# whats-broken

The protocol exists because of one failure mode: a plausible quick fix that skips evidence. It looks efficient, it usually patches the symptom, and each round of it pollutes the diff your reviewers later have to litigate. So the phases gate each other, and the one rule with no exceptions is that **no fix is proposed before the evidence phase completes.**

**Entry paths:** finish-assembly routes a CI failure here when the fix isn't obvious from the log tail; agents-assemble routes here after scout verification fails twice on one task; and bare invocation — "CI is red", "this won't stop failing" — works with or without an active ticket (no ticket → the hypothesis log lives at repo root and you say so).

## Phases

**1. Reproduce.** A command that fails deterministically, run and shown. Can't make it deterministic → say so explicitly with the observed frequency ("3 of 20 runs") — a probabilistic bug investigated as a deterministic one produces confident nonsense.

**2. Evidence.** Scouts gather facts: the failing path, recent changes touching it (`git log`), what the error actually says versus what everyone assumed it says, config and environment at the failure site. Gitty-up's fail report (buckets + log tails) is admissible evidence on the CI path. No fixes in this phase — not proposed, not "just noted for later". Full stop.

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

**5. Fix, through the normal path.** An engineer dispatch whose ASKED stanza includes a regression test as an acceptance criterion. The fix targets the confirmed cause — if the diff you're reviewing patches the symptom's location instead of the hypothesis's location, that is the quick fix wearing a lab coat; reject it.

## The breaker

Three failed fixes → **stop.** Summarize the hypothesis log and escalate to the user: "the architecture or the understanding is wrong — which do you want to attack?" A fourth patch is never the answer; by strike three the cheap explanations are exhausted and continuing spends real money relocating the problem. Delete `whats-broken.md` when the debug closes (prune-ticket removes stragglers).

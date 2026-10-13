# MERGE-VADER REPORT: fix/retry-queue into main

VERDICT: BLOCK
> "I find your lack of faith in the pipeline disturbing."

| | |
|---|---|
| Branch | `fix/retry-queue` @ `3e2477e` |
| Base | `main` @ `092800f` |
| Change size | 14 files, +420/-96, 5 commits |
| Review depth | full diff read ; 3 code-scout, 1 web-scout, 1 qualitylens dispatched |

## Summary

The branch rewrites the retry queue's drain loop and moves session handling into the auth package. Risk concentrates in two places: a pipeline change that drops the coverage gate, and a session check that compares secrets with a plain equality test. Those two drive the verdict. Pricing logic leaked into the store, and one plan commitment is missing.

## Findings

### Critical

#### MV-1 | sdlc | Coverage gate removed from the pipeline

- Evidence: `.github/workflows/ci.yml:41` `# - run: uv run pytest --cov-fail-under=90`
- Why it matters: the next regression merges without a failing check.
- Fix: Restore the `--cov-fail-under=90` step in the test job.
- Verify: `rg -n 'cov-fail-under' .github/workflows/ci.yml`
- Confidence: High

### High

#### MV-2 | security | Session token compared with ==

- Evidence: `src/auth/session.py:88` `if token == stored:`
- Why it matters: the comparison leaks timing, so a caller can recover the token byte by byte.
- Fix: Use `hmac.compare_digest` for the comparison.
- Verify: `uv run pytest -q tests/test_session.py`
- Confidence: High
- Signals: qualitylens shows the function changed in 6 of the last 10 commits.

### Medium

#### MV-3 | quality | Store mixes persistence and pricing

- Evidence: `src/billing/store.py:10-140` `class Store:`
- Evidence (metric): uncle-bob-metrics.json violations.functions_over_20_loc: billing/store.py:busy 38
- Why it matters: a pricing change now risks the persistence tests.
- Fix: Extract a `PriceBook` and have the store call it.
- Verify: `rg -n 'class PriceBook' src/billing`
- Confidence: Low
- Architect escalation: the split moves a public import path, which needs a design decision.

#### MV-4 | plan | Plan commitment 3 (retry cap) is not implemented

- Evidence: `src/queue/retry.py:30` `attempts = attempts + 1`
- Why it matters: a poisoned message retries forever and starves the queue.
- Fix: Stop retrying after the plan's cap of five attempts and move the message to the dead-letter list.
- Verify: `uv run pytest -q tests/test_retry.py -k cap`
- Confidence: High

### Low

#### MV-5 | docs | README still names the removed flag

- Evidence: `README.md:12` `--drain-fast`
- Why it matters: a reader follows the README to a flag that no longer exists.
- Fix: Replace `--drain-fast` with the `--batch` option.
- Verify: `rg -n -e '--drain-fast' README.md`
- Confidence: High

## Plan conformance

Commitments 1 and 2 hold. Commitment 3 is MV-4.

## Clean dimensions

Nothing else surfaced in the diff.

## Conditions

1. Resolve MV-1 and MV-2, then repeat their Verify steps.

## Not verified

Fixture reports for the other persona were not read.

## Scout log

5 dispatched: 4 VERIFIED, 1 INFERRED, 0 NEEDS-ANALYSIS, 0 UNKNOWN-BLOCKED.

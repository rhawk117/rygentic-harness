# Uncle Bob Code Quality Report — retry-queue

Mode: pure · 2026-10-04 · 42 files / 5120 LOC analyzed
(Python) · 12 read closely, 30 sampled

## Grade: C

The queue and the store import each other, so neither can change alone. The single most valuable repair is breaking that cycle behind an interface the queue owns.

## Category grades

| Category | Grade | Determining evidence |
|---|---|---|
| Names | B | consistent, a few vague helpers |
| Functions | C | `drain` is 74 lines with 6 parameters |
| Comments | B | few, accurate |
| Error Handling | B | one swallowed exception |
| Tests | B | 0.8 test ratio |
| Classes & SOLID | C | `Store` has three reasons to change |
| Components & Architecture | D | queue and store form a cycle |
| Simplicity & Duplication | B | one duplicated retry snippet |

## The numbers

LOC 5120, test ratio 0.8, 1 dependency cycle, worst function `drain` at 74 LOC.

## Findings

### Blocker

#### UB-1 | [ADP] Dependency cycle between queue and store — `src/queue/store.py:12`

- Evidence: `src/queue/store.py:12` imports `queue.worker`, which imports the store back.
- Evidence (metric): uncle-bob-metrics.json cycles: queue.store <-> queue.worker
- Why: Acyclic Dependencies Principle: a cycle makes the two components one unit of change.
- Future pressure: the dead-letter work lands in both.
- Expected churn: high, 9 commits in 30 days.
- Clean extension path: no, every change touches both modules.
- Fix: Define a `MessageStore` protocol in the queue package and make the store implement it.
- Verify: `uv run python -c "import queue.store"` with no import cycle reported by the metrics script
- Confidence: High

### High

#### UB-2 | [DIP] Domain imports the ORM session — `src/queue/domain.py:30-52`

- Evidence: `src/queue/domain.py:30` `from sqlalchemy.orm import Session`
- Evidence (convention): ruff.toml TID251 bans sqlalchemy in domain; src/queue/policy.py:3, src/queue/retry.py:5 take the session as an argument
- Why: the Dependency Rule points outward, and this import points inward.
- Future pressure: none foreseen
- Expected churn: medium
- Clean extension path: yes, pass the session in.
- Fix: Take the session as an argument instead of importing it.
- Verify: `rg -n 'sqlalchemy' src/queue/domain.py`
- Confidence: High

### Medium

#### UB-3 | [F1] Output argument in drain — `src/queue/worker.py:101`

- Evidence: `src/queue/worker.py:101` `def drain(queue, results):`
- Evidence (idiom): https://docs.python.org/3.14/tutorial/controlflow.html#defining-functions
- Why: F2 forbids output arguments; the caller cannot see that `results` is written.
- Future pressure: none foreseen
- Expected churn: low
- Clean extension path: yes
- Fix: Return the results from `drain`.
- Verify: `rg -n 'def drain' src/queue/worker.py`
- Confidence: Low
- Architect escalation: callers outside the package pass a list, which needs a decision.

### Low

#### UB-4 | [G12] Unused import left in the store — `src/queue/store.py:3`

- Evidence: `src/queue/store.py:3` `import json`
- Why: clutter.
- Future pressure: none foreseen
- Expected churn: low
- Clean extension path: yes
- Fix: Delete the import.
- Verify: `uv run ruff check src/queue/store.py`
- Confidence: High

## What holds up

Tests exist and cover the retry path.

## Repair sequence

1. Break the queue and store cycle (UB-1).

## Coverage and method

12 files read in full, 30 sampled; metrics from the script, grades judged.

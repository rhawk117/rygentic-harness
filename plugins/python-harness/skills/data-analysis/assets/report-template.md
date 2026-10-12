# TITLE: the question in one line

Data: SYNTHETIC | PUBLIC | PROVIDED. Run: DATE, SCRIPT, EXECUTION STATUS.

## Answer

Two or three sentences a decision-maker can act on: the main result with its units, n, effect size and interval, and what it changes about the decision.

## Question and observation

- Decision this informs:
- Estimand:
- One observation is:
- Population and time window:
- Denominator of each rate:

## Data

- Sources and extraction window:
- Exclusions, counts excluded, and why:
- Contract checks run (types, nulls, duplicate keys, join cardinality, time zones):

## Method

- Class (descriptive, estimation, modeling, prediction, causal, retrieval, graph, survival, change point):
- Package pairing and why it fits:
- Baseline:
- Validation design (split unit, horizon, origins, threshold selection):

## Results

| measure | value | unit | n   | interval (level, method) |
| ------- | ----- | ---- | --- | ------------------------ |
|         |       |      |     |                          |

Diagnostics: convergence, censoring counts, discordant pairs, residual checks, calibration, as applicable.

## Practical consequence

Alerts per day, cost per verified success, affected services, capacity headroom: whatever turns the number into an operational effect.

## What this does not show

Causation without a design, populations not sampled, horizons not evaluated, assumptions not checked.

## Reproduce

```bash
uv run ANALYSIS_SCRIPT.py ARGS
```

Inputs (path and digest or query with extraction bounds), parameters, seed policy, package versions.

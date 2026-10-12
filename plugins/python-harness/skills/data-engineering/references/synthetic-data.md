# Synthetic and fake data

Read before generating fixtures, demo data, stress inputs or simulation data.

## Purpose decides the generator

| purpose                        | generator                                                   | what it can establish                                  |
| ------------------------------ | ----------------------------------------------------------- | ------------------------------------------------------ |
| exact unit-test expectations   | small hand-written records                                  | a named behavior gives the expected result             |
| realistic strings and metadata | Faker                                                       | formatting and handling of plausible values            |
| model mechanics                | scikit-learn sample generators                              | behavior under controlled separation, noise, imbalance |
| statistical method checks      | explicit NumPy/SciPy data-generating process                | recovery, coverage, sensitivity under known truth      |
| pipeline contracts             | relational generation with valid keys and timestamps        | join and schema behavior                               |
| failure handling               | deliberate corruption of valid records                      | rejection, quarantine, diagnostics                     |
| performance                    | realistic shapes, skew, cardinality, string sizes, sparsity | resource behavior on those characteristics             |
| production effectiveness       | real held-out data; synthetic only as a supplement          | evidence about the actual population                   |

Faker supplies plausible values, not covariance, temporal dependence, entity behavior or referential integrity. Independent random columns rarely make a realistic analytical dataset, and schema-valid synthetic rows are not evidence a model generalizes.

## Write the process down

Record: the unit and its ID; population size, prevalence, category frequencies, entity counts; conditional relationships and latent variables; noise, tails, outliers, measurement limits; frequency, seasonality, autocorrelation, drift, event windows; the missingness mechanism; ground truth kept apart from observable columns; generator version, parameters, seed, RNG algorithm, package versions, partition policy.

Generate parents before children and sample valid foreign keys. Give join keys realistic skew; uniform keys hide hot-key failures. Very compressible repeated strings make I/O benchmarks look cheap.

## Random streams

Inject a `numpy.random.Generator` or a declared seed at the composition boundary; never call global `np.random.seed()` in reusable code. Spawn one child stream per component so changing one component (say, the missing fraction) leaves the others' draws unchanged:

```python
import numpy as np

route_stream, latency_stream, error_stream, missing_stream = map(
    np.random.default_rng, np.random.SeedSequence(42).spawn(4)
)
```

Fix the mapping from streams to components or partitions; if worker scheduling picks it, reproduction breaks. Changing chunk size or draw order changes values even with the same root seed. A seed is not a full reproducibility spec: pin the environment for exact-value checks. Statistical equivalence and byte equality are different acceptance criteria.

## Example: related request telemetry with separate truth

```python
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.special import expit


@dataclass(frozen=True, slots=True, kw_only=True)
class TrafficConfig:
    rows: int = 20_000
    seed: int = 42
    deployment_multiplier: float = 1.4
    missing_fraction: float = 0.01


def generate_requests(config: TrafficConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    route_rng, latency_rng, error_rng, missing_rng = map(
        np.random.default_rng, np.random.SeedSequence(config.seed).spawn(4)
    )
    index = np.arange(config.rows)
    route = route_rng.choice(3, size=config.rows, p=[0.55, 0.30, 0.15])
    load = 0.5 + 0.5 * np.sin(2 * np.pi * index / 2_880)
    deployed = index >= config.rows // 2
    incident = (index >= 3 * config.rows // 4) & (index < 4 * config.rows // 5)
    median_ms = (
        np.array([70.0, 180.0, 110.0])[route]
        * (1 + 0.6 * load)
        * np.where(deployed, config.deployment_multiplier, 1.0)
        * np.where(incident, 2.0, 1.0)
    )
    duration = latency_rng.lognormal(mean=np.log(median_ms), sigma=0.4)
    error_probability = expit(-5.0 + load + 0.7 * deployed + 1.2 * incident)
    failed = error_rng.binomial(1, error_probability).astype(bool)
    missing = missing_rng.random(config.rows) < config.missing_fraction
    observed = pd.DataFrame(
        {
            'request_id': index,
            'timestamp': pd.date_range('2026-01-01', periods=config.rows, freq='30s', tz='UTC'),
            'endpoint': np.array(['/login', '/orders', '/search'])[route],
            'status': np.where(failed, 500, 200),
            'duration_ms': np.where(missing, np.nan, duration),
            'release': np.where(deployed, 'new', 'old'),
        }
    )
    truth = pd.DataFrame(
        {
            'request_id': index,
            'load': load,
            'injected_incident': incident,
            'latent_median_ms': median_ms,
            'error_probability': error_probability,
            'duration_missing': missing,
        }
    )
    return observed, truth
```

What the mechanism means: one row every 30 seconds (a regular grid, not a bursty arrival process); imbalanced routes on purpose; NumPy's lognormal `mean` is the log-scale mean, so `exp(mean)` is the median, not the arithmetic mean (`E = exp(mu + sigma^2/2)`); latency and failure share load and event effects, so they correlate; missingness is independent of duration (MCAR), which real telemetry loss often is not. Validate config ranges in a separate testable function that returns the violation (rows >= 100, positive finite multiplier, missing fraction in \[0, 1)).

## Missingness and corruption

| mechanism | example                                      | consequence                         |
| --------- | -------------------------------------------- | ----------------------------------- |
| MCAR      | independent sensor dropouts                  | lost precision only                 |
| MAR       | one region's older collector loses more rows | condition on the observed factor    |
| MNAR      | the slowest requests lose their durations    | observed latency looks falsely good |

The pattern of missing values does not reveal the mechanism; simulate several when it matters. Test all-missing groups, null labels, malformed times, duplicate IDs, impossible statuses, negatives and nonfinite values as separate deliberate fixtures, not as a tiny random corruption rate that may never fire.

## Other generators

- Faker: seed the instance (`fake.seed_instance(42)`), use integer IDs for identity, use reserved domains (`example.invalid`), never assert exact generated names across upgrades. Fake names over real records do not anonymize them.
- `make_classification(weights=[0.98, 0.02], flip_y=...)`: label noise changes realized prevalence, so inspect it. Calling the generator separately for train and test does not share a target function.
- AR(1) noise via `scipy.signal.lfilter([1.0], [1.0, -phi], innovations)` with a warmup discarded; `|phi| < 1`.

## Acceptance checks

Exact structural invariants (keys, ranges, truth separation) hold exactly. Requested prevalence or missing fraction are probabilities, not exact counts; use a justified tolerance or generate exact totals. Keep several scenario seeds, chosen before seeing which method wins. Never tune a generator against held-out real data and then call the evaluation independent.

## Docs

[NumPy parallel streams](https://numpy.org/doc/stable/reference/random/parallel.html), [Faker](https://faker.readthedocs.io/en/master/), [scikit-learn generators](https://scikit-learn.org/stable/datasets/sample_generators.html), [lognormal](https://numpy.org/doc/stable/reference/random/generated/numpy.random.Generator.lognormal.html), [lfilter](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.lfilter.html)

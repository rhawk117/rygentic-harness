# Testing analytical code

Read when writing or reviewing tests for data transformations, aggregations, features, generators or publication. Follow the project's existing pytest conventions and plugins first.

## Pick tests by the failure they catch

| target                          | regression                                   | assertion                                                   | layer                  |
| ------------------------------- | -------------------------------------------- | ----------------------------------------------------------- | ---------------------- |
| missing latency                 | error denominator shrinks                    | request and error counts unchanged; latency count lower     | unit                   |
| duplicate dimension keys        | join multiplies rows                         | explicit failure, or documented dedup                       | unit                   |
| combined rates                  | mean of unequal-sized group rates            | hand-computed count-based answer                            | unit                   |
| empty input or zero denominator | undefined rate reported as 0 or NaN silently | explicit error or documented undefined value                | unit                   |
| quantile convention             | engines disagree                             | small named example with agreed interpolation               | unit                   |
| preprocessing boundary          | validation leakage                           | changing held-out rows cannot change the fitted transform   | unit                   |
| past-only features              | future leaks backward                        | changing future values leaves earlier features identical    | metamorphic            |
| group or time split             | entity or future row crosses boundary        | disjointness and ordering assertions                        | unit                   |
| generator                       | invalid keys, coupled streams                | schema, truth separation, stream independence               | unit                   |
| model convergence               | failed fit reported as reliable              | convergence status handled                                  | integration            |
| artifact serialization          | lost types, units, nulls, nonfinite JSON     | round trip with schema and value checks                     | integration            |
| publication failure             | partial bundle looks complete                | no manifest, no success event                               | integration            |
| CLI boundary                    | human text in machine output                 | artifacts and logs on their channels; no unsolicited stdout | end-to-end             |
| statistical method              | bias, poor coverage                          | designed simulation with Monte Carlo error                  | statistical validation |
| performance                     | cardinality explosion, densification         | shape invariants plus representative measurement            | benchmark              |

Coverage percentage, test count and a model score are not evidence that an analysis is correct.

## Oracles

Expected values come from hand-computed small cases, not from re-running the implementation's formula inside the test; a copied formula reproduces the same mistake. Ten errors in 100 plus nine in 900 must give 19/1000 = 0.019, not 0.055. A test is valuable only if it would fail on a plausible bug: counting non-null durations as requests must fail the denominator test; dropping `shift(1)` must fail the future-perturbation test; writing the manifest before the Parquet must fail the publication test. Check that by temporarily breaking the code.

## Properties and metamorphic relations

Useful: rates in [0, 1]; numerators and denominators reconcile with input row counts; order-insensitive summaries are permutation invariant; combining disjoint partitions equals computing on the union; no input mutation; no future influence on earlier features. Choose relations the method really preserves: duplicating every row preserves means and rates but not linearly interpolated quantiles (p95 of `[0, 10]` is 9.5; of `[0, 0, 10, 10]` it is 10). Compare cluster assignments up to label permutation; compare retrieval by relevant-item ranks, not exact scores.

## Comparisons

Exact assertions for IDs, counts, labels and schema. `pandas.testing.assert_frame_equal` or `polars.testing.assert_frame_equal` with explicit order and dtype policy. `numpy.testing.assert_allclose` or `pytest.approx` with tolerances chosen from units and conditioning, not a blanket relative tolerance. Decide NaN equality explicitly. Sort only when order is semantically irrelevant; never sort a time series to hide an ordering bug. Avoid exact fitted-coefficient snapshots across dependency upgrades unless the environment is pinned for that purpose.

## Fixtures and isolation

Arrange in fixtures scoped as narrowly as their use; no shared mutable frames across tests; `tmp_path` for artifacts. Mock only the external failure boundary (storage, network), never pandas aggregation or the estimator under test. Assert log events and fields, not timestamp text. Normalize run IDs and creation times before snapshotting artifacts. Check plotted values and axis semantics rather than pixels unless layout is the contract. Parametrize named boundary cases with `pytest.param(..., id=...)`; use Hypothesis for input spaces with explicit bounds.

## Example shape

```python
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from request_analysis import combined_error_rate


@st.composite
def partition_counts(draw: st.DrawFn) -> tuple[int, int]:
    requests = draw(st.integers(1, 10_000))
    return draw(st.integers(0, requests)), requests


class TestCombinedErrorRate:
    weighted_cases = [
        pytest.param([100, 900], [10, 9], 19 / 1_000, id='unequal-groups-weighted'),
        pytest.param([4], [0], 0.0, id='no-errors'),
    ]

    @pytest.mark.parametrize(('requests', 'errors', 'expected'), weighted_cases)
    def test_weights_groups_by_requests(
        self, requests: list[int], errors: list[int], expected: float
    ) -> None:
        counts = pd.DataFrame({'requests': requests, 'errors': errors})
        assert combined_error_rate(counts) == pytest.approx(expected)

    @given(st.lists(partition_counts(), min_size=1, max_size=30))
    def test_partition_order_does_not_matter(self, pairs: list[tuple[int, int]]) -> None:
        counts = pd.DataFrame(pairs, columns=['errors', 'requests'])
        assert combined_error_rate(counts) == pytest.approx(combined_error_rate(counts.iloc[::-1]))
```

## Statistical validation is not a unit test

A 95% interval misses about 5% of the time; asserting it always covers rejects a correct method. Run designed simulations with known truth, report coverage with Monte Carlo SE `sqrt(c(1-c)/R)`, and gate on a predeclared band. Choose sample sizes, effects, dependence, missingness and seeds before seeing results. Keep these runs out of the fast unit suite and store their results as artifacts.

## Performance tests

Keep timing out of fast unit tests. Prefer cheap structural guards that catch the real regression: no dense n x n matrix, no multiplied join rows, bounded batch size, a fixed number of fits. Use a benchmark tool with warmup and controlled threads for timing gates, and measure peak memory on representative shapes and cardinalities.

## Plugins, only for a stated purpose

pytest-mock (narrow boundary substitution), pytest-cov (coverage measured, thresholds by risk), pytest-randomly (expose order and random-state dependence; keep failing seeds), pytest-xdist (after isolation is correct), Hypothesis (bounded input generation), Testcontainers (real services when the boundary matters). Register markers you actually select on; do not silently exclude unmarked tests from CI.

## Docs

[pytest parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html), [tmp_path](https://docs.pytest.org/en/stable/how-to/tmp_path.html), [logging capture](https://docs.pytest.org/en/stable/how-to/logging.html), [Hypothesis](https://hypothesis.readthedocs.io/en/latest/), [assert_frame_equal](https://pandas.pydata.org/docs/reference/api/pandas.testing.assert_frame_equal.html), [assert_allclose](https://numpy.org/doc/stable/reference/generated/numpy.testing.assert_allclose.html)

# Tables, storage, joins, logs and rates

Read for any pandas, Polars or DuckDB work over files, joins, request logs or inventories. Contents: contracts; Parquet and Arrow; engines; the log/latency pattern; rates and percentiles; anti-patterns; streaming limits and join growth; inventory joins.

## Contract checklist

Define the key that makes one observation unique, then check:

- types, units, nullability, finite numbers, allowed ranges
- time zones, what a timestamp means, ordering, window boundaries
- duplicate keys, and whether duplicates are legitimate repeats
- unmatched inventory rows and unknown categories
- join cardinality: 1:1, m:1, 1:m, or intentionally m:m
- whether each field existed at decision time
- whether a duration is complete or censored

Pandera suits repeatable column-wise batch contracts; Pydantic suits configuration and API boundaries. Do not turn millions of rows into validation objects when column checks answer the question. `python-harness-data profile-data` gives the facts for a file or a join without loading it into pandas.

## Parquet, Arrow, PyArrow

Parquet is compressed, typed columnar storage; Arrow is the in-memory columnar format and interchange ecosystem; PyArrow is the Python binding. Compressed size on disk is not resident memory. Arrow support on both sides does not guarantee zero-copy; dtypes, nulls and layout decide.

Projection (read only needed columns) and predicate pushdown (filter at scan) cut I/O; how much depends on row-group statistics, partitions and sort order. Partition by bounded filter dimensions such as date; partitioning by a high-cardinality ID creates many tiny files and slow metadata operations. Use categoricals for repeated low-cardinality strings, not for near-unique IDs. Validate range and precision before downcasting numbers.

Materialization boundary: scan large files in DuckDB or lazy Polars, return a small result, fit or plot that. Keep four sizes apart: bytes scanned, working state, output materialized, and what stays referenced afterwards.

## Choosing the engine

| engine        | use when                                                                         | main pressure                                                  |
| ------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| pandas        | exploration, reshaping, index work, library compatibility, small reduced results | resident memory, callbacks, intermediate copies                |
| Polars (lazy) | repeatable column-expression pipelines                                           | group cardinality, non-streaming operators, final output, UDFs |
| DuckDB        | joins, aggregates, windows expressed in SQL over files and frames                | blocking operators, join output, aggregate state, spill I/O    |

Compare on the actual workload: result correctness, peak memory and the plan. One query is not a ranking.

## Request logs: per-route latency and errors

Validated input: UTC `timestamp`, normalized `route`, integer `status`, finite nonnegative `duration_ms`.

```python
from datetime import UTC, datetime

import duckdb

cutoff = datetime(2026, 10, 1, tzinfo=UTC)
with duckdb.connect() as connection:
    summary = connection.execute(
        """
        SELECT
            route,
            count(*) AS requests,
            count(duration_ms) AS latency_observations,
            sum((status >= 500)::INTEGER) AS errors,
            avg((status >= 500)::INTEGER) AS error_rate,
            quantile_cont(duration_ms, 0.95) AS p95_ms
        FROM read_parquet(?)
        WHERE timestamp >= ?
        GROUP BY route
        HAVING count(*) >= 100
        ORDER BY p95_ms DESC
        """,
        ['logs/*.parquet', cutoff],
    ).pl()
```

```python
from datetime import UTC, datetime

import polars as pl

cutoff = datetime(2026, 10, 1, tzinfo=UTC)
summary = (
    pl.scan_parquet('logs/*.parquet')
    .select('timestamp', 'route', 'status', 'duration_ms')
    .filter(pl.col('timestamp') >= cutoff)
    .group_by('route')
    .agg(
        pl.len().alias('requests'),
        pl.col('duration_ms').count().alias('latency_observations'),
        (pl.col('status') >= 500).sum().alias('errors'),
        (pl.col('status') >= 500).mean().alias('error_rate'),
        pl.col('duration_ms').quantile(0.95, interpolation='linear').alias('p95_ms'),
    )
    .filter(pl.col('requests') >= 100)
    .sort('p95_ms', descending=True)
    .collect()
)
```

Polars `quantile` defaults to `'nearest'`; `'linear'` matches DuckDB `quantile_cont`. In Polars 2 the lazy engine already defaults to streaming; streaming does not bound memory for every operator or for the final result.

Route normalization: raw paths with IDs (`/users/8812/orders`) explode group cardinality and split one route into thousands of groups. Normalize to templates (`/users/{id}/orders`) in the engine with a regex replace on ID-like segments (numeric, UUID, hex), and verify the resulting route count is small and plausible.

```python
route = (
    pl.col('path')
    .str.replace_all(r'/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b', '/{uuid}')
    .str.replace_all(r'/\d+\b', '/{id}')
    .alias('route')
)
```

Replace UUIDs before bare numbers, since a UUID can start with digits. The patterns are a starting point: inspect the most frequent resulting routes and the least frequent ones before trusting the grouping.

## Rates and percentiles

- Keep counts beside every rate. Ten errors in twenty requests is not ten in a million.
- Combine rates as summed numerators over summed denominators, never the mean of group rates.
- Never average p95s across pods, files, partitions or windows and call it a p95. Recompute from raw observations, or merge a mergeable sketch (t-digest, DDSketch, HDR histogram) and label it approximate.
- Missing durations reduce the latency sample, not the error-rate denominator.
- Report any exclusion policy; do not silently drop invalid rows from a denominator.
- Compare like with like: same service, request mix, payload and window.

## Anti-patterns and their fixes

| anti-pattern                                       | fix                                                                        |
| -------------------------------------------------- | -------------------------------------------------------------------------- |
| `pd.read_parquet(path)` then select columns        | `pd.read_parquet(path, columns=[...])`, or scan lazily                     |
| `pl.read_parquet` then `.lazy()`                   | `pl.scan_parquet`; a later lazy wrapper cannot undo the eager read         |
| `df.apply(lambda row: ..., axis=1)` for arithmetic | native column expressions                                                  |
| Polars `map_elements` where an expression exists   | native expression; keep UDFs for genuinely custom logic                    |
| `result = pd.concat([result, chunk])` in a loop    | collect chunks and concat once, or write partitions or mergeable summaries |
| grouping by a near-unique ID                       | group by the real grain; check distinct count first                        |
| `cosine_similarity(all_docs)`                      | query-to-corpus top-k; see `performance.md`                                |

Loop concatenation copies the growing prefix every iteration, roughly quadratic data movement.

## Streaming limits and join growth

A global sum needs one accumulator; a sum per service needs state per service; grouping by request ID needs state per row; list aggregation keeps the volume; global sort and exact quantiles need global work and may spill. A join must hold match state and produce its output: one key with `a` left and `b` right rows yields `a * b` rows (1,000 x 1,000 = 1,000,000 for one key). For existence questions use a semi-join (`how='semi'`, `WHERE EXISTS`) instead of materializing matches. Polars may fall back to in-memory execution for operators that do not stream; DuckDB spills many blocking operators but some aggregate states still exhaust memory. Read the plan.

## Inventory joins and remediation reports

The unit is one asset/CVE pair per scan snapshot. Deduplicate findings on the full remediation key, validate the dimension join, and refuse unmatched findings:

```python
import pandas as pd

findings = pd.read_csv('findings.csv')
assets = pd.read_csv('assets.csv')
pairs = findings.drop_duplicates(['asset_id', 'cve'])
enriched = pairs.merge(assets, on='asset_id', how='left', validate='many_to_one', indicator=True)
unmatched = enriched.loc[enriched['_merge'] != 'both', 'asset_id'].unique()
```

`validate='many_to_one'` raises `MergeError` when an inventory `asset_id` appears twice; that is a data defect to report (which asset, which rows), not something to deduplicate silently, since the two rows may disagree on owner. A non-empty `unmatched` means findings without an owner; report them rather than dropping them in an inner join. Package remediation may need `asset + package + version + path + CVE` as the key. Keep risk dimensions (known exploited, exposure, criticality, deadlines) visible instead of summing CVSS into an invented score. Never merge different snapshots as if simultaneous.

## Docs

[pandas scaling](https://pandas.pydata.org/docs/user_guide/scale.html), [pandas merge](https://pandas.pydata.org/docs/user_guide/merging.html), [Polars lazy API](https://docs.pola.rs/user-guide/concepts/lazy-api/), [Polars streaming](https://docs.pola.rs/user-guide/concepts/streaming/), [DuckDB Python](https://duckdb.org/docs/stable/clients/python/overview), [DuckDB Parquet](https://duckdb.org/docs/current/data/parquet/overview), [DuckDB tuning](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads), [PyArrow Parquet](https://arrow.apache.org/docs/python/parquet.html), [Pandera](https://pandera.readthedocs.io/en/stable/)

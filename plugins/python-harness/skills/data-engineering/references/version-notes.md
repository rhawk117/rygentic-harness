# Version notes

Read when a library call behaves unexpectedly, before relying on a default, or before upgrading. Labels: doc-verified (official docs), observed (probed in an installed environment), source (carried from the reference document, not re-checked). Snapshot 2026-10-07 on Python 3.14.6.

Probed: polars 2.0.0, duckdb 1.5.6, pyarrow 25.0.1, pandas 2.3.3, numpy 2.5.3, scipy 1.18.1, scikit-learn 1.9.1, msgspec 0.22.0.

## Polars 2.0 ([upgrade guide](https://docs.pola.rs/releases/upgrade/2/))

- doc-verified: `LazyFrame.collect()` resolves `engine='auto'` to the streaming engine; joins and unpivot may not preserve order unless `maintain_order` is set.
- doc-verified: `pl.read_csv` and `pl.read_ipc` dispatch to `scan_*().collect()` and lost `n_threads`, `batch_size`, `rechunk`.
- doc-verified: `LazyFrame.profile()` was removed; use `explain()` and external timing.
- doc-verified: `is_in()` coercion is strict; `String` to `Date`/`Datetime` casts were removed (use `str.to_date()` / `str.to_datetime()`); horizontal concat requires equal heights; `explode()` turns empty lists into zero rows.
- doc-verified: CSV schema inference reads 10 files by default; headerless column names start at `column_0`.
- observed: `Expr.quantile` defaults to `interpolation='nearest'`.
- observed: `join(..., validate='m:1')` raises `ComputeError` when the right side has duplicate keys.

## pandas

- observed: statsmodels 0.15 and lifelines 0.30 resolve pandas 2.3.x through formulaic.
- doc-verified: pandas 3.0 has Copy-on-Write only (chained assignment does nothing), the `str` dtype by default, datetime resolution inference (often `us`), zoneinfo time zones, NaN treated as NA in nullable dtypes. [whatsnew](https://pandas.pydata.org/docs/whatsnew/v3.0.0.html)
- observed: `merge(validate='many_to_one')` raises `MergeError` on duplicate right keys; `indicator=True` adds `_merge`.

## DuckDB

- observed: `connection.execute(sql, params).pl()` returns Polars; `read_parquet(?)` accepts a bound glob; `EXPLAIN ANALYZE` profiles; `approx_quantile` and `quantile_cont` exist.

## SciPy / NumPy

- doc-verified: `scipy.stats.bootstrap(rng=...)`; `random_state` is the legacy keyword and only one may be passed. Default `method='BCa'`; `batch` memory is O(batch * n).
- source: `Generator.multinomial(n, pvals, size)` draws category counts.

## msgspec

- observed: `msgspec.json.encode(float('nan'))` gives `null` with no error; decoding `NaN` into a `float` field raises `DecodeError`. Validate finiteness before encoding.
- observed: `msgspec.yaml` requires PyYAML.

## Spark 4.2 ([tuning](https://spark.apache.org/docs/latest/sql-performance-tuning.html))

- doc-verified: AQE and skew-join handling are on by default; skewed means larger than `skewedPartitionFactor` (5.0) x median and larger than `skewedPartitionThresholdInBytes` (256MB); applies to sort-merge joins.

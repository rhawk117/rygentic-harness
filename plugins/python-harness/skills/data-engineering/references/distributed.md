# Distributed and chunked computation

Read for Dask, Spark, dbt, or chunked xarray work, and for any job where one task lags the rest.

## When to distribute

Only after a well-designed single-machine approach is shown insufficient, or when independent tasks offer real parallelism. Distribution adds scheduling, serialization, network, coordination and worker memory pressure, and it does not fix a join explosion, an all-pairs output or an invalid design. Reduce early; if the reduced result fits in pandas, finish there. dbt plus a warehouse is for versioned, repeatable organizational transformations, a different concern from interactive modeling.

## Shuffles and skew

Joins, group-by on new keys, repartitioning and global sorts move data between workers. Measure shuffle bytes and per-task input size. One hot key overloads one task while others idle; adding executors does not help that task because all rows for one key land in one partition.

Diagnose: in the Spark UI stage view compare max vs median task duration and shuffle-read size; count rows per join key (`groupBy(key).count().orderBy(desc('count'))`) on both sides. Typical hot keys are sentinels: `'anonymous'`, `'unknown'`, empty string, NULL, a default tenant.

Fix, in order of preference:

1. Handle the sentinel separately. Filter it out of the join and process it on its own path (often it should not join at all: anonymous clicks have no user row), then union the results.
2. Broadcast the small side when it fits in executor memory (`broadcast(users)`), which removes the shuffle of the large side for that join.
3. Adaptive skew-join handling. In Spark 4.x `spark.sql.adaptive.enabled` and `spark.sql.adaptive.skewJoin.enabled` default to true; a partition counts as skewed only if it exceeds both `skewedPartitionFactor` (default 5.0) times the median and `skewedPartitionThresholdInBytes` (default 256MB), and it applies to sort-merge joins. Check that the plan shows the skew handling before assuming it ran; tune the thresholds if the hot partition sits below them.
4. Salting: append a random suffix `0..s-1` to the hot key on the large side and replicate the small side's matching rows `s` times; correct but more code and more data.

Also avoid: thousands of tiny partitions; a few huge ones; collecting a large distributed result to the driver; recomputing shared upstream work (cache deliberately, unpersist after); persisting everything; assuming more workers always raise throughput. Choose partition size from working memory and scheduling overhead, not a universal row count.

## Chunked arrays (xarray + Dask)

Avoid tiny chunks (too many tasks) and huge chunks (worker memory); align chunks with the access pattern and on-disk chunks; avoid repeated rechunking and repeated reads; filter and reduce before `.compute()`. Per-location time series and full-map operations want different chunk layouts, so chunking is part of the algorithm.

## Docs

[Spark SQL performance tuning](https://spark.apache.org/docs/latest/sql-performance-tuning.html), [PySpark](https://spark.apache.org/docs/latest/api/python/index.html), [Dask best practices](https://docs.dask.org/en/stable/best-practices.html), [Dask dataframe best practices](https://docs.dask.org/en/stable/dataframe-best-practices.html), [xarray and Dask](https://docs.xarray.dev/en/stable/user-guide/dask.html), [dbt](https://docs.getdbt.com/docs/introduction)

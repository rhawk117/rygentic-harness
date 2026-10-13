# Performance: growth, memory, measurement, workload-specific scaling

Read when code is slow or memory-hungry, before proposing a fix. Contents: growth table; memory arithmetic; measurement plan; bootstrap; model fitting; time series; retrieval; graphs; geospatial; charts.

## Growth by operation

Symbols: `n, m` rows (two join inputs), `p` columns, `g` groups, `B` resamples, `I` iterations, `k` clusters, `V, E` vertices and edges, `r` output rows, `nnz` sparse nonzeros, `w` window width.

| operation                            | typical growth             | pressure                                      |
| ------------------------------------ | -------------------------- | --------------------------------------------- |
| scan and filter projected columns    | ~linear in bytes scanned   | I/O, decoding, bandwidth                      |
| dense elementwise arithmetic         | O(np)                      | memory traffic, temporaries                   |
| hash aggregation                     | expected O(n), state O(g)  | high cardinality                              |
| hash join                            | expected O(n + m + r)      | build state and output                        |
| comparison sort                      | O(n log n)                 | memory, spill                                 |
| dense all-pairs comparison           | O(n^2 p)                   | quadratic work and output                     |
| gradient-based linear models         | ~O(Inp)                    | repeated passes                               |
| dense least squares                  | ~O(np^2 + p^3)             | feature width, conditioning                   |
| KMeans                               | ~O(Inkp)                   | distances                                     |
| bootstrap of a linear-scan statistic | ~O(Bn)                     | resampling and evaluation                     |
| single-source graph traversal        | O(V + E)                   | edges, representation                         |
| all-pairs graph distances            | O(V(V + E)), output O(V^2) | work and output                               |
| naive rolling window                 | O(nw)                      | rescans; some statistics update incrementally |
| naive spatial pair test              | O(nm)                      | candidates, geometry complexity               |

These are algorithmic models, not benchmarks. Solvers, sparsity and approximation change them.

## Memory arithmetic (decimal bytes, excluding indexes, copies, temporaries)

- 1,000,000 rows x 100 float64 columns = 800 MB.
- 100,000^2 float32 similarities = 40 GB; 1,000,000^2 = 4 TB.
- 1,000,000 x 768 float32 embeddings = 3.07 GB.

`python-harness-data size-check` computes these. `DataFrame.memory_usage(deep=True)` and `ndarray.nbytes` are not process memory: views can pin larger buffers and native libraries allocate outside Python's tracer. Measure peak RSS.

## Measurement plan

| stage               | record                                                |
| ------------------- | ----------------------------------------------------- |
| read                | bytes scanned, file count, throughput, cache state    |
| decode              | CPU time, resident representation                     |
| filter, group, join | rows in and out, distinct keys, plan, peak memory     |
| features            | shape, dense or sparse, nnz, expansion                |
| fit                 | per-fit time, iterations, convergence, fit count      |
| predict or search   | realistic batch and corpus sizes, latency, throughput |
| serialize or render | payload size, render time                             |
| distributed         | shuffle bytes, skew, scheduling, worker memory        |

DuckDB: `EXPLAIN` shows the plan, `EXPLAIN ANALYZE` runs and profiles it. Polars: `LazyFrame.explain()` (Polars 2 removed `LazyFrame.profile()`). Look for full scans, join order, sorts, fallbacks and aggregate state before touching settings. A benchmark records input shape, dtypes, sparsity, key cardinality, hardware, thread settings, warm or cold cache, elapsed time and peak memory; a runtime without its workload is meaningless.

## Bootstrap

Generic bootstrap is ~O(Bn); vectorized evaluation needs O(batch * n) memory, so `scipy.stats.bootstrap(batch=...)` bounds memory but not total work. BCa (the default) adds jackknife work that grows with n; switching to percentile changes the procedure, not just its speed.

Count-based bootstrap for a mean over a few categories: for independent paired binary outcomes, differences take values in `{-1, 0, +1}`. Resampling n observations is a multinomial draw over the three category counts, so:

```python
import numpy as np


def paired_difference_interval(
    old_only_wins: int, ties: int, new_only_wins: int, rng: np.random.Generator
) -> tuple[float, float]:
    counts = np.array([old_only_wins, ties, new_only_wins])
    n = int(counts.sum())
    resampled = rng.multinomial(n, counts / n, size=20_000)
    means = resampled @ np.array([-1, 0, 1]) / n
    lower, upper = np.quantile(means, [0.025, 0.975])
    return float(lower), float(upper)
```

The three counts come from one pass over the data (for example `value_counts` of `new - old`).

This is O(n + B) instead of O(Bn): counting is one pass and each resample is a fixed-size draw, so 50M rows bootstrap in seconds. It preserves the resampling distribution of the mean for independent units. It does not apply to arbitrary statistics (medians of continuous data, ratios needing the joint distribution) or to clustered designs where the cluster must be resampled. Alternatively, at this n the normal-approximation interval for a paired mean difference is accurate and essentially free.

## Model fitting

Fits = configurations x folds x repeats + final refits + calibration + nested loops; 50 x 5 = 250 fits at 6 minutes = 25 serial hours. Common waste: huge one-hot encodings of high-cardinality columns, unbounded tree depth or ensemble size, ignoring prediction cost, recomputing reusable work (without reusing learned transforms across folds), grids over mostly hopeless regions, and `n_jobs=-1` everywhere. Nested parallelism multiplies threads: 8 CV workers x 8 BLAS threads = 64 threads on 8 cores; set inner threads explicitly. `partial_fit` exists only on some estimators and pipelines. On GPUs, avoid tiny batches, repeated host-device transfers and retained graphs; synchronize when timing.

| family                        | training                               | prediction                      |
| ----------------------------- | -------------------------------------- | ------------------------------- |
| linear, gradient-based        | ~O(Inp)                                | cheap dot products              |
| random forest                 | trees, depth, candidate features       | traverse every tree             |
| gradient boosting             | sequential rounds                      | traverse the ensemble           |
| brute-force nearest neighbors | cheap                                  | compare against all stored rows |
| kernel SVM                    | between quadratic and cubic in samples | support-vector count            |

## Time series

Refitting on every growing prefix is roughly quadratic in history; refit at a cadence, use fewer origins, roll a window, or update state with fixed parameters, and say which (each changes the adaptation strategy). A seasonal period of 365 is a different problem from 12. Budget series x origins x candidate models x fit cost.

## Retrieval

Never compute `cosine_similarity(documents)` for query retrieval: the n x n output is the problem (10,000 docs = 400 MB float32, 100,000 = 40 GB, 1,000,000 = 4 TB). Do query-to-corpus top-k in chunks: for each block of queries compute similarities against the corpus (sparse TF-IDF stays sparse), keep the top k per row with `argpartition`, discard the block. That bounds memory to block x corpus but still does O(n^2) work for all-documents neighbors; for a nightly batch over 1M that can be acceptable, otherwise use an index. Embeddings cost `n x dim x bytes` before index overhead. FAISS offers exact and approximate indexes; approximate ones trade recall for memory and latency, so measure recall@k against exact search on a sample. Do not re-embed unchanged documents.

```python
import numpy as np
from scipy.sparse import csr_matrix


def rank_block(block: csr_matrix, corpus: csr_matrix, k: int) -> np.ndarray:
    scores = (block @ corpus.T).toarray()
    candidates = np.argpartition(-scores, k - 1, axis=1)[:, :k]
    descending = np.argsort(-np.take_along_axis(scores, candidates, axis=1), axis=1)
    return np.take_along_axis(candidates, descending, axis=1)


def top_k_neighbors(
    queries: csr_matrix, corpus: csr_matrix, k: int, block_rows: int = 1_024
) -> np.ndarray:
    starts = range(0, queries.shape[0], block_rows)
    return np.vstack(
        [rank_block(queries[start : start + block_rows], corpus, k) for start in starts]
    )
```

With L2-normalized TF-IDF rows (the `TfidfVectorizer` default), the dot product is cosine similarity. When queries and corpus are the same set, ask for `k + 1` and drop each row's self-match.

## Graphs

Single-source traversal is O(V + E); all-pairs distances are O(V(V + E)) with O(V^2) output; all simple paths can be exponential. Do not compute all-pairs for a single-source question, refresh centralities needlessly, attach large payloads to every node, or rebuild static graphs per query. NetworkX object overhead can dominate; rustworkx when that is the measured limit.

## Geospatial

Cost follows geometry complexity, not row count. Spatial indexes cut candidate pairs but overlapping bounding boxes still leave exact checks. Filter to the region first, use spatial joins, avoid repeated reprojection.

## Charts

Preparation, serialization, transfer, parsing and rendering all cost. Aggregate to bins, use density views, sample for point inspection while keeping extremes and incident windows. Datashader scans every observation into a canvas; it does not make input processing free.

## Docs

[pandas scaling](https://pandas.pydata.org/docs/user_guide/scale.html), [scikit-learn scaling](https://scikit-learn.org/stable/computing/scaling_strategies.html), [scikit-learn parallelism](https://scikit-learn.org/stable/computing/parallelism.html), [SciPy bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html), [NumPy multinomial](https://numpy.org/doc/stable/reference/random/generated/numpy.random.Generator.multinomial.html), [FAISS](https://faiss.ai/), [PyTorch tuning](https://docs.pytorch.org/tutorials/recipes/recipes/tuning_guide.html)

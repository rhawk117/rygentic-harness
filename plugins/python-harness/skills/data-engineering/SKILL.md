---
name: data-engineering
description: >-
  Makes data code correct first and cheap second: pins down the output, estimates sizes before
  running, checks schema and join contracts, chooses the engine, reads the query plan before
  tuning, and has results returned or published as artifacts instead of printed. Covers synthetic
  data and tests for data code. Hands back the changed code with the measurement behind every
  speed or memory claim.
when_to_use: >-
  Use when data code is slow, runs out of memory or is about to: pandas, Polars or DuckDB over
  large Parquet or CSV files, joins that multiply rows or lose matches, all-pairs similarity, slow
  bootstraps or cross-validation, Spark or Dask jobs stuck on skew or shuffles. Also use for
  choosing between pandas, Polars and DuckDB, schema and key contracts, synthetic data and
  fixtures, and tests for analytical code. Typical requests are "this job runs out of memory",
  "why did the join double my rows" and "generate fake data for this pipeline". Not for choosing a
  statistical method or deciding what results mean (data-analysis).
argument-hint: "[what data engineering task to perform]"
paths:
  - "**/*.py"
  - "**/*.pyi"
  - "**/pyproject.toml"
  - "**/*.csv"
  - "**/*.parquet"
  - "**/*.ipynb"
allowed-tools:
  - Read
  - Grep
  - Glob
  - AskUserQuestion
  - Agent
  - mcp__plugin_python-harness_python-harness__survey
  - mcp__plugin_python-harness_python-harness__collect_python_facts
  - mcp__plugin_python-harness_python-harness__map_python_calls
  - mcp__plugin_python-harness_python-harness__gate
  - mcp__plugin_python-harness_python-harness__search_python_docs
  - mcp__plugin_python-harness_python-harness__read_python_docs
  - mcp__plugin_python-harness_python-harness__plan_review_surface
  - mcp__plugin_python-harness_python-harness__check_citations
  - Bash(python-harness-data *)
---

# Data engineering

<purpose>
Make data code correct first and cheap second. In data code, the usual failure is a wrong observation model or an explosive computation hidden behind convenient syntax. Examples include an eager read of every column, a row-wise `apply`, a `concat` in a loop, an n by n similarity matrix, an unvalidated many-to-many join, a printed result instead of a returned one, or a test that re-implements the formula it checks. Fix the representation and the algorithm before reaching for another library, more threads, a GPU, or a cluster.
</purpose>

<inputs>
- The data track pairs this skill with `data-analysis`. If the work turns into deciding which statistical method answers the question, or what a result means, switch to the `data-analysis` skill for that part. This skill can also be invoked directly, by name or when the request matches the description.
- Paths below that start with `references/` or `assets/` are inside this skill's directory, `${CLAUDE_SKILL_DIR}`.
- The plugin's MCP server names each tool `mcp__plugin_python-harness_python-harness__<tool>`; the steps below use the short name `survey`. The project tools take no root argument: the project is the session's project directory (`CLAUDE_PROJECT_DIR`). If these tools are not available, tell the user to check the plugin in `/plugin` (its Errors tab) and the server in `/mcp`; the dispatches below cannot run without them.
- Before the first dispatch below, call `survey` for the project root, the Python version and the toolchain; the dispatches pass them on.
</inputs>

<workflow>
### 1. Pin down the output and the operation

Write down what the code must produce: its grain, columns and units, its size, and how often it runs. Many slow jobs compute something the question does not need, such as all pairs when top-k per query would do, every match when an existence check would do, or exact quantiles when an approximate one with a stated error would do. Changing the operation is the biggest win available. Confirm with the user before changing what is computed. Changing how it is computed needs no confirmation.

When the data size, the target environment, or which columns matter would change the approach and the request does not say, ask through `AskUserQuestion`. While waiting, keep doing work that does not depend on the answer.

### 2. Estimate size before running

Count before executing:

- rows and columns scanned
- distinct groups and their state
- rows a join produces (left matches × right matches per key)
- dense versus sparse shape
- resamples × n for a bootstrap
- configurations × folds × repeats for model fits

Run `python-harness-data size-check SUBCOMMAND ...` for the arithmetic agents get wrong by orders of magnitude:

- `pairwise --n 1000000 --dtype float32` prints the n by n output size (4 TB here)
- `dense --rows R --cols C --dtype float64`
- `sparse --rows R --cols C --nnz NNZ`
- `embeddings --n N --dim D --dtype float32`
- `join --left-matches A --right-matches B` gives the output rows for one key
- `fits --configs K --folds F [--repeats R] [--seconds-per-fit S]`

The result holds exact bytes and a decimal size. Disk size of Parquet is not resident size.

Both bundled commands share one output shape and exit codes. Every command prints one YAML document with the same five keys: `schema_version`, `command`, `arguments` (the inputs it was given, so the run can be repeated), `result`, and `caveats` (conditions that limit the result; read them before using the numbers). Key columns are always `--key`. Exit 0 means success. Exit 2 means the input breaks a contract (bad values, missing or duplicate keys), so report it and do not work around it. Exit 3 means the input could not be read (missing file, unsupported format).

### 3. Check the data contract before transforming

Run `python-harness-data profile-data profile PATH [--key COL ...]` to get schema, null counts, approximate distinct counts and key uniqueness for a Parquet or CSV file. DuckDB reads the file, so nothing is loaded into pandas. Before any join, run `python-harness-data profile-data join LEFT RIGHT --key COL [--key COL ...]`. It reports the observed cardinality (1:1, m:1, 1:m, m:m), duplicate keys on each side, unmatched keys, and the exact inner-join output row count. A join that should be many-to-one but shows duplicates on the right is a defect in the data. Stop and report it, because deduplicating silently hides a remediation or ownership question. Then encode the contract in the code: pandas `merge(validate='many_to_one', indicator=True)`, Polars `join(validate='m:1')`, plus an explicit check for unmatched keys.

Read `references/tabular-and-storage.md` for the contract checklist and the rules on rates and logs.

### 4. Choose the engine and keep work lazy

Use DuckDB for filters, joins, aggregates and windows over files. Use Polars lazy for column-expression pipelines. Use pandas for small reduced results and library compatibility. Choose by the workload, not by reputation. Push projection and filters into the scan, stay lazy until the result is small, then materialize. The details and the anti-patterns (eager reads, per-row callbacks, loop concatenation, averaged percentiles) are in `references/tabular-and-storage.md`. Before changing any setting, read the plan with DuckDB `EXPLAIN ANALYZE` or Polars `LazyFrame.explain()`.

### 5. Diagnose performance in this order

1. Confirm the required output and the mathematical operation.
2. Estimate shape, cardinality, output size and repetitions (step 2).
3. Remove unnecessary input and intermediates.
4. Replace Python callbacks with native expressions.
5. Read the plan and profile stages. Measure peak resident memory, not just time.
6. Tune batching, chunking, dtypes, ownership and parallelism, re-checking correctness each time.
7. Only then consider compiled kernels, another representation, a GPU, or distribution.

Read the reference for the workload:

| workload                                                                             | read                                |
| ------------------------------------------------------------------------------------ | ----------------------------------- |
| tables, Parquet, joins, logs, inventories, rates                                     | `references/tabular-and-storage.md` |
| arrays, broadcasting, sparse, numerical stability                                    | `references/numerical.md`           |
| growth rates, memory math, bootstrap, ML fits, time series, retrieval, graph scaling | `references/performance.md`         |
| Dask, Spark, dbt, shuffles, skew, chunked arrays                                     | `references/distributed.md`         |
| library defaults or a version-sensitive call                                         | `references/version-notes.md`       |

When a step rests on standard-library behavior for the project's Python version (`multiprocessing`, `concurrent.futures`, `array`, `statistics`, `random`), dispatch `python-harness:pep-talk` with the question and the Python version from `survey`. Treat its return as cited facts: open the cited lines before relying on them.

### 6. Return values, publish artifacts, log events

Keep three boundaries apart:

- Computation returns tables, arrays, figures and typed results. It never prints them.
- Publication writes documented artifacts to a fresh directory and writes the manifest last.
- Logging records lifecycle events to stderr.

`assets/results.py` is a small module that implements this: msgspec records for metrics and intervals, a finiteness check that returns its violation, and `publish_bundle` that writes `manifest.json` last. Copy it into the project when results must be reused, and adapt its package list. Read `references/output-contracts.md` for the rules on units, missing values and manifests.

### 7. Synthetic data and fixtures

Decide what the fake data must establish before choosing a generator. That could be exact unit expectations, a schema, a statistical method's recovery, a performance limit, or failure handling. Write the data-generating process down and use spawned `SeedSequence` streams per component. Keep the truth table separate from the observed columns, and label the data synthetic. Read `references/synthetic-data.md`.

### 8. Tests that catch the failure, not the implementation

Pick tests by the regression they would catch:

- a shrinking denominator
- an undefined rate (empty input, zero requests) reported as zero
- join multiplication
- a mean of rates
- leakage across a split or from future values
- a quantile convention changing
- an artifact losing its types
- a partial publish presented as complete

Use hand-computed oracles, never the implementation's own formula. Use metamorphic and property tests for invariants. Keep simulation checks of statistical methods separate from deterministic unit tests. Read `references/testing.md`, and follow the project's own pytest conventions where they exist.

When the project has a test suite to extend, dispatch `python-harness:test-engineer` to write the chosen tests, briefing it with the regressions above, the hand-computed oracles, the permitted test and fixture paths, and the project root and Python version from `survey`.

### 9. Review before done

Before saying done, meet every item in the gates below, including the review of the changed paths.
</workflow>

<dispatch>
Each dispatch in steps 5, 8 and 9 is one `Agent` call to one of these agents. Pass the project root and Python version from `survey` in the request; do not pass a `model`.

- agent: `python-harness:test-engineer`
- model: sonnet
- effort: high
- tools: Read, Grep, Glob, Bash, Edit, Write, `mcp__plugin_python-harness_python-harness__survey`, `mcp__plugin_python-harness_python-harness__collect_python_facts`, `mcp__plugin_python-harness_python-harness__map_python_calls`, `mcp__plugin_python-harness_python-harness__gate`, `mcp__plugin_python-harness_python-harness__search_python_docs`, `mcp__plugin_python-harness_python-harness__read_python_docs`

- agent: `python-harness:reviewer`
- model: sonnet
- effort: high
- tools: Read, Grep, Glob, Bash, `mcp__plugin_python-harness_python-harness__plan_review_surface`, `mcp__plugin_python-harness_python-harness__check_citations`, `mcp__plugin_python-harness_python-harness__survey`, `mcp__plugin_python-harness_python-harness__gate`

- agent: `python-harness:pep-talk`
- model: haiku
- tools: Read, Grep, Glob, `mcp__plugin_python-harness_python-harness__search_python_docs`, `mcp__plugin_python-harness_python-harness__read_python_docs`, `mcp__plugin_python-harness_python-harness__survey`, `mcp__plugin_python-harness_python-harness__check_citations`

If an agent type is not available, stop. The plugin's agents did not load: tell the user to check the plugin in `/plugin` (its Errors tab) or run `claude plugin validate` on it, then start a new session. Do not substitute another agent.
</dispatch>

<gates>
Step 9, before saying done:

- Every speed or memory claim comes from a measurement in this session, with shape, dtypes, cardinality, hardware and cache state recorded.
- Correctness is re-checked after every optimization: counts reconcile, and results match the slow path on a sample.
- No join can multiply rows unnoticed, and no unmatched key is dropped silently.
- Learned transforms and time boundaries are intact (no leakage introduced by caching or reuse).
- Results are returned or published, never printed. Data is labeled synthetic, public or provided.
- Anything approximate (quantiles, ANN search, sampling) is labeled approximate, and its error or recall was measured.

Dispatch `python-harness:reviewer` on the changed paths, with the task as agreed with the user as the contract, the checks this workflow requires before done as the acceptance criteria, the verification output so far, and the project root and Python version from `survey`. Open the cited lines before relying on its findings, and fix or report each one; it edits nothing.
</gates>

<output>
The changed data code, and a chat summary:

- the measurements behind every speed or memory claim, and the correctness re-checks that followed;
- the results returned or published, and how the data is labeled;
- anything approximate, with its measured error or recall;
- the tests written, and the reviewer's findings.
</output>

<handoff>
Work that turns into deciding which statistical method answers the question, or what a result means, goes to `data-analysis`. The next stage is tactical-slop-review, once code exists. Pass it the changed data code and the tests, and say which gates passed and which are open.
</handoff>

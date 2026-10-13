# Package selection

Read when choosing the tools for an analysis route. Pattern: when the data or question is X, choose Y because it provides Z. These are layers chosen by need, not a list to install. Record the demonstrated need, the baseline, the expected benefit and the new cost for anything beyond pandas/NumPy/SciPy.

## Environment

New project default: Python 3.14 with uv and a lockfile; otherwise use the project's own Python requirement.

```bash
uv init analysis-lab --python 3.14
uv add numpy pandas scipy matplotlib
uv add duckdb polars pyarrow
uv add statsmodels scikit-learn
uv run python analysis.py
```

statsmodels 0.15 and lifelines 0.30 currently resolve pandas 2.x (through formulaic), so a project using them stays on pandas 2 (observed 2026-10-07; see `version-notes.md`). Notebooks must run from a clean kernel; marimo is an option when reactive, file-based notebooks help review. The R counterpart is tidyverse plus tidymodels; choose by existing code and team, not language loyalty.

## Routing table

| condition                                                                  | choose                                                                    | why, and the usual pairing                                                       |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| manageable table needing exploratory cleaning, reshaping, index-aware work | pandas                                                                    | flexible labeled frames; pairs with seaborn, statsmodels                         |
| repeatable transformation expressible as column expressions                | Polars                                                                    | typed expressions, optimized lazy plan; pairs with Parquet                       |
| mostly filters, joins, aggregates, windows over files                      | DuckDB                                                                    | SQL directly over Parquet/CSV; return the reduced result to pandas or Polars     |
| homogeneous numeric arrays                                                 | NumPy                                                                     | vectorized arithmetic, linear algebra; pairs with SciPy                          |
| an established numerical or statistical algorithm                          | SciPy                                                                     | tested implementations instead of hand-rolled ones                               |
| interval for a mean, median or difference                                  | NumPy + SciPy                                                             | analytical or bootstrap intervals with the right independence unit               |
| two configurations ran the same tasks                                      | pandas/NumPy + SciPy                                                      | paired alignment, discordant counts, exact tests; `python-harness-data paired-compare` |
| coefficients and uncertainty for a specified relationship                  | pandas + statsmodels                                                      | GLMs, diagnostics, inferential output                                            |
| group variation with few observations per group                            | pandas + PyMC                                                             | hierarchical partial pooling, when justified                                     |
| a causal effect is asked for                                               | design first; possibly DoWhy                                              | explicit assumptions, identification, refutation checks                          |
| numeric features, continuous target, prediction                            | ridge regression baseline                                                 | regularized linear baseline first                                                |
| numeric features, categorical target                                       | logistic regression baseline                                              | compact baseline with probabilities                                              |
| mixed tabular features with nonlinearity                                   | boosted trees (sklearn HistGradientBoosting, XGBoost, LightGBM, CatBoost) | evaluate against the linear baseline                                             |
| categorical-heavy table                                                    | CatBoost as a candidate                                                   | avoids reflexive huge one-hot expansion                                          |
| sparse text predicting a label                                             | TF-IDF + linear classifier                                                | sparse supervised baseline                                                       |
| similar incidents share distinctive terms                                  | TF-IDF + cosine                                                           | cheap lexical retrieval                                                          |
| relevant text uses different wording                                       | Sentence Transformers                                                     | semantic embeddings, evaluated against lexical                                   |
| exact embedding scan misses the latency budget                             | FAISS                                                                     | exact or approximate index with measured recall                                  |
| unlabeled records need unusualness scores                                  | Isolation Forest or another outlier method                                | unusual is not malicious or actionable                                           |
| trend, seasonality, future values                                          | pandas + statsmodels                                                      | time indexing, SARIMAX and friends                                               |
| a persistent regime shift                                                  | ruptures                                                                  | change-point detection                                                           |
| periodic components in a sampled signal                                    | SciPy signal (Welch PSD)                                                  | spectral estimation                                                              |
| durations where some cases are still open                                  | pandas + lifelines                                                        | censoring-aware survival                                                         |
| relationships and reachability                                             | NetworkX                                                                  | graph algorithms; rustworkx if object overhead is the measured limit             |
| coordinates, polygons, spatial joins, distances                            | GeoPandas                                                                 | geometry and coordinate reference systems                                        |
| named array dimensions                                                     | xarray + NumPy                                                            | named coordinates; Dask when partitioning is justified                           |
| controlled static figures for a report                                     | Matplotlib + seaborn                                                      | explicit plotting, statistical graphics                                          |
| exploration needing hover and zoom                                         | Plotly                                                                    | interactive figures                                                              |
| linked views, declarative encodings                                        | Altair                                                                    | declarative specification                                                        |
| more points than display pixels                                            | Datashader                                                                | aggregate to canvas resolution                                                   |
| many experiment runs to compare                                            | MLflow                                                                    | parameters, metrics, artifacts                                                   |
| a validated model needs a search                                           | Optuna                                                                    | searches a defensible validation objective only                                  |

Avoid blanket engine rankings. pandas vs Polars vs DuckDB is decided by the workload, correctness of the result, memory and the plan; that comparison belongs to the `data-engineering` skill.

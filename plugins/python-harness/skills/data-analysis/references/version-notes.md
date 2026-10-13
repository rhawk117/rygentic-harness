# Version notes

Read when a library call behaves unexpectedly or before relying on a default. Each line is labeled: doc-verified (official docs), observed (probed in an installed environment), or source (carried from the reference document, not re-checked). Snapshot 2026-10-07 on Python 3.14.6.

Probed versions: pandas 2.3.3, numpy 2.5.3, scipy 1.18.1, scikit-learn 1.9.1, statsmodels 0.15.0, lifelines 0.30.3, networkx 3.7, polars 2.0.0, duckdb 1.5.6, msgspec 0.22.0.

- observed: statsmodels 0.15 and lifelines 0.30 depend on formulaic, which resolves pandas 2.3.x; a project using them is not on pandas 3 yet.
- doc-verified: pandas 3.0 makes Copy-on-Write the only mode (chained assignment silently does nothing), infers strings as the `str` dtype, and infers datetime resolution (often `us`, not `ns`; integer conversion differs by 1000x). Code must work on both 2.x and 3.x. [whatsnew 3.0](https://pandas.pydata.org/docs/whatsnew/v3.0.0.html)
- doc-verified: `scipy.stats.bootstrap` takes `rng=` (Generator); `random_state=` is the legacy name, and only one may be given. Default `method='BCa'`; `batch` bounds memory at O(batch * n); `paired=True` resamples shared indices across samples.
- observed: `scipy.stats.binomtest(k, n, p=0.5)` is the exact McNemar test on discordant pairs.
- observed: Polars `Expr.quantile` defaults to `interpolation='nearest'`; pass `'linear'` to match DuckDB `quantile_cont` and NumPy's default.
- doc-verified: Polars 2.0 lazy queries run on the streaming engine by default; joins and unpivot may not preserve row order without `maintain_order`. [upgrade guide](https://docs.pola.rs/releases/upgrade/2/)
- observed: scikit-learn 1.9 provides `GroupKFold(shuffle=)`, `StratifiedGroupKFold`, `TimeSeriesSplit(gap=)`; `cross_validate(..., groups=)` routes groups to the splitter.
- observed: `KaplanMeierFitter.fit(durations, event_observed=...)`; `median_survival_time_` can be `inf` when fewer than half the subjects have the event.
- source: DoWhy refutation checks cannot prove all confounders are measured.

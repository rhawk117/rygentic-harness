# Time series: forecasts, anomalies, change points, signals

Read when observations are ordered in time and the question is about the future, unusual points, shifts, or periodicity.

## Pick the question; they need different methods

| question                                           | route                                                                          |
| -------------------------------------------------- | ------------------------------------------------------------------------------ |
| what are the trend and seasonal patterns           | decomposition and plots (pandas + statsmodels)                                 |
| what will future values be                         | forecast model plus chronological evaluation against a seasonal-naive baseline |
| is one observation unusual given expected behavior | residual thresholds or anomaly scores                                          |
| when did the process shift persistently            | change-point detection (ruptures)                                              |
| is there periodic behavior at some frequency       | spectral estimation (`scipy.signal.welch`)                                     |

A single spike and a deploy that raises every later value are different phenomena; do not answer one with the other's method.

## Forecast workflow

1. Put the series on a regular index (`resample('MS')` for months). Missing periods stay missing: an outage is not zero traffic. State-space models such as SARIMAX accept NaN observations; otherwise impute using only past values within each training window.
2. Hold out the most recent horizon chronologically; never shuffle.
3. Baseline: seasonal naive, the value from the same period one season ago.
4. Evaluate at the deployment horizon (for example a 3-month fixed-origin forecast), from several historical origins, on the same eligible observations for every method.
5. Check convergence; report forecast intervals as model-based and check empirical coverage across origins.

```python
import pandas as pd
import statsmodels.api as sm

monthly = sm.datasets.co2.load_pandas().data['co2'].resample('MS').mean()
train, test = monthly.iloc[:-12], monthly.iloc[-12:]
fitted = sm.tsa.SARIMAX(train, order=(1, 1, 1), seasonal_order=(0, 1, 1, 12)).fit(disp=False)
converged = bool(fitted.mle_retvals['converged'])
forecast = fitted.get_forecast(steps=len(test))
prediction = forecast.predicted_mean
seasonal_naive = pd.Series(train.iloc[-12:].to_numpy(), index=test.index)
eligible = test.notna() & prediction.notna() & seasonal_naive.notna()
model_mae = float((test[eligible] - prediction[eligible]).abs().mean())
baseline_mae = float((test[eligible] - seasonal_naive[eligible]).abs().mean())
```

On this public dataset the source document observed MAE about 0.28 ppm vs 1.49 for the seasonal baseline on the last year; one origin on one series is not a model ranking.

Rolling-origin evaluation: loop over origins, fit on data up to each origin, forecast the horizon, collect errors per origin and per horizon step. A fixed-origin multi-step forecast and an updating one-step forecast answer different questions; match deployment. Refitting on every prefix is roughly quadratic in history length; refit at a justified cadence, use fewer origins, or update state with fixed parameters, and say which you chose.

## Correctness mistakes

- Shuffling when the question is the future.
- Filling gaps with values from after the split (interpolation across the boundary, centered rolling means).
- Treating missing intervals as zero, or mixing sampling intervals.
- Ignoring trend, seasonality, calendar effects or a changed process.
- Evaluating one-step-ahead when deployment needs a long fixed horizon.
- Reporting one favorable origin.
- Confusing an isolated outlier with a regime change.

## Past-only features

A feature for time `t` may only use data before `t`: `shift(1)` before `rolling(window)`, applied per series on a validated regular grid. A row count of 24 is not 24 hours on irregular data. Test it metamorphically: changing future values must not change earlier features.

## Docs

[SARIMAX](https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html), [forecasting workflow](https://www.statsmodels.org/stable/examples/notebooks/generated/statespace_forecasting.html), [SARIMAX FAQ](https://www.statsmodels.org/stable/examples/notebooks/generated/statespace_sarimax_faq.html), [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html), [ruptures](https://centre-borelli.github.io/ruptures-docs/), [Welch](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html)

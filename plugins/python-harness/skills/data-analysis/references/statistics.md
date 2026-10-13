# Statistics: intervals, paired comparisons, rates, models, causality, survival

Read when the question is "how uncertain", "is it different", "what is associated with", "did it cause", or "how long until". Contents: method by observation structure; paired binary outcomes; evaluation metrics to keep separate; independence; rates and GLMs; causal claims; Bayesian models; survival; formulas.

## Match the method to the observation structure

| question                                        | start with                                                      | pairing                        |
| ----------------------------------------------- | --------------------------------------------------------------- | ------------------------------ |
| how uncertain is a statistic                    | analytical or bootstrap interval with the right resampling unit | NumPy + SciPy                  |
| did two configurations differ on the same tasks | paired differences, exact McNemar on discordant pairs           | `python-harness-data paired-compare` |
| which factors go with the outcome               | regression/GLM with diagnostics                                 | pandas + statsmodels           |
| how does variation differ across groups         | hierarchical model when justified                               | pandas + PyMC                  |
| did an intervention cause an effect             | experiment or identification strategy                           | design first, possibly DoWhy   |
| how long until resolution, some still open      | survival analysis                                               | pandas + lifelines             |

Report effect size and practical importance. A significant result can be operationally negligible; a large observed difference can be too uncertain to act on.

## Paired binary outcomes (agent A vs agent B on the same tasks)

Each row is one task run under both configurations; 1 means independently verified success, not the agent's claim. Pairing is the information: compute per-task differences first, or count discordant pairs. A two-independent-proportion test throws the pairing away.

- New-only wins `w` and old-only wins `l` are the discordant pairs. Exact McNemar conditions on `m = w + l`: under the null `W ~ Binomial(m, 0.5)`, so `scipy.stats.binomtest(w, m, 0.5)`.
- The mean of differences `d_i = new_i - old_i` in `{-1, 0, +1}` is the rate difference. Its percentile bootstrap can resample category counts from a multinomial instead of rebuilding arrays; `python-harness-data paired-compare` does this.
- Example from the source document (illustrative data): 6/12 vs 9/12, +25 percentage points, interval roughly -8 to +58 points, 4 new-only wins vs 1 old-only, exact p = 0.375. Twelve tasks are weak evidence. Never write "proven better"; say the interval includes zero and how many more paired tasks would narrow it.
- The percentile interval illustrates resampling; at small n prefer reporting the exact test and per-arm Wilson intervals alongside it.

Run: `python-harness-data paired-compare results.csv --old old_pass --new new_pass --key task_id`

## Evaluation metrics to keep separate

| metric                           | meaning                                                                                          |
| -------------------------------- | ------------------------------------------------------------------------------------------------ |
| verified success rate            | completion that passes external checks                                                           |
| false completion rate            | claimed done but failed checks; state the denominator                                            |
| cost per attempted task          | spend across all attempts                                                                        |
| total cost / verified successes  | cost of a success including failures; undefined at zero successes, so say so instead of dividing |
| wall-clock duration              | user-visible time                                                                                |
| tool failure rate, recovery rate | reliability and recovery after a defined failure                                                 |
| results by task category         | where it improved or regressed                                                                   |

Fewer tool calls is not a quality result on its own; it can mean efficiency or skipped verification.

## Independence and repeated measures

Twenty attempts on one task are not twenty independent tasks. Resample the unit the design randomized or sampled (task, repository, customer, time block). Clustered, grouped or block methods apply when outcomes cluster. Fix the evaluation protocol before looking; stopping as soon as results look good needs a sequential design.

## Rates, counts and GLMs

Combine rates from summed numerators and denominators: `r = sum(e_g) / sum(n_g)`. Ten errors in 100 and nine in 900 is 19/1000 = 1.9%; the mean of the two rates, 5.5%, answers a different question. A latency mean uses the count of observed measurements, not requests with missing durations.

Errors per service-day with traffic as exposure, `deployed` as the term of interest:

```python
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

service_days = pd.read_csv('service_day.csv')
model = smf.glm(
    'errors ~ deployed + C(service) + C(day_of_week)',
    data=service_days,
    family=sm.families.Poisson(),
    offset=np.log(service_days['requests']),
    missing='raise',
).fit(cov_type='HC0')
rate_ratio = float(np.exp(model.params['deployed']))
rate_ratio_interval = np.exp(model.conf_int().loc['deployed'])
```

- The offset fixes log traffic's coefficient at one, so the coefficient is a rate effect. A rate ratio of 1.20 is a 20% higher rate conditional on the included terms, not proof the deploy caused it.
- Failed requests out of known requests are binomial trials: `sm.families.Binomial()` with `var_weights=requests` on the failure proportion, or `freq_weights` on expanded success/failure rows, gives an odds ratio.
- Overdispersion (variance far above the mean) points to negative binomial; parameterizations differ, so check the API.
- `HC0` handles heteroskedasticity, not serial or cluster dependence; service-day panels may need cluster-robust covariance by service or a different structure.
- Check rank, convergence, residuals and that every level of the term has data on both sides. If deploys always happen on one weekday, `deployed` is collinear with `C(day_of_week)`: the fit fails with a singular matrix or the effect is unidentified. That is a design limit to report, not a bug to suppress.

Choose statsmodels when coefficients and uncertainty are the goal; scikit-learn when out-of-sample prediction is.

## Causal claims

Start from an experiment or explicit assumptions (a DAG, an identification strategy such as difference-in-differences with a comparison group, an instrument, a discontinuity). DoWhy can state a model, identify, estimate and run refutation checks; no check proves all confounders were measured. Adjusted observational association, feature importance and prediction scores are not causal effects. When the user asks "did X cause Y" without a design, report the association, name plausible confounders (traffic mix, concurrent changes, day-of-week, incident timing), and say what design would answer it.

## Bayesian and hierarchical models

Use PyMC when an explicit probability model, posterior uncertainty or partial pooling across groups with few observations justifies it. Runtime depends on likelihood cost, parameter count, warmup, draws, chains and posterior geometry. Divergences, poor mixing and low effective sample size are validity problems, not just speed problems.

## Survival: time to resolution with open cases

A resolved incident is an event at its duration; an open incident is right-censored at its age at the observation cutoff. Dropping open incidents biases toward fast resolutions; closing them at their current age is also wrong.

```python
import pandas as pd
from lifelines import KaplanMeierFitter

incidents = pd.read_csv('incidents.csv', parse_dates=['opened_at', 'resolved_at'])
cutoff = pd.Timestamp('2026-10-01T00:00:00')
end = incidents['resolved_at'].fillna(cutoff)
duration_hours = (end - incidents['opened_at']).dt.total_seconds() / 3600
resolved = incidents['resolved_at'].notna()
fitter = KaplanMeierFitter().fit(duration_hours, event_observed=resolved)
median_hours = fitter.median_survival_time_
```

Report the median (it can be infinite if fewer than half resolved), the number of events and the number censored. Check that censoring is plausibly unrelated to resolution time (for example, a recent spike of hard incidents violates it). Use the same time zone for `opened_at`, `resolved_at` and the cutoff.

## Formulas worth getting exactly right

- Sample variance needs n >= 2; `SE = s / sqrt(n)` assumes independence. With positive within-group covariance, the true variance of the mean is larger; more correlated rows are not more independent units.
- Absolute change 0.50 -> 0.75 is 0.25 (25 percentage points); relative change is 50%. Relative change from a zero baseline is undefined.
- Wilson interval for `s` successes in `n`: with `p = s/n` and normal quantile `z`, center `c = (p + z^2/(2n)) / (1 + z^2/n)`, half-width `h = z * sqrt(p(1-p)/n + z^2/(4n^2)) / (1 + z^2/n)`; clip to [0, 1]. It gives a nonzero upper bound at zero successes (0/10 gives about [0, 0.278]). Assumes independent trials.
- Poisson log link with exposure `N_i`: `log mu_i = log N_i + x_i' beta`; `exp(beta_j)` is the rate ratio. Logit: `p = 1 / (1 + exp(-x' beta))`; use `scipy.special.expit`, not a hand expansion that overflows.
- Lognormal: `median = exp(mu)`, `mean = exp(mu + sigma^2 / 2)`; NumPy's `lognormal(mean=...)` takes the log-scale mean.
- A p-value is a tail probability under a stated model, not the probability the hypothesis is true.
- Coverage of an interval method is checked by simulation: over `R` repetitions, `coverage = mean(covered)` with Monte Carlo SE `sqrt(c(1-c)/R)` (about 0.0069 at 0.95 and 1,000 reps). Do not require every simulated interval to contain the truth.

## Docs

[SciPy bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html), [SciPy binomtest](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html), [statsmodels GLM](https://www.statsmodels.org/stable/glm.html), [statsmodels proportion intervals](https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.proportion_confint.html), [PyMC divergences](https://www.pymc.io/projects/examples/en/latest/diagnostics_and_criticism/Diagnosing_biased_Inference_with_Divergences.html), [DoWhy](https://www.pywhy.org/dowhy/v0.13/user_guide/causal_tasks/estimating_causal_effects/index.html), [lifelines](https://lifelines.readthedocs.io/en/latest/Quickstart.html)

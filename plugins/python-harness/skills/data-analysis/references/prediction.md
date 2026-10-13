# Prediction: classifiers, regressors, anomaly scores, thresholds

Read when building or evaluating a model that scores new observations. Contents: baselines; pipelines and leakage; split by deployment; rare events and thresholds; inspection; fit-count budgeting.

## Baseline first

| problem                                | baseline or first candidate                                                        |
| -------------------------------------- | ---------------------------------------------------------------------------------- |
| continuous target, numeric features    | `DummyRegressor`, then ridge regression                                            |
| categorical target                     | `DummyClassifier(strategy='most_frequent')` or `'prior'`, then logistic regression |
| nonlinear mixed tabular                | gradient-boosted trees against the linear baseline                                 |
| categorical-heavy table                | CatBoost as a candidate                                                            |
| sparse text labels                     | TF-IDF + linear model                                                              |
| unlabeled unusual records              | Isolation Forest or another outlier method                                         |
| images, audio, learned representations | PyTorch with a suitable pretrained model                                           |

Boosted trees and neural nets are candidates to evaluate, not automatic improvements. Anomalous is not the same as malicious, defective or actionable.

## Pipelines keep learned transforms inside the fold

Imputation, scaling, encoding and feature selection learn from data. Fitting them on the full table before validation leaks the test fold into training.

```python
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

numeric = make_pipeline(SimpleImputer(strategy='median'), StandardScaler())
categorical = make_pipeline(
    SimpleImputer(strategy='most_frequent'),
    OneHotEncoder(handle_unknown='ignore'),
)
preprocess = ColumnTransformer(
    [
        ('numeric', numeric, ['request_count', 'error_rate', 'latency_ms']),
        ('categorical', categorical, ['service', 'region']),
    ]
)
model = make_pipeline(preprocess, LogisticRegression(max_iter=2_000))
```

Every feature must exist at prediction time. Drop columns written after the outcome (analyst notes, resolution codes, labels derived from the target). `handle_unknown='ignore'` avoids a crash on new categories; it does not make the model behave under category drift.

## Choose the split from the deployment, before the model

| deployment                                            | validation                                                                              |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------- |
| new independent observations from the same population | random split, stratified for imbalance                                                  |
| future observations                                   | chronological split (`TimeSeriesSplit`, or custom time boundaries for irregular events) |
| new hosts, repositories, customers, organizations     | group split (`GroupKFold`, `StratifiedGroupKFold`, `GroupShuffleSplit`) with `groups=`  |
| future observations from unseen groups                | both time and group boundaries                                                          |

Near-identical rows from one host crossing a boundary inflate scores for the unseen-host question. Assert disjointness: `set(train_hosts).isdisjoint(test_hosts)`. Never use the final test set to choose model, threshold, preprocessing or hyperparameters.

```python
from sklearn.model_selection import StratifiedGroupKFold, cross_validate

folds = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_validate(
    model,
    features,
    labels,
    groups=host_ids,
    cv=folds,
    scoring={'average_precision': 'average_precision', 'recall': 'recall'},
)
```

## Rare events: score the operating condition, not accuracy

At 0.1% prevalence, "always benign" is 99.9% accurate. Report recall, precision, average precision (PR-AUC), alerts per day, recall at the alert budget, calibration and stability over time, with prevalence and the evaluation population stated.

Expected load at prevalence `pi`, recall `t`, false positive rate `f`, `N` events: alerts `= N(pi*t + (1-pi)*f)`, precision `= pi*t / (pi*t + (1-pi)*f)`. One million events at 0.1% prevalence, 90% recall, 1% FPR gives 900 true and 9,990 false alerts: about 8% precision. Compute this with `python-harness-data alert-budget` whenever a detector is evaluated.

Thresholds: choose on validation data to maximize recall subject to the alert budget or a precision floor (`precision_recall_curve`), then evaluate that fixed threshold once on held-out test data. Precision depends on prevalence; it will not transfer to a population with a different base rate.

Formulas: precision `TP/(TP+FP)`, recall `TP/(TP+FN)`, F1 `2TP/(2TP+FP+FN)`, FPR `FP/(FP+TN)`. Document zero-denominator behavior rather than trusting a library's zero-division fallback. Macro F1 averages per-class F1; it is not F1 on pooled counts. Brier and log loss need valid probabilities; ranking quality, calibration and threshold quality are three separate properties. MAE and RMSE keep target units (RMSE weights large errors); MAPE breaks near zero.

## Inspection

Start with held-out performance and permutation importance on held-out data; SHAP explains model outputs. Neither is causal importance, and correlated features share or swap credit. Use MLflow when many runs need tracking; use Optuna only after the validation objective is defensible, since tuning an invalid split optimizes the invalidity.

## Budget the fits before running

Fits = configurations x folds x repeats, plus refits, calibration and nested procedures. Fifty configurations x five folds = 250 fits; at six minutes each that is 25 serial hours. Uncontrolled nested parallelism (eight CV workers each with eight BLAS threads on eight cores) oversubscribes. Performance diagnosis and scaling belong to the `data-engineering` skill.

## Docs

[scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html), [cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html), [precision_recall_curve](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.precision_recall_curve.html), [permutation importance](https://scikit-learn.org/stable/modules/generated/sklearn.inspection.permutation_importance.html), [outlier detection](https://scikit-learn.org/stable/modules/outlier_detection.html)

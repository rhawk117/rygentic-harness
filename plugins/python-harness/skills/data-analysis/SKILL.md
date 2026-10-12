---
name: data-analysis
description: 'Answer a question from data with a defensible, uncertainty-aware result. Use when the user asks what the data says or wants a decision backed by numbers: compare two agents, models, configs or releases (A/B, paired runs, "is B significantly better"), estimate a rate or difference with an interval, explain an error or latency change after a deploy, build or evaluate a classifier or anomaly detector, forecast a series, measure time to resolve with open cases, rank similar records, find blast radius or reachability in a dependency graph, measure spatial distance, or write up an analysis report. Fixes the question, observation grain, denominator and baseline before choosing a method, keeps validation leakage-safe, reports effect size with uncertainty, and says what the evidence does not prove. Not for making data code faster or fit in memory, pipeline plumbing, schema contracts, fixtures or tests for data code: use data-engineering.'
argument-hint: "[question to answer from data]"
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
  - mcp__plugin_python-harness_python-harness__plan_review_surface
  - mcp__plugin_python-harness_python-harness__check_citations
  - mcp__plugin_python-harness_python-harness__gate
  - mcp__plugin_python-harness_python-harness__search_python_docs
  - mcp__plugin_python-harness_python-harness__read_python_docs
  - Bash(python-harness-data *)
---

# Data analysis

<purpose>
Work as an analyst who must defend the answer and an engineer who must make it rerunnable. The failure this skill exists to prevent is choosing a model or library before the question is fixed, then overclaiming: a "proven gain" from twelve tasks, an averaged p95, a cross-validation score that leaked, open incidents dropped from a resolution time, an association reported as a cause. Every step below is there because skipping it produces one of those.
</purpose>

<inputs>
- The data track pairs this skill with `data-engineering`. If the work turns into making code faster, fitting it in memory, validating schemas, generating fixtures or writing tests, switch to the `data-engineering` skill for that part. This skill can also be invoked directly, by name or when the request matches the description.
- Paths below that start with `references/` or `assets/` are inside this skill's directory, `${CLAUDE_SKILL_DIR}`.
- The plugin's MCP server names each tool `mcp__plugin_python-harness_python-harness__<tool>`; the steps below use the short name `survey`. The project tools take no root argument: the project is the session's project directory (`CLAUDE_PROJECT_DIR`). If these tools are not available, tell the user to check the plugin in `/plugin` (its Errors tab) and the server in `/mcp`; the dispatches below cannot run without them.
- Before the first dispatch below, call `survey` for the project root, the Python version and the toolchain; the dispatches pass them on.
</inputs>

<workflow>
### 1. Fix the question before touching a method

Restate the request as a decision and an estimand. "Analyze the logs" becomes "which routes' p95 latency rose after Tuesday's deploy, by how much, with what uncertainty". Then classify it, because the class decides what counts as evidence:

| intent                           | class                | starting point                                              |
| -------------------------------- | -------------------- | ----------------------------------------------------------- |
| what happened, where, how often  | descriptive          | query, distributions, sorted counts                         |
| how uncertain is a difference    | estimation           | effect size plus interval, paired when the units are shared |
| which factors go with an outcome | statistical modeling | regression or GLM with diagnostics                          |
| what happens for new cases       | prediction           | baseline, leakage-safe pipeline, deployment-shaped split    |
| did X cause Y                    | causal               | experiment or an explicit identification strategy           |
| which records are similar        | retrieval            | lexical baseline, relevance judgments                       |
| what can reach or affect what    | graph                | explicit edge meaning, targeted traversal                   |
| how long until an event          | survival             | durations, event flags, censoring                           |
| when did behavior shift          | change point         | method for sustained shifts, not spikes                     |

Success in one class is not evidence in another: a strong prediction score does not show a feature causes the outcome, and a small p-value is not the probability the hypothesis is true.

### 2. Define one observation and its denominator

Write down the unit (a request, a task pair, an asset/CVE pair, a service-day, an incident, an edge), the population, the time window, units of measure, and the denominator of every rate. Then check what was knowable at decision time: any field written after the outcome (a triage note, a resolution code) is leakage for prediction.

When the target, grain, or deployment population is missing and the answer would change the method, ask the user through `AskUserQuestion`. While waiting, keep doing work that does not depend on the answer, such as loading, profiling, and checking types, nulls, duplicates and time coverage. Do not guess silently.

### 3. Look before modeling

Get counts, missingness, distributions, group sizes and the time trend. Check join cardinality and duplicate keys before any join, because a duplicated dimension row silently multiplies findings. When the data is large or the checks need code, the `data-engineering` skill's `python-harness-data profile-data` command does this without loading everything.

### 4. Set the baseline

Pick the thing the new method must beat and keep it in every comparison: majority class (`DummyClassifier`), seasonal naive (same month last year), the current alert rule, TF-IDF retrieval, the existing configuration. A result without a baseline cannot tell the user whether the method added anything.

### 5. Choose the method and package pairing

Use the routing table in `references/package-selection.md`. State why the pairing fits ("DuckDB for the reduction, statsmodels for coefficients and intervals"). A new package is not a quality improvement by itself. Name the need it meets and the cost it adds.

Read the reference for the class before writing code:

| class                                                                         | read                                    |
| ----------------------------------------------------------------------------- | --------------------------------------- |
| intervals, paired comparisons, rates, GLMs, causal claims, Bayesian, survival | `references/statistics.md`              |
| classifiers, regressors, anomaly scoring, thresholds, model inspection        | `references/prediction.md`              |
| forecasts, seasonality, anomalies vs change points, backtests                 | `references/time-series.md`             |
| text similarity, dependency graphs, coordinates, named-dimension arrays       | `references/retrieval-graph-spatial.md` |
| any chart                                                                     | `references/visualization.md`           |
| a library call behaving unexpectedly, or before relying on a default          | `references/version-notes.md`           |

When a step rests on standard-library behavior for the project's Python version (`statistics`, `random`, `decimal`, `zoneinfo`, `datetime`), dispatch `python-harness:pep-talk` with the question and the Python version from `survey`. Treat its return as cited facts: open the cited lines before relying on them.

### 6. Run the calculation the agent gets wrong by hand

Two bundled commands compute what is easy to get subtly wrong. Run them as `python-harness-data <subcommand>`; the launcher brings the dependencies. Every command prints one YAML document with the same five keys: `schema_version`, `command`, `arguments` (the inputs it was given, so the run can be repeated), `result`, and `caveats` (conditions that limit the result; read them before using the numbers). Key columns are always `--key`. Exit 0 means success. Exit 2 means the input breaks a contract (bad values, missing or duplicate keys), so report it and do not work around it. Exit 3 means the input could not be read (missing file, unsupported format).

- Two configurations on the same tasks with pass/fail outcomes:
  `python-harness-data paired-compare RESULTS.csv --old OLD_COL --new NEW_COL [--key TASK_COL] [--level 0.95] [--seed 42]`
  It returns the success rate per arm with Wilson intervals, the paired difference with a count-based bootstrap interval, discordant pair counts, and the exact McNemar p-value. Use it instead of a two-proportion test, which ignores the pairing.
- Detection or classification rates turned into operational load:
  `python-harness-data alert-budget --events N --prevalence P --recall R --fpr F [--budget ALERTS] [--cost-fn C --cost-fp C]`
  It returns expected true and false alerts, precision at that prevalence, and cost per event. It also says whether the alert count fits the review budget. Run it whenever a classifier's quality is reported as accuracy on a rare class.

### 7. Validate the way it will be used

Split along the deployment boundary: by time for future data, by group for unseen hosts, repositories or customers, by both when both apply. Fit every learned transform (scaling, imputation, encoding, feature selection) inside the training fold through a pipeline. Pick thresholds on validation data and evaluate the fixed choice once on untouched test data. Evaluate forecasts at the real horizon from several origins. The details are in the class references.

### 8. Report effect, uncertainty, and consequence

Fill `assets/report-template.md`. It holds these items, and each one exists because readers act on what is missing:

1. Question, observation grain, population.
2. Sources, time coverage, exclusions and why.
3. Method and package pairing, and why it fits.
4. Baseline and evaluation design.
5. Main result with units, denominator, n, and effect size.
6. Uncertainty and diagnostics (interval method, convergence, censoring counts).
7. Practical consequence, such as alerts per day, cost per verified success, or affected services.
8. What the evidence does not show, such as causation, generalization past the sample, or a population the sample did not cover.
9. Reproduction: the script, the inputs, and the execution status.

Without an experiment or an identification strategy, the headline must not use causal verbs such as "caused", "explains" or "drove". Say "coincides with" or "is associated with" and name the design that would settle it. Report only numbers that came from a run in this session. Label data as synthetic, public, or user-provided. Keep a rate difference of 0.25 as 25 percentage points, never "25%". Never print a model summary in place of an answer.

### 9. Deliver

Keep computation separate from presentation. The script returns tables, arrays and typed results. When the results need to be reused or published as artifacts, follow the `data-engineering` skill's output contract and the results module bundled with it.

Dispatch `python-harness:reviewer` on the analysis script's path, with the question, grain, denominator and baseline fixed above as the agreed contract, the checks below as the acceptance criteria, and the project root and Python version from `survey`. Treat its findings as input to the checks below; it edits nothing.
</workflow>

<dispatch>
Each dispatch in steps 5 and 9 is one `Agent` call to one of these agents. Pass the project root and Python version from `survey` in the request; do not pass a `model`.

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
Before saying done, check these:

- The report answers the stated question.
- Joins, duplicates, missingness and denominators are handled on purpose and reported.
- The split or resampling unit matches the deployment and the design.
- No future or post-outcome information reached training or features.
- The baseline is meaningful, and every comparison uses the same eligible rows.
- Metric and threshold match the operating condition.
- Convergence and numerical warnings are checked.
- Every conclusion is supported by an output produced in this session.
</gates>

<output>
Hand back a rerunnable analysis script and the filled report.
</output>

<handoff>
Work that turns into making code faster, fitting it in memory, validating schemas, generating fixtures or writing tests goes to `data-engineering`; the analysis script and the filled report go with it. The next stage is tactical-slop-review, once code exists. Pass it the analysis script and the report, and say which gates passed and which are open.
</handoff>

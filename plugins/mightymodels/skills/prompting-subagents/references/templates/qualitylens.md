# Template: qualitylens dispatch

For one bounded measurement request from a persona reviewer or review-circus. qualitylens runs the review signals script and transcribes its output; its contract lives in the qualitylens agent file. The worker launches the script by name, as `mightymodels review-signals`, so the dispatch carries no path to it.

**Ten-second checklist:** the target is the changed files or one directory, not the repository root · the history window is explicit (`since`, `max-commits`, or `baseline-ref`) and fits the repository's age · broader context (hotspots) is asked for only when it changes a finding.

```text
<objective>Measure <target> with the review signals script and report the values.</objective>
<context>
Target: <paths>
History window: <since=DATE | max-commits=N | all-history | baseline-ref=REF>
<Include hotspots: yes, only when broader context is needed.>
</context>
```

Slots: target · history window · hotspots flag.

# Template: reviewer dispatch (review-circus dispatching merge-vader or uncle-bob)

For dispatching one persona reviewer worker from review-circus. Each reviewer's method lives in the doctrine skill it preloads, `becoming-merge-vader` or `becoming-uncle-bob`, so neither is passed a doctrine path; the dispatch carries only scope, absolute paths, and conformance inputs. Subagents cannot find review-circus's files themselves, so every path is absolute, under the `<review-circus skill directory>` that review-circus's SKILL.md names.

**Ten-second checklist:** scope explicit (diff, branch+base, ticket, or codebase) · every path absolute and readable: profiles, idiom evidence, run directory · depth and role (lead or secondary) from the review run · uncle-bob gets the metrics JSON path (or a note that the languages are unparsed) and its mode · merge-vader gets the plan/issue when a ticket exists, since "not supplied" is a worse report for no reason · the signals history window only at standard or deep, or for a quick review's one named gap · model comes from the run's `models`, which already applied the depth rule.

```text
<objective>Review <the diff against HEAD | branch X against base Y | the entire codebase> as <merge-vader | uncle-bob> and return your complete report.</objective>
<context>Profile: <review-circus skill directory>/references/profiles.md, depth <quick | standard | deep>, you are the <lead | secondary> persona. Idiom evidence rules: <review-circus skill directory>/references/idiom-evidence.md. Run directory: <absolute run directory>. <Ticket: .mightymodels/<slug>/ticket.yml. Issue: #<n>. Plan path when one exists; merge-vader's conformance check consumes it.> <uncle-bob only: Metrics: <run directory>/uncle-bob-metrics.json. Mode: <pure | calibrated>.> <Signals history window: <baseline-ref=REF | max-commits=N | since=DATE | all-history>.></context>
<output>Return the report as your whole response, in the doctrine's template. review-circus writes it to <MERGE-VADER-REPORT.md | UNCLE-BOB-REPORT.md> in the run directory. Findings carry Fix: and Verify: lines an engineer can consume without re-deriving the analysis. A quality finding at Medium or above cites its evidence by kind (metric, idiom, convention); one that needs a design decision carries an Architect escalation line.</output>
```

Slots: reviewer · scope · profile and idiom-evidence paths · depth and role · run directory · ticket, issue, and plan · metrics path and mode (uncle-bob) · signals history window.

# Review profiles

Read before the scope dialog and when building a reviewer dispatch. The `review` tool's `start` action encodes every rule here; this file explains them. A profile is depth plus emphasis. Depth sets the evidence budget and the model tier; emphasis sets which persona leads. Neither changes what counts as a valid finding or how severity is judged.

## Depth

| Depth    | Personas                                                   | Reviewer model                                                                                           | Evidence                                                                                                                 |
| -------- | ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| quick    | one: `persona`, else the heavier weight (a tie is refused) | `sonnet`                                                                                                 | Scouts or qualitylens only to close one named evidence gap. Bounded second opinion. Replaces calling a persona directly. |
| standard | each persona weighted 0.25 or more                         | `opus`                                                                                                   | Targeted code-scout waves; qualitylens for churn and coupling on the changed files.                                      |
| deep     | both                                                       | `opus`                                                                                                   | Broad evidence waves, web-scout idiom documentation for quality findings, full report.                                   |

The `override` action moves the run's heavier-weighted reviewer to `fable` once, to be dispatched with effort high; a ticket's reviewer keys change nothing. Evidence workers (code-scout, web-scout, qualitylens) always run on `haiku`, their fixed model.

## Emphasis

| Emphasis          | merge-vader                                                 | uncle-bob |
| ----------------- | ----------------------------------------------------------- | --------- |
| release-readiness | 0.7                                                         | 0.3       |
| maintainability   | 0.3                                                         | 0.7       |
| balanced          | 0.5                                                         | 0.5       |
| custom            | `weights` for both personas, each from 0 to 1, summing to 1 |           |

Weights do three things: pick the persona for a quick review that names none, drop a persona below 0.25 from a standard review, and order findings inside one severity in the gate and the report. They never filter a finding, lower a severity, or hide a Critical or High finding. The dispatch names the persona's role as lead (the heavier weight) or secondary, so a secondary persona spends its budget on its highest-severity dimensions.

## Scope

- **diff**: uncommitted and staged changes against HEAD.
- **branch**: the branch against `base`.
- **ticket**: the ticket's branch against `base`, with the plan and issue for merge-vader's conformance check. Needs `slug`.
- **codebase**: a health pass over the whole repository; no base.

## History window for signals

qualitylens needs a window. Default to `--baseline-ref BASE_REF` for branch and ticket scope, and `--max-commits 500` for codebase scope. A legacy repository with slow history can ask for `--all-history` or a release range (`--baseline-ref v2.0.0`); never assume a fixed number of days fits.

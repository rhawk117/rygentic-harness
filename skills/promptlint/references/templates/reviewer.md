# Template: reviewer kickoff (review-circus dispatching uncle-bob or merge-vader)

For dispatching a review skill session from review-circus. Each reviewer's method lives in its own SKILL.md — the dispatch carries only scope, output path, and conformance inputs.

**Ten-second checklist:** scope explicit (branch+base, or codebase-wide) · output path is the active ticket's review dir · model comes from ticket.yml (uncle-bob and merge-vader keys) · plan/issue supplied when conformance checking is wanted — merge-vader writes "not supplied" otherwise, which is a worse report for no reason if the issue exists.

````
<objective>Run <uncle-bob | merge-vader> on <branch X against base Y | the entire codebase>.</objective>
<context>Ticket: .mightymodels/<slug>/ticket.yml. Issue: #<n>. <Plan path when one exists — merge-vader's conformance check consumes it.></context>
<output>Write your report to .mightymodels/<slug>/review/<UNCLE-BOB-REPORT.md | MERGE-VADER-REPORT.md>. Findings carry Fix: and Verify: lines an engineer can consume without re-deriving the analysis.</output>
````

Slots: reviewer · scope · ticket path · issue number · plan path · report path.

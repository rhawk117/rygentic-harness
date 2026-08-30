# Template: budgetron dispatch

For one named residual with a bounded fix — a verification leftover or a review finding. The budgetron contract (budget, escalation, report) lives in agents/budgetron.md. The finding's own Fix: and Verify: lines are the payload; paste them verbatim, never paraphrase — paraphrase is where scope creep starts.

**Ten-second checklist:** exactly one issue named · Fix: is a bounded action, not a goal · Verify: is a command or grep the budgetron can run · commit/push instructions explicit.

````
<objective>Close one residual: <issue id and one-line name>.</objective>
<context><where it came from: which task's verification, or which review finding — one line></context>
Fix: <verbatim from the finding or verification failure>
Verify: <verbatim check>
<constraints>Commit as "<message>". <"Push after committing." only in remediation mode.> If this exceeds the named fix, escalate per your contract — do not widen.</constraints>
````

Slots: issue id · source line · Fix · Verify · commit message · push flag.

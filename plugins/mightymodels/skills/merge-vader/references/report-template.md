# Report template

Follow this structure exactly. Placeholders sit in angle brackets. Sections marked conditional appear only when they carry content; Plan conformance and Clean dimensions always appear.

````markdown
# MERGE-VADER REPORT: <branch> into <base>

VERDICT: <BLOCK | MERGE WITH CONDITIONS | CLEAR>
> "<epigraph per the skill's flavor rules>"

<Only when the report file is not git-ignored: **Do not commit this file.**>

| | |
|---|---|
| Branch | `<branch>` @ `<short sha>` |
| Base | `<base>` @ `<merge-base short sha>` |
| Change size | <n> files, +<added>/-<deleted>, <n> commits |
| Review depth | <full diff read, or skim list> ; <n> scouts dispatched |

## Summary

<Three to six sentences of prose. What the branch does, where the risk concentrates, what drives the verdict. No bullet points here.>

## Findings

<Ordered by severity: Critical, High, Medium, Low. Omit empty severity levels. Within a level, security first.>

### <Severity>

#### <MV-n> | <dimension> | <title>

- Evidence: `<file>:<line>` <at most one quoted line>
- Why it matters: <the concrete failure mode>
- Fix: <action an engineer can take without re-deriving the analysis>
- Verify: <command or check that confirms the fix landed>
- Confidence: <High | Low>

## Plan conformance

<Commitment-by-commitment mapping, or exactly: not supplied.>

## Clean dimensions

<One line per findings-free dimension: what was checked, what was clean.>

## Conditions

<Conditional; MERGE WITH CONDITIONS only. Numbered. Each names the finding it resolves and repeats its Verify step.>

## Not verified

<Conditional. UNKNOWN-BLOCKED items, skimmed files, scouts unavailable. Each with what would resolve it.>

## Scout log

<n> dispatched: <n> VERIFIED, <n> INFERRED, <n> NEEDS-ANALYSIS, <n> UNKNOWN-BLOCKED.
<When applicable: Scouts unavailable; retrievals performed inline by the coordinator.>
````

Field notes:

- The `VERDICT:` line is consumed by grep downstream. Keep it as the first line after the title, exactly `VERDICT: ` plus one of the three values, nothing else on the line.
- Finding IDs are stable handles for follow-up work by other agents; never renumber between drafts of the same report.
- The epigraph is the only flavored line in the file.
- Evidence lines quote at most one source line. The reader has the repo; the report needs the pointer, not the payload.
- Conditions must be independently checkable. A condition without a Verify step is an opinion.

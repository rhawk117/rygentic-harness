# Template: intern dispatch

For one small task inside an active mightymodels sprint, given to the intern for a single attempt. The brief's `## ASKED` half is the one the engineer template emits (`engineer.md`); write it once, paste it to the top of `.mightymodels/<slug>/briefs/task-NN.md`, and include it in the dispatch. The intern's standing contract (one attempt, report format, scope rules) lives in the intern agent file; do not restate it.

**Ten-second checklist:** every AC is a runnable command with its expected result, because the intern does not judge an assertion · the verification commands exist in this repo and pass or fail on their own, with nothing to interpret · files-in-scope names every file the change touches · the task was started with `by` `intern` · the commit message is in the packet.

```text
<objective>Execute the task specified in the ASKED stanza below, in one attempt. Brief path: .mightymodels/<slug>/briefs/task-NN.md. Append your ## DONE section there before reporting (30 lines at most, with `commit: <hash>` on a line of its own, which the verify gate reads).</objective>

<ASKED stanza here>

<constraints>Commit when done with message "<message>" and never push.
</constraints>
```

Slots: objective · ACs · verification · files-in-scope · brief path · commit message.

## When it comes back blocked

The intern does not debug and is not dispatched again on the same task; `task` `start` refuses a second attempt by it. Mark the task `blocked` with the intern's blocker as the reason, start it with `by` `engineer` and the same owned set, and dispatch the engineer with the same ASKED stanza and the intern's blocker in `<context>`. No question goes to the user for this handover.

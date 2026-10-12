# Template: engineer dispatch (emits the ASKED stanza)

For one task dispatch inside an active mightymodels sprint. This template's first output block IS the brief's `## ASKED` half — write it once, paste it to the top of `.mightymodels/<slug>/briefs/task-NN.md`, and include it in the dispatch. The engineer's standing contract (report format, scope rules, blast-radius doctrine) lives in the engineer agent file — do not restate it.

**Ten-second checklist:** every AC is checkable — a runnable command or an assertion with a location; "works correctly" is a placeholder, reject it · files-in-scope is disjoint from any other open group's set · the verification commands actually exist in this repo (check the runner config before promising them) · tier bump, if any, has its reason logged · the toolchain lines are pasted from `toolchain.md` (a hook the commit runs, a lint ban, a sandbox denial, a tool the task can use), never recalled.

ASKED stanza (goes in the brief AND the dispatch):

```text
## ASKED
objective: <one sentence — what and why>
acceptance:
  - AC-1: <runnable command, or checkable assertion with file/behavior named>
  - AC-2: <...>
verification: <commands, in order>
files-in-scope: [<paths this task owns>]
engineer-tier: <model from ticket.yml, or bumped one tier: reason>
uses: [<repository skills or instruction files, when the task names them>]
toolchain: [<the TC lines of .mightymodels/<slug>/toolchain.md that bind this task, verbatim; left out on a ticket with no survey>]
```

Dispatch wrapper around the stanza:

```text
<objective>Execute the task specified in the ASKED stanza below. Brief path: .mightymodels/<slug>/briefs/task-NN.md — append your ## DONE section there before reporting (≤65 lines, with `commit: <hash>` on a line of its own, which the verify gate reads).</objective>

<ASKED stanza here>

<constraints>Commit when done with message "<message>" and never push.
</constraints>
```

Slots: objective · ACs · verification · files-in-scope · tier(+reason) · toolchain lines · brief path · commit message.

## Residual variant

For one named residual with a bounded fix: a verification leftover, a mechanical CI failure, or a review finding carrying Fix: and Verify: lines. The finding's own lines are the payload; paste them verbatim, never paraphrase, because paraphrase is where scope creep starts. No brief is written for a residual.

**Ten-second checklist:** exactly one issue named · Fix: is a bounded action, not a goal · Verify: is a command or grep the engineer can run · files-in-scope names every file the Fix touches · commit/push instructions explicit.

```text
<objective>Close one residual: <issue id and one-line name>. Treat it as a group of one task with the id <issue id>.</objective>
<context><where it came from: which task's verification, which CI check, or which review finding, one line></context>
files-in-scope: [<every file the Fix touches>]
Fix: <verbatim from the finding or verification failure>
Verify: <verbatim check>
<constraints>Commit as "<message>" and never push. One attempt: if Verify still fails, report failed with the output tail; if the Fix needs a file outside files-in-scope, report blocked.</constraints>
```

Slots: issue id · source line · files-in-scope · Fix · Verify · commit message.

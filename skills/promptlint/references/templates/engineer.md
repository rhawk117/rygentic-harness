# Template: engineer dispatch (emits the ASKED stanza)

For one task dispatch inside an active mightymodels sprint. This template's first output block IS the brief's `## ASKED` half — write it once, paste it to the top of `.mightymodels/<slug>/briefs/task-NN.md`, and include it in the dispatch. The engineer's standing contract (report format, scope rules, blast-radius doctrine) lives in engineer.agent.md — do not restate it.

**Ten-second checklist:** every AC is checkable — a runnable command or an assertion with a location; "works correctly" is a placeholder, reject it · files-in-scope is disjoint from any other open group's set · the verification commands actually exist in this repo (check the runner config before promising them) · tier bump, if any, has its reason logged.

ASKED stanza (goes in the brief AND the dispatch):

````
## ASKED
objective: <one sentence — what and why>
acceptance:
  - AC-1: <runnable command, or checkable assertion with file/behavior named>
  - AC-2: <...>
verification: <commands, in order>
files-in-scope: [<paths this task owns>]
engineer-tier: <model from ticket.yml, or bumped one tier: reason>
uses: [<repository skills or instruction files, when the task names them>]
````

Dispatch wrapper around the stanza:

````
<objective>Execute the task specified in the ASKED stanza below. Brief path: .mightymodels/<slug>/briefs/task-NN.md — append your ## DONE section there before reporting (≤65 lines).</objective>

<ASKED stanza here>

<constraints>Commit when done with message "<message>". <Push only if this dispatch is remediation-mode: "push after committing.">
</constraints>
````

Slots: objective · ACs · verification · files-in-scope · tier(+reason) · brief path · commit message · push flag.

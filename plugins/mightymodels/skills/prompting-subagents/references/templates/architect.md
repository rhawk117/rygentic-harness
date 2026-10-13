# Template: architect dispatch

For escalating one task to the recovery tier after engineer returned `failed` or `blocked`, or after a designated reviewer rejected an implementation for poor code quality with structured evidence. The architect's standing contract (modes, envelope rules, result shape) lives in the architect agent file; carry only what varies per dispatch.

**Ten-second checklist:** the trigger is pasted verbatim (the engineer's report, or the reviewer's finding with future pressure, expected churn, clean extension path, and locations) · the ASKED contract is the one the engineer received, unedited · files-in-scope is the original owned set, and `systemic-refactor` appears only with an approved expanded envelope attached · the brief path is named when the task has one, and a residual (`R<n>` or `C<n>`) has none, so its packet carries the slug and its contract ids · the task is started with `by` `architect`, after the owner's answer unless the ticket has `auto-escalate` on · this is the task's first architect dispatch; a second failure goes to whats-broken, not back here.

```text
<objective>Recover task <task id> in <recovery-implementation | systemic-refactor | diagnose-replan> mode. Brief path: .mightymodels/<slug>/briefs/task-NN.md (replace its DONE half with yours before reporting; when you commit, it carries `commit: <hash>` on a line of its own, which the verify gate reads).</objective>
<context>
Trigger: <engineer failed | engineer blocked | reviewer rejection>, verbatim below.
<the engineer's report, or the reviewer finding, unedited>
<Residual only, in place of the brief path: slug: <ticket slug>. contract-id: <the ids its Verify lines were approved under>.>
</context>

<the task's ASKED stanza, unedited, including files-in-scope>

<constraints>
Envelope: <files-in-scope from ASKED | the approved expanded envelope, listed>. Commit when done with message "<message>" and never push.
</constraints>
```

Slots: task id · mode · brief path, or slug and contract ids for a residual · trigger text · ASKED stanza · envelope · commit message.

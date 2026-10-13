# Shared operating method

The lead owns one shared brief. Carry it between contributing skills:

- outcome and caller;
- representative accepted and rejected examples;
- rules, errors, and partial-success behavior;
- environment and inspected evidence;
- state, dependency, transaction, concurrency, and cleanup ownership;
- decisions with rationale;
- unresolved questions and what they block;
- verification commands, results, and limitations.

Ask two to four connected questions per round and skip facts already established by
evidence. Classify missing information as blocking, safely inferable from repository
convention, or deferred. In contributor mode, ask only questions absent from the shared brief
and return them to the lead rather than starting a second interview.

One mutable artifact has one owner:

- the contract phase owns public application contracts.
- Design Persistence owns persistence decisions, adapter contracts, and migration plans.
- the `design-tests` skill, run by the `test-engineer` agent, owns scenario tests.
- the implementation phase owns the permitted implementation slice.

Contributors return conflicts to the lead rather than silently rewriting another owner's
artifact. A handoff names the task, input artifacts, permitted changes, required outputs,
acceptance criteria, and unresolved questions.

Report design inspection, manual walkthrough, and implementation-backed checks separately.
Test friction reopens the relevant design gate.

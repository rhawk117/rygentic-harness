# Shared operating method

Carry one shared brief between contributing skills:

- outcome and caller;
- representative accepted and rejected examples;
- rules, errors, and partial-success behavior;
- environment and inspected evidence;
- state, dependency, transaction, concurrency, and cleanup ownership;
- decisions with rationale;
- unresolved questions and what they block;
- verification commands, results, and limitations.

Ask two to four connected questions per round. Classify missing information as
blocking, safely inferable from repository convention, or deferred. In
contributor mode, ask only questions absent from the shared brief and return
them to the lead.

One mutable artifact has one owner. The contract phase owns public design,
the Test Engineer owns scenario tests, and a domain implementer owns business
behavior. A handoff names the task, input artifacts, permitted changes,
required outputs, acceptance criteria, and unresolved questions.

Write interfaces before implementation when behavior or ownership is
consequential. Use a protocol only at a meaningful replaceable or caller-owned
boundary. Test friction reopens the relevant design gate.

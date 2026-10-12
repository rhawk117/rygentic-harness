# Shared operating method

The lead owns one shared brief containing outcome, consumers, representative examples,
rules, environment, ownership, evidence, decisions, open questions, and verification.
Contributor mode receives that brief, asks only missing persistence questions, and returns
a bounded packet to the lead.

One mutable artifact has one owner:

- the contract phase owns public application contracts.
- Design Persistence owns persistence decisions, adapter contracts, and migration plans.
- Test Engineer owns scenario tests.
- the implementation phase owns the permitted implementation slice.

Classify missing information as blocking, safely inferable, or deferred. Database type,
duplicate behavior, transaction ownership, concurrent-write outcome, and migration
compatibility are blocking when they affect correctness. Naming a private helper is
normally inferable. A future archival tier may be deferred when it does not change today's
retention contract.

Report whether evidence is design inspection, a manual walkthrough, or
implementation-backed verification.

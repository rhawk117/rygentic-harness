# Design-tests interview and gates

Ask two to four connected questions per round and reuse the shared brief.

## Round 1: promises

Ask:

1. What can callers observe and rely on?
2. Which compatibility promise must survive refactoring?
3. Which defect would cause meaningful harm?
4. Which current output is documented, and which is merely incidental?

**Gate 1:** every important promise has an observable and a harmful defect.

Rank the resulting risks before choosing tests. Business invariant violations
and corrupted state outrank convenience, coverage percentage, and internal
call verification.

## Round 2: boundaries

Ask:

1. Which external systems can run locally?
2. Which boundaries require a fake, mock, controlled clock, or real compatible
   service?
3. Who owns fixture setup, mutable state, and teardown?
4. Is the contract about returned behavior, committed state, or interaction
   with a dependency?

**Gate 2:** every scenario has a justified test level, substitute, fixture
owner, and cleanup plan.

Classify each selected test as domain unit, use-case contract, repository
contract, adapter integration, end-to-end, characterization, property, or
concurrency/fault.

## Round 3: semantics

Ask:

1. Is result order meaningful to callers?
2. Is exact error wording contractual, or are type and structured fields
   sufficient?
3. Does serialized field order matter?
4. For numeric or generated values, which invariant or tolerance matters?

**Gate 3:** assertions cover semantic behavior without freezing incidental
representation.

## Branching follow-ups

- If order matters, ask what key establishes it and which ties are legal.
- If retries matter, distinguish “eventually succeeds” from an exact attempt
  count.
- If mocks are proposed, ask which interaction is public contract rather than
  implementation detail.
- If broad inputs share invariants, inspect whether Hypothesis is installed
  before recommending project-local opt-in.
- If contract tests predate implementation, require strict XFAIL and a reason.

## Worked branch

The first batch-import draft accepted `Iterable[OrderDraft]` and returned
outcomes keyed only by `order_id`.

The duplicate scenario asked which of two same-ID inputs was accepted. A test
could assert one accepted and one duplicate, but a broken implementation that
attached the duplicate outcome to the wrong input would still pass.

The friction packet reopened the enterprise-design ergonomics gate. The
revised contract accepts `Sequence[OrderDraft]` and includes `input_index` in
every item outcome. The test can now assert that index 0 is accepted and index
1 is duplicate without relying on private state.

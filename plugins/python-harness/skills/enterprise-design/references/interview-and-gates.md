# Enterprise-design interview and gates

Ask two to four connected questions per round. Skip questions already answered
by repository evidence or the shared brief, and record the evidence instead.

## Round 1: operation

Ask:

1. Which caller invokes the operation: application code, an adapter, an
   operator, or another domain component?
2. What does the caller know at invocation time?
3. Which accepted example best represents useful success?
4. Which example must be rejected, and what should the caller observe?

Branch when a term such as duplicate, complete, active, imported, or accepted
could have multiple meanings. Offer concrete alternatives and show the
caller-visible difference.

**Gate 1:** actor, operation, vocabulary, accepted example, and rejected
example are recorded.

## Round 2: business rules

Ask:

1. What must remain true after every call?
2. Which transitions are allowed?
3. Are duplicates idempotent successes, separately reported no-ops, updates,
   or operation-wide errors?
4. With valid and invalid items together, is the result atomic, partially
   successful, or continuing with a rejection report?

Follow partial success with questions about result identity, side effects for
accepted items, and whether rejected items are retryable. Follow duplicate
answers with identity-key and repeated-batch questions.

**Gate 2:** preconditions, postconditions, duplicate semantics, partial-success
semantics, and expected rejection are observable.

## Round 3: boundaries

Ask:

1. Which dependencies already exist, and which party constructs them?
2. Who owns the transaction or commit boundary?
3. May calls overlap, and which state is shared?
4. Which dependency failures are safe to retry, and how can the caller tell?

If the user does not know the engineering mechanism, explain the behavioral
trade-off with one example and ask for the desired behavior.

**Gate 3:** dependency ownership, side-effect boundary, transaction ownership,
overlap, retry, and compatibility are explicit.

## Round 4: architecture ownership

Ask:

1. What is the single caller-visible use case?
2. Which invariants belong to entities or values?
3. Does any rule genuinely need a domain service?
4. Which persistence operations does the use case need from a repository?

Present a boundary table and dependency direction. Reject generic “service”
and CRUD repository labels that do not identify responsibility.

**Gate 4:** each component has one role, dependencies point inward, and
transaction/error ownership is explicit.

## Round 5: interface review

Show the complete proposed Python declarations: inputs, outputs, use-case
constructor and method, repository protocol methods, and concrete exceptions.
Explain every boundary and ask only about consequential alternatives.

**Gate 5:** the user has reviewed the exact API surface.

## Round 6: caller ergonomics

Show the proposed signatures and examples. Ask:

1. Can the caller perform the accepted case in one documented sequence?
2. Can it distinguish duplicate, rejection, and dependency failure without
   strings or private state?
3. Does partial success identify every input outcome needed for recovery?
4. Is any ordering guarantee actually semantic?

**Gate 6:** normal and recovery examples are complete and no consequential
choice remains hidden.

## Worked branch

Initial answer: “The importer accepts any iterable and reports duplicate order
IDs.”

Proposed signature:

```python
class ImportOrders:
    def __init__(self, repository: OrderRepository) -> None: ...

    def execute(self, orders: Iterable[OrderDraft]) -> ImportResult: ...
```

Test-writing friction: a batch containing the same ID twice needs to identify
which occurrence was accepted and which was the duplicate. A one-shot iterable
cannot be safely revisited to correlate outcomes.

Follow-up: “Must callers recover by original input position, or is order ID
alone sufficient?”

Answer: original position is required.

Revised signature and result:

```python
class ImportOrders:
    def __init__(self, repository: OrderRepository) -> None: ...

    def execute(self, request: ImportOrdersRequest) -> ImportResult: ...


@dataclass(frozen=True, slots=True)
class ImportOrdersRequest:
    orders: Sequence[OrderDraft]


@dataclass(frozen=True, slots=True)
class ItemOutcome:
    input_index: int
    order_id: str
    kind: ItemOutcomeKind
```

The answer changes the public input contract and result identity before an
implementation is written.

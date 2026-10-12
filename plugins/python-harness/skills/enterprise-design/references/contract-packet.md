# Contract design packet

Use this inline Markdown template after the operation, rules, boundaries, interface review,
and caller ergonomics gates pass. It is a durable design record for the lead, not generated
workflow state.

## Operation

- **Operation:** `<domain operation>`
- **Caller:** `<consumer>`
- **Vocabulary:** `<term: meaning pairs>`
- **Public artifacts:** `<path and exported symbol>`

## Boundaries

For each component, record:

- **Component:** `<name>`
- **Role:** `entity | value | use-case | domain-service | repository | adapter | DTO`
- **Responsibility:** `<one responsibility>`
- **Owns:** `<state, transaction, resource, or none>`
- **Depends on:** `<inward dependencies>`
- **Public operations:** `<exact signatures>`
- **Failure translation:** `<source error to public error>`

## Signatures and rules

- **Exact declarations:** `<complete importable Python declarations>`
- **Rule ID:** `<R1>`
- **Precondition:** `<condition>`
- **Postcondition:** `<observable result>`
- **Side effects:** `<effects or none>`

## Outcomes and ownership

- **Partial success:** `<aggregate representation>`
- **Duplicate:** `<item or operation representation>`
- **Expected rejection:** `<typed result or concrete exception>`
- **Dependency failure:** `<concrete exception and retry semantics>`
- **Dependency owner:** `<constructor or call owner>`
- **Transaction owner:** `<owner and boundary>`
- **Mutable-state owner:** `<owner and lifetime>`

## Examples and evidence

- **Normal:** `<caller example>`
- **Recovery:** `<expected recovery example>`
- **Contract tests:** `<path and promise covered>`
- **Interface shown to user:** `true | false`
- **Consequential choices accepted:** `true | false`
- **Unresolved:** `<blocking decision or none>`

## Batch-import example

The import result contains item outcomes with `input_index`, `order_id`, and a kind of
accepted, duplicate, or rejected. `partial_success` is true only when accepted items
coexist with duplicate or rejected items. Repository unavailability raises
`DependencyFailureError` with the failed operation and retryability; it is not an item
rejection.

A repository protocol is justified because persistence is caller-owned and tests need a
meaningful in-memory substitute. `ImportOrders` is an application use case: it owns one
operation and receives the repository port through its constructor. It is not a generic
service or persistence adapter.

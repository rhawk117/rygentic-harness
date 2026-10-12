# Scenario-test design packet

Use this inline Markdown template after the promises, boundaries, and semantics gates pass.
The packet selects executable evidence; it does not replace the contract or production
implementation.

## Contract source and priorities

- **Contract source:** `<contract design or public file>`
- **Priority:** `<rank>`
- **Risk:** `<business or failure risk>`
- **Test kind:** `<selected kind>`
- **Reason:** `<why this is high-value evidence>`

## Scenarios

For each scenario, record:

- **ID:** `<descriptive-id>`
- **Promise:** `<public promise>`
- **Kind:** `domain-unit | use-case-contract | repository-contract | adapter-integration | end-to-end | characterization | property | concurrency-fault`
- **Level:** `unit | integration | end-to-end`
- **Fixture owner:** `<fixture and resource>`
- **Observable:** `<result, error, or committed state>`
- **Plausible broken implementation:** `<defect this test rejects>`
- **Ordering semantic:** `true | false`
- **Status:** `executable | awaiting-implementation`

## Tools, friction, and execution

- **pytest-mock:** `installed | absent | not-needed`
- **Hypothesis:** `installed | absent | not-needed`
- **Friction:** `<contract issue returned to design or none>`
- **Deferred:** `<lower-priority test and why it is deferred>`
- **Commands and observed results:** `<literal command and result>`

## Batch-import scenario map

The following examples remain useful when designing batch-import evidence:

| ID                                  | Promise                                                               | Plausible broken implementation rejected                             |
| ----------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `mixed-batch-partial-success`       | accepted and rejected items coexist and `partial_success` is true     | rejects the entire batch after one invalid item                      |
| `duplicate-second-occurrence`       | duplicate is distinct and tied to the second input index              | deduplicates silently or attributes the duplicate to the first input |
| `expected-rejection-structured`     | invalid transition is a rejected outcome with a reason code           | raises a generic exception or stores the invalid item                |
| `dependency-failure-operation-wide` | repository failure raises `DependencyFailureError` with retry context | converts outage into item rejection or an empty success              |

The four scenarios are use-case contract tests with an in-memory repository. A reusable
repository contract suite and real adapter integration test are deferred until an
implementation and adapter exist. Result order is semantic only through `input_index`;
collection storage order is otherwise not asserted.

# Implementation handoff design

Use this inline Markdown template only after the contract, persistence, and scenario-test
decisions are complete. It describes the work a later implementation phase would receive;
it does not select or dispatch an agent.

## Operation and inputs

- **Operation:** `<operation>`
- **Caller:** `<consumer>`
- **Required capability:** `<domain and technical capability>`
- **Contract design:** `<path or embedded record>`
- **Persistence design:** `<path or embedded record>`
- **Scenario-test design:** `<path or embedded record>`

## Interface and boundaries

- **Public declarations:** `<exact Python signatures>`
- **Boundary table:** `<components, responsibilities, dependencies, and ownership>`
- **Dependency direction:** `<caller to use case to domain and ports to adapters>`
- **Error and transaction ownership:** `<explicit owners>`

## Scope and acceptance

- **Permitted production paths:** `<relative paths>`
- **Permitted test paths:** `<relative paths>`
- **Required outputs:** `<files, evidence, and report>`
- **Acceptance criteria:** `<observable success, rejection, failure, and cleanup behavior>`
- **Unresolved decisions:** `<none or each blocker>`
- **Verification limitations:** `<checks not run or evidence not available>`
- **Status:** `ready | blocked`

Stop and return the handoff to the design gate when any unresolved item changes caller
behavior, authorization, transaction ownership, durability, or deployment safety.

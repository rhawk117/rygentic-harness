# Persistence design packet

Use this inline Markdown template after the meaning, access, invariant, transition,
placement, transaction, concurrency, and migration gates pass. It is a decision record, not
permission to generate models or migrations before those gates.

## Records

- **Name:** `<business record>`
- **Meaning:** `<fact represented>`
- **Identity:** `<internal and external identity>`
- **Ownership:** `<tenant, account, system, or none>`
- **Lifecycle:** `<states and deletion/history behavior>`

## Access patterns

- **Operation:** `<read or write>`
- **Shape:** `<keys, filters, ordering, cardinality>`
- **Scale:** `<expected volume and concurrency>`
- **Consistency:** `<required observation>`

## Transitions

- **Current state:** `<state>`
- **Action:** `<operation>`
- **Actor:** `<authorized actor>`
- **Preconditions:** `<rules>`
- **Next state:** `<state>`
- **Committed effects:** `<effects>`
- **Rejection:** `<typed outcome>`

## Constraints

For each invariant, record:

- **Rule:** `<invariant>`
- **Authority:** `database | application | external`
- **Mechanism:** `<constraint, policy, or external check>`
- **Reason:** `<placement rationale>`
- **Concurrent conflict:** `<observable outcome>`
- **Test evidence:** `<scenario or check>`

## Transaction and interfaces

- **Transaction owner:** `<use case or unit of work>`
- **Begins:** `<boundary>`
- **Commits:** `<boundary>`
- **Rollback:** `<conditions>`
- **External-effect order:** `<order and reconciliation>`
- **Persistence interfaces:** `<exact Python declarations>`

## Database

- **Family:** `SQL | NoSQL`
- **Product:** `<selected database>`
- **Driver:** `<selected driver>`
- **Rationale:** `<requirements evidence>`

## Migration

- **Existing data:** `<evidence>`
- **Coexistence:** `<versions>`
- **Phases:** `<expand, backfill, contract>`
- **Verification gate:** `<evidence required before contract>`
- **Recovery:** `<rollback or forward repair>`

## Tests and status

- **Tests:** `<transition, repository, adapter, concurrency, or migration evidence>`
- **Unresolved:** `<blocking decision or none>`
- **Status:** `ready | not-applicable | blocked`

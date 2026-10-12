# Persistence interview and gates

Ask connected questions in rounds. Branch from supplied evidence instead of dumping every
question on the user.

## Round 1: meaning, access, and database family

Ask:

1. What real-world fact does each record represent, and who owns it?
2. Which identifiers are internal, external, user-visible, tenant-scoped, or reusable?
3. What are the common and highest-cost reads and writes?
4. What consistency, latency, volume, retention, and availability are required?
5. Are relationships and multi-record transactions central, or are aggregate/document
   access patterns dominant?
6. Does the user require SQL or NoSQL, and what existing infrastructure constrains it?

Branch:

- If SQL is selected, compare concrete relational choices in `database-selection.md`.
- If NoSQL is selected, ask for partition key, query shapes, consistency, transaction
  boundaries, secondary indexes, item size, hot-key risk, and operational ownership.
- If the project already has a database, preserve it unless evidence shows it cannot meet
  a blocking requirement.

Gates:

- **Meaning:** identities, ownership, time, units, and lifecycle are unambiguous.
- **Access:** known queries and writes drive the model; no speculative index list exists.
- **Database family:** SQL versus NoSQL and concrete product remain decisions, not defaults.

## Round 2: invariants, transitions, deletion, and history

Ask:

1. Which fields are required in each state, and which values are derived?
2. What is unique, within what scope, and what should a duplicate writer observe?
3. Which actors may perform each state transition?
4. Can a transition be retried, reversed, superseded, or repeated?
5. Is deletion physical, logical, prohibited, or represented by a terminal state?
6. Which history is required for audit, support, billing, or reconciliation?

Follow up when:

- uniqueness includes nullable values, case folding, time windows, tenant scope, or soft-
  deleted rows;
- one operation updates multiple aggregates;
- history must be immutable or queryable at a prior point in time;
- external identifiers can be reassigned;
- stored state duplicates facts derivable from authoritative data.

Gates:

- **Invariants:** every required, optional, derived, and unique rule is stated.
- **Transitions:** a transition table identifies actor, precondition, next state, effects,
  and rejection.
- **History:** deletion, retention, audit, and restoration behavior are explicit.

## Round 3: transactions, concurrent writes, and external effects

Ask:

1. What must commit atomically?
2. Which use case controls the transaction boundary?
3. What can two callers change concurrently, and what should the loser observe?
4. Can the caller retry after timeout without duplicating effects?
5. What happens if a remote side effect succeeds and the database commit fails?
6. Does any queue or consumer deliver messages more than once?

Follow up with optimistic versions, locks, unique constraints, idempotency records,
outbox/inbox, or reconciliation only when the answers require them.

Gates:

- **Transaction:** one owner controls begin, commit, rollback, and repository participation.
- **Concurrency:** overlap and conflict outcomes are observable and testable.
- **Failure ordering:** external effects, persistence, publication, and recovery have a
  deliberate order.

## Round 4: existing data and migration compatibility

Ask:

1. Does data already exist, and can writes pause?
2. Must old and new application versions run concurrently?
3. How will new required values and constraints be backfilled and verified?
4. Which indexes or table rewrites can block production traffic?
5. Is downgrade required, or is forward repair the supported recovery path?
6. How are partial migration, deploy rollback, and incompatible worker versions handled?

Gates:

- **Compatibility:** every application version in the rollout can use the intermediate
  schema.
- **Validation:** existing rows are measured before a constraint becomes authoritative.
- **Recovery:** failure has a tested rollback or forward-repair procedure.

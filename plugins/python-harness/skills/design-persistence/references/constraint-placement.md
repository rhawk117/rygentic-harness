# Constraint placement

For every rule, name the authoritative enforcement point and why it belongs there.

## Database constraints

Place a rule in the database when it depends only on committed database facts and must
hold across every writer. Examples include non-null requirements, referential integrity,
tenant-scoped uniqueness, bounded scalar checks, and mutually exclusive rows expressible
by a supported constraint or index.

An application-side existence query is not a uniqueness guarantee. Concurrent writers
can both pass the query. Use a database constraint and translate the resulting named
integrity conflict.

## Application constraints

Place a rule in the application when it needs:

- authenticated identity or authorization policy;
- a state transition with actor and workflow context;
- multiple external facts or an authoritative remote decision;
- a richer rejection reason than a database constraint can safely express;
- ordering across persistence and external side effects.

The database may still enforce lower-level facts that protect against invalid committed
state.

## External policy boundaries

Place a rule at an external authority when that system owns the fact: identity-provider
account state, payment authorization, regulatory eligibility, or another service's
resource policy. Persist the decision or reference only when the business needs audit,
reconciliation, caching, or retry behavior. Do not silently treat a cached external
answer as permanently authoritative.

## Review table

For each constraint record:

| Rule | Authority                         | Enforcement     | Concurrent behavior  | Error translation | Test evidence |
| ---- | --------------------------------- | --------------- | -------------------- | ----------------- | ------------- |
| ...  | database / application / external | exact mechanism | winner/loser outcome | public result     | test          |

---
name: design-persistence
description: >-
  Designs how a Python system stores durable records: record meaning and access patterns,
  invariants and state transitions, where each constraint is enforced, transaction and concurrency
  ownership, repository boundaries and a migration plan. Chooses the database from the
  requirements, writes no project files, and hands the persistence packet to design-tests.
when_to_use: >-
  Use when a Python system needs durable state and the storage is undecided: which database to
  use, what the tables or documents hold, uniqueness and duplicate rules, who owns the
  transaction, what happens under concurrent writes, deletion and history, or migrating existing
  data safely. Typical requests are "design the schema for X", "SQLite or Postgres for this" and
  "plan this migration". Not for deciding the public contract (enterprise-design), making a slow
  query or data pipeline faster (data-engineering) or reviewing finished code
  (tactical-slop-review).
argument-hint: "[persistent state to design]"
paths:
  - "**/*.py"
  - "**/*.pyi"
  - "**/pyproject.toml"
allowed-tools:
  - Read
  - Grep
  - Glob
  - AskUserQuestion
  - mcp__plugin_python-harness_python-harness__survey
  - mcp__plugin_python-harness_python-harness__gate
disallowed-tools:
  - Edit
  - Write
  - NotebookEdit
---

# Design persistence

<purpose>
Turn business meaning and access requirements into durable invariants, transaction boundaries, persistence interfaces, and a migration plan. Work in **lead mode** when the user's outcome is persistence design and in **contributor mode** when another skill, especially `build-web-service`, supplies the shared brief.

This skill writes no project files and dispatches nothing. The accepted persistence decisions and the migration plan are design records kept in the conversation, in the inline Markdown templates of the references, not generated workflow state.
</purpose>

<inputs>
- The service track hands to this skill from enterprise-design, with its accepted contract packet and implementation handoff. It can also be invoked directly, by name or when the request matches the description.
- Paths below that start with `references/` are inside this skill's directory, `${CLAUDE_SKILL_DIR}`. Read now:
  - [Shared operating method](references/shared-method.md)
  - [Interview branches and decision gates](references/interview-and-gates.md)
  - [Database selection](references/database-selection.md)
  - [Constraint placement](references/constraint-placement.md)
  - [Persistence packet](references/persistence-packet.md)
  - [SQLAlchemy and Alembic](references/sqlalchemy-alembic.md)
  - [Django ORM](references/django-orm.md)
  - [sqlite3](references/sqlite3.md)
- Contributor mode receives that brief, asks only missing persistence questions, and returns a bounded packet to the lead.
- Database type, duplicate behavior, transaction ownership, concurrent-write outcome, and migration compatibility are blocking when they affect correctness. Naming a private helper is normally inferable. A future archival tier may be deferred when it does not change today's retention contract.
- The plugin's MCP server names each tool `mcp__plugin_python-harness_python-harness__<tool>`; the steps below use the short names `survey` and `gate`. The project tools take no root argument: the project is the session's project directory (`CLAUDE_PROJECT_DIR`). If these tools are not available, stop: the server did not start. Tell the user to check the plugin in `/plugin` (its Errors tab) and the server in `/mcp`.
- Require:
  - the records' business meaning and identifiers;
  - common and critical reads, writes, transitions, and history questions;
  - duplicate, retry, and concurrent-write behavior;
  - current database, data volume, deployment, and migration evidence, or an explicit greenfield statement;
  - transaction, side-effect, and failure-order requirements;
  - permitted model, adapter, migration, and test paths.
- Call `survey` for the project root, the Python version and the toolchain when the database evidence or the verification depends on them.
- In contributor mode, consume the existing shared brief and return only unresolved persistence questions to the lead. Do not restart the whole service interview.
- Record accepted persistence decisions in the inline Markdown packet template in `references/persistence-packet.md`. The packet is a design record for the lead, not generated workflow state. If required evidence is unavailable, stop and return the missing decision to the lead rather than guessing.
</inputs>

<workflow>
### 1. Establish record meaning and access

Run Interview Round 1. Define what each record represents, its source of identity, time and unit semantics, relationships, ownership, and required reads and writes. Ask whether the system requires SQL or NoSQL before naming a database product.

For a relational branch, compare SQLite with `aiosqlite`, PostgreSQL with `asyncpg`, and MySQL with an async driver against the actual concurrency, scale, operational, and compatibility needs. Do not choose from familiarity alone.

Pass the Meaning and Access gates before proposing tables or document shapes.

### 2. Define invariants and state transitions

Run Interview Round 2. Write:

- stable identifiers and external identifiers;
- required and optional values by lifecycle state;
- uniqueness and duplicate semantics;
- legal transitions and transition actors;
- derived values versus persisted facts;
- deletion, retention, audit, and history rules.

Represent transitions as a table with current state, action, actor, preconditions, next state, committed effects, and rejection. Avoid conflicting Boolean flags when one state machine expresses the rules.

Pass the Invariants and Transitions gates before designing storage.

### 3. Place every constraint deliberately

Use [Constraint placement](references/constraint-placement.md). Classify each rule as:

- database-enforced when it depends only on committed database facts and must hold across every writer;
- application-enforced when it requires workflow context, authorization, external facts, or a richer decision than the database can express safely;
- external-policy-enforced when another authoritative system owns the rule.

Use defense in depth when appropriate, but name the authoritative enforcement point. Do not call a pre-insert application query a uniqueness guarantee under concurrency.

Pass the Placement gate with a reason for every consequential rule.

### 4. Establish transaction and concurrency ownership

Run Interview Round 3. Ask what must commit together, who opens the transaction, whether two callers may update the same record, what retries mean, and what happens when an external side effect and database commit disagree.

Define:

- the work unit and transaction owner;
- repository operations derived from use cases rather than generic CRUD;
- optimistic versioning, row locking, unique constraints, or serialization only where the scenario needs them;
- duplicate-write and integrity-error translation;
- rollback, cancellation, timeout, and retry behavior;
- whether an outbox, inbox, idempotency record, or reconciliation process is required.

Pass the Transaction and Concurrency gates before implementation.

### 5. Define persistence boundaries

Produce exact persistence interfaces and ownership:

- application use case or unit of work controlling the operation;
- repository boundaries with business-shaped operations;
- adapter responsibilities and infrastructure error types;
- session, connection, transaction, and mutable-state lifetimes;
- process-lifetime engine ownership and deterministic async disposal;
- committed outcomes visible to callers.

For the primary async SQLAlchemy path, the `SQLAlchemyAdapter` owns engine and session construction and yields a transactional `AsyncSession`. Unit-of-work classes consume that session and materialize repositories. Repositories may add and flush but never commit. The application lifespan owns the adapter and awaits `engine.dispose()` through the infrastructure aggregate during normal shutdown and partial-startup cleanup. Never treat session closure as engine disposal.

### 6. Plan existing-data and migration compatibility

Run Interview Round 4. Establish whether data exists, whether writes may pause, whether old and new application versions coexist, how constraints are validated against existing rows, and how partial migration failure is recovered.

Review generated migrations. Separate schema and data changes. Use expand, backfill, and contract phases when versions coexist, with an explicit verification gate before the contract phase. Do not run production schema migration automatically from application startup.

Pass the Migration gate before calling the design deployable.

### 7. Delegate contracts and tests

When public application behavior changes, invoke `enterprise-design` in contributor mode with the persistence decisions. Invoke `design-tests` after the contract and persistence packets exist.

Tests should favor stable observable behavior:

- domain transition tests;
- use-case tests with deliberately designed in-memory repository behavior where useful;
- reusable repository contract tests;
- adapter integration tests against the intended database when dialect semantics matter;
- concurrency, rollback, retry, and migration tests only where those risks are contractual.

### 8. Design through the selected stack

Use the stack reference only after the database and adapter decisions are accepted. Preserve existing conventions when compatible. Do not impose SQLAlchemy, Django ORM, or sqlite3 on a project that selected another persistence architecture.

### 9. Verify and report

Call `gate` for the repository's ruff, ty and pytest checks, and run the smallest checks that establish declared constraints, transitions, transactions, adapter compatibility, and migration behavior through it; name any check the gate cannot run as a limitation. Inspect committed state and generated SQL for known access paths. Report literal commands and limitations.

Complete the inline persistence packet with status `ready` only when its unresolved list is empty. Use `not-applicable` only when the accepted brief requires no durable state. Return open decisions to the owning gate rather than filling them with guesses.
</workflow>

<dispatch>
This skill dispatches no agent. Contracts and tests are designed in step 7 by invoking the skills named there.
</dispatch>

<gates>
| Gate        | Required evidence                                                                   | Return path       |
| ----------- | ----------------------------------------------------------------------------------- | ----------------- |
| Meaning     | record purpose, identity, units, time semantics, ownership, and lifecycle           | Interview Round 1 |
| Access      | common and critical reads/writes with expected scale and consistency                | Interview Round 1 |
| Invariants  | required, optional, derived, unique, deletion, retention, and history rules         | Interview Round 2 |
| Transitions | legal state changes, actors, effects, and rejections                                | Interview Round 2 |
| Placement   | database, application, or external authority for every consequential constraint     | Placement review  |
| Transaction | work unit, transaction owner, atomic effects, rollback, retry, and failure ordering | Interview Round 3 |
| Concurrency | overlapping writers, duplicate behavior, locking/versioning, and conflict outcome   | Interview Round 3 |
| Migration   | existing data, coexistence, rollout, validation, recovery, and compatibility        | Interview Round 4 |
| Testability | stable repository contract and evidence at the narrowest realistic boundary         | `design-tests`    |

Complete when:

1. record meaning, access patterns, invariants, transitions, deletion, and history are explicit;
2. SQL versus NoSQL and the concrete database choice follow requirements evidence;
3. every consequential constraint has an authoritative enforcement point and reason;
4. transaction, session, repository, concurrency, duplicate, and retry ownership are explicit;
5. persistence interfaces and infrastructure error translation are exact;
6. existing-data and migration compatibility are resolved or recorded as blocking;
7. selected tests can falsify incorrect transitions, constraints, transaction behavior, and adapter semantics;
8. verification claims match executed evidence.

Edit, Write and NotebookEdit are disallowed for this skill: it creates no project file.
</gates>

<output>
The completed persistence packet in the conversation, plus a chat summary:

- the record meanings, the database choice and the consequential constraint placements with their rationale;
- each gate and whether it passed;
- design inspection and the `gate` result reported separately, with literal check evidence;
- limitations and checks not run;
- unresolved decisions, or a statement that none block the handoff.
</output>

<handoff>
The next stage of the service track is design-tests. Pass it the accepted persistence packet and the contract packet, and say which gates passed, which are open, and that no code or file was changed. A stage this workflow already ran in contributor mode with an accepted packet is complete, so hand to the first stage that has not run.
</handoff>

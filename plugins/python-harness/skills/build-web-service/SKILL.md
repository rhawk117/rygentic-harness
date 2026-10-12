---
name: build-web-service
description: Use when building or extending a Python HTTP service with consequential contracts, identity and authorization, persistence, deferred work, lifecycle resources, traffic constraints, or deployment behavior. It leads requirements discovery and one complete design handoff; FastAPI, Pydantic v2, and async SQLAlchemy are the primary recipe.
argument-hint: "[what to build or extend]"
paths:
  - "**/*.py"
  - "**/*.pyi"
  - "**/pyproject.toml"
allowed-tools:
  - Read
  - Grep
  - Glob
  - AskUserQuestion
  - Agent
  - mcp__plugin_python-harness_python-harness__survey
  - mcp__plugin_python-harness_python-harness__gate
  - mcp__plugin_python-harness_python-harness__plan_review_surface
  - mcp__plugin_python-harness_python-harness__check_citations
  - mcp__plugin_python-harness_python-harness__search_python_docs
  - mcp__plugin_python-harness_python-harness__read_python_docs
disallowed-tools:
  - Edit
  - Write
  - NotebookEdit
---

# Build web service

<purpose>
Lead the user from requirements through one verified Python web-service design. Do not begin with framework files. First establish what the service must do, how complex it is, whether it is backend-only or a BFF, and which architecture decisions are consequential.

Work in **lead mode** for an end-to-end service outcome. Work in **contributor mode** only when another skill supplies a complete shared brief and requests a bounded HTTP implementation phase.

This skill writes no project files and dispatches no implementation. The accepted brief, contract, persistence decisions, scenario tests and design handoff stay in the conversation, in the inline Markdown templates of the references. They are explanatory design documents, not generated workflow state; the handoff records what a later implementation phase must receive.
</purpose>

<inputs>
- This skill is the entry of the service track. It can be invoked directly, by name or when the request matches the description.
- Paths below that start with `references/` are inside this skill's directory, `${CLAUDE_SKILL_DIR}`. Read now: `references/shared-method.md` (shared operating method), `references/interview-and-gates.md` (requirements interview and decision gates), `references/fastapi-pydantic-v2.md` (FastAPI and Pydantic v2 recipe), `references/infrastructure-lifecycle-observability.md` (infrastructure, lifecycle, and observability), `references/async-work-and-capacity.md` (async work, traffic, rate limits, and caching) and `references/vertical-slice-packet.md` (the vertical-slice packet).
- The plugin's MCP server names each tool `mcp__plugin_python-harness_python-harness__<tool>`; the steps below use the short names `survey` and `gate`. The project tools take no root argument: the project is the session's project directory (`CLAUDE_PROJECT_DIR`). If these tools are not available, stop: the server did not start. Tell the user to check the plugin in `/plugin` (its Errors tab) and the server in `/mcp`.
- Require:
  - consumers, operations, and representative requests and responses;
  - backend-only or BFF delivery, including the selected HTML/CSS/JavaScript architecture;
  - compatibility requirements and existing application evidence;
  - identity source and authorization behavior;
  - persistent state, invariants, retries, duplicates, and consistency;
  - streaming, deferred work, external effects, cancellation, and durability;
  - expected and peak RPS, burst shape, payload sizes, latency, concurrency, and limits;
  - caching freshness and invalidation needs;
  - runtime, process count, proxy, startup/shutdown resources, migrations, and observability;
  - permitted contract, production, configuration, migration, and test paths.
- If these are incomplete, run the interview before architecture or implementation.
</inputs>

<workflow>
### 1. Grill the requirements

Call `survey` for the project root, the Python version and the toolchain; the existing application evidence and the dispatches below rely on them.

Run the interview rounds in `references/interview-and-gates.md`. Ask connected questions and follow consequential branches. Do not assume a CRUD service, backend-only delivery, relational database, JWT, edge rate limiting, cache, in-process background task, or single-process deployment.

Classify the service:

- **bounded service:** a small synchronous request path with local state and few effects;
- **workflow service:** multiple operations, durable state, integrations, or deferred work;
- **distributed/durable service:** queues, multiple processes, cross-service consistency, high traffic, or explicit recovery and availability requirements.

Pass the Requirements and Complexity gates before designing contracts.

Record the accepted shared brief in the conversation with `status: ready`, then validate the `requirements` gate. Keep it `draft` while open questions remain.

### 2. Produce contracts

Invoke `enterprise-design` in contributor mode when public behavior, business rules, partial outcomes, duplicates, authorization, retries, or expected failures are consequential. Supply the shared brief; do not make it repeat the service interview.

Require exact request/response examples, application input/output declarations, error types, authorization outcomes, retry semantics, and caller recovery behavior.

Complete the contract phase in the conversation and record the accepted public contract using the inline template in the contract reference before persistence or tests consume it.

### 3. Resolve persistence and the data layer

Invoke `design-persistence` when durable state exists. It must resolve database family and product, record meaning, access patterns, transitions, uniqueness, constraint placement, transaction ownership, concurrent writes, deletion/history, existing data, and migration compatibility.

For the primary async SQLAlchemy path, use a `SQLAlchemyAdapter` that yields an explicitly transactional `AsyncSession`; unit-of-work classes consume the session and materialize repositories. Repositories flush but do not commit.

Pass the Persistence gate before writing ORM models or migrations.

Complete persistence design using the inline packet template, or mark it not applicable only when the accepted requirements contain no durable state. Validate the Persistence gate before test design.

### 4. Design scenario tests

Invoke `design-tests` in contributor mode after contract and persistence packets exist. Prioritize stable behavior that changes less frequently:

1. domain and application outcomes;
2. authorization and failure behavior;
3. state transitions, committed state, and repository contracts;
4. adapter behavior against the intended database;
5. a small number of HTTP integration paths.

Avoid brittle tests of private functions or incidental calls. Deliberately designed in-memory repository behavior is useful for application tests when a repository boundary exists; it does not replace database adapter tests.

Pass the Testability gate before preparing the design handoff.

Record the scenario-test packet with the inline template. Every contract rule identifier must be covered by at least one scenario, and scenarios must not invent rule identifiers. Validate the Testability gate.

### 5. Consolidate design inputs

Gather the accepted contract, persistence decisions, test scenarios, permitted paths, required outputs, and acceptance evidence for the final design handoff. Include the request/response, identity, authorization, transaction, lifecycle, observability, and resulting-state decisions needed for a later implementation. Continue through the design recipes below; do not dispatch or claim implementation execution.

### 6. Apply the FastAPI primary recipe

Use `references/fastapi-pydantic-v2.md` for greenfield or compatible services:

- application factory and async lifespan;
- capability-based routers and `Annotated` dependencies;
- the accepted backend-only or BFF boundary and frontend delivery choice;
- one infrastructure aggregate with healthcheck and deterministic disposal;
- external identity-provider integration rather than a home-grown authorization server;
- strict separation of request/response, domain, and ORM models;
- three failure layers without using `HTTPException` for normal application behavior;
- explicit serialization, validation, and OpenAPI review.

Preserve an existing framework when it satisfies the requirements. Do not rewrite Django, Flask, or Starlette merely to apply this recipe.

When a recipe choice rests on standard-library behavior for the project's Python version (lifespan and `asyncio.TaskGroup` cleanup, exception groups, `contextvars`, `http.HTTPStatus`), dispatch `python-harness:pep-talk` with the question and the Python version from `survey`. Treat its return as cited facts: open the cited lines before relying on them.

### 7. Resolve deferred work, traffic, and caching

Use `references/async-work-and-capacity.md`.

- Strongly discourage in-process queues for accepted deferred work. Present Celery, Taskiq, Dramatiq, and arq with pros and cons.
- Ask expected and peak RPS, burst shape, cost, latency, concurrency, and abuse behavior before choosing edge or application rate limiting. Use Redis-backed `fastapi-limiter` when the selected design requires FastAPI-level limits.
- Add caching only after defining freshness, invalidation, tenant isolation, failure behavior, and ownership. Use Redis with `fastapi-cache2` for the primary application-cache recipe.
- State whether database acceptance, message publication, and execution are each durable.

### 8. Establish deployment lifecycle

Define:

- proxy and trusted-header behavior;
- process and worker counts;
- connection-pool budgets across every process;
- startup/shutdown ownership for database, HTTP, broker, cache, and telemetry resources;
- deterministic `engine.dispose()`, Redis/client closure, and partial-startup cleanup;
- migration execution outside application startup;
- health, readiness, metrics, logs, traces, and suspicious-request signals;
- request correlation propagated through structured logs and response headers;
- graceful shutdown, cancellation, and outstanding-work handling.

Involve SRE input only when durable/background/multiprocess or operational design is required. Do not assume adding workers improves a blocking or database-bound workload.

### 9. Expand proven conventions

Add routes only after the first slice's contracts, errors, dependencies, transactions, tests, and lifecycle behavior are verified. Reuse the proven shape without creating a generic framework for imagined future operations.

### 10. Complete the design handoff and report

Complete the inline vertical-slice packet with the design decisions above. When the service extends existing code, dispatch `python-harness:reviewer` on the paths the slice will extend, with the accepted shared brief as the agreed contract, the slice's acceptance criteria, and the project root and Python version from `survey`; its findings feed the packet's unresolved items and nothing is edited. Call `gate` for the repository's ruff, ty and pytest checks, and run the focused domain/use-case, repository, adapter, and HTTP checks the repository provides through it; name any check the gate cannot run as a limitation. Verify the design's expected state transitions and cleanup ownership. Report design inspection and manual walkthrough separately, with literal check evidence where available.
</workflow>

<dispatch>
Each dispatch in steps 6 and 10 is one `Agent` call to one of these agents. Pass the project root and Python version from `survey` in the request; do not pass a `model`.

- agent: `python-harness:reviewer`
- model: sonnet
- effort: high
- tools: Read, Grep, Glob, Bash, `mcp__plugin_python-harness_python-harness__plan_review_surface`, `mcp__plugin_python-harness_python-harness__check_citations`, `mcp__plugin_python-harness_python-harness__survey`, `mcp__plugin_python-harness_python-harness__gate`

- agent: `python-harness:pep-talk`
- model: haiku
- tools: Read, Grep, Glob, `mcp__plugin_python-harness_python-harness__search_python_docs`, `mcp__plugin_python-harness_python-harness__read_python_docs`, `mcp__plugin_python-harness_python-harness__survey`, `mcp__plugin_python-harness_python-harness__check_citations`

If an agent type is not available, stop. The plugin's agents did not load: tell the user to check the plugin in `/plugin` (its Errors tab) or run `claude plugin validate` on it, then start a new session. Do not substitute another agent.
</dispatch>

<gates>
| Gate         | Required evidence                                                                     | Return path          |
| ------------ | ------------------------------------------------------------------------------------- | -------------------- |
| Requirements | all mandatory interview areas resolved or explicitly not applicable                   | Interview            |
| Complexity   | bounded, workflow, or distributed/durable band with reasons                           | Interview            |
| Contract     | representative requests/responses, public types, rules, errors, and caller recovery   | `enterprise-design`  |
| Identity     | issuer or mechanism, trusted claims, client type, authorization and disclosure rules  | Interview            |
| Persistence  | data model, database, transaction, concurrency, duplicate, and migration packet       | `design-persistence` |
| Async work   | sync/deferred boundary, queue choice, delivery, retries, cancellation, and durability | Interview or SRE     |
| Capacity     | RPS, bursts, latency, concurrency, limits, cache semantics, and pool budget           | Interview or SRE     |
| Testability  | scenario tests attack stable public behavior and plausible defects                    | `design-tests`       |
| Handoff      | complete permitted slice is documented with no unresolved design blocker              | Lead                 |
| Lifecycle    | startup, shutdown, migrations, resources, and graceful termination are owned          | Design lead          |

The design is complete when:

1. requirements and complexity were established before architecture;
2. contracts, persistence/data-layer decisions, and scenario tests precede implementation;
3. one authorized vertical slice is described through the application boundary;
4. unauthenticated and authenticated-but-unauthorized behavior are distinct;
5. transaction, duplicate, retry, failure, and committed-state behavior match the packets;
6. queue, rate-limit, cache, database, migration, process, and lifecycle choices follow explicit requirements;
7. no in-process work is described as durable;
8. design checks and limitations are reported from actual evidence;
9. the inline design handoff is complete and no implementation is dispatched.

Edit, Write and NotebookEdit are disallowed for this skill: it creates no project file.
</gates>

<output>
The completed vertical-slice packet in the conversation, built from the accepted shared brief, contract, persistence decisions and scenario tests, plus a chat summary:

- the service classification and the consequential decisions with their rationale;
- each gate and whether it passed;
- design inspection, manual walkthrough and the `gate` result reported separately, with literal check evidence;
- limitations and checks not run;
- unresolved items, or a statement that none block the handoff.
</output>

<handoff>
The next stage of the service track is `enterprise-design`. Pass it the accepted shared brief and the vertical-slice packet, and say which gates passed, which are open, and that no code or file was changed.
</handoff>

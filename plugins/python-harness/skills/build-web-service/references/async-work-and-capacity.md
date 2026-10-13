# Async work, traffic, rate limits, and caching

## Deferred work

Strongly discourage FastAPI `BackgroundTasks`, `asyncio.create_task()`, or an in-process
queue for accepted work. Process loss drops execution, retries, and progress unless the
work is explicitly disposable best effort.

Present durable worker options to the user:

| Option   | Strengths                                             | Costs and questions                                     |
| -------- | ----------------------------------------------------- | ------------------------------------------------------- |
| Celery   | mature ecosystem, retries, scheduling, broad brokers  | operational complexity, sync heritage, configuration    |
| Taskiq   | async-native design, typed integrations, modern shape | smaller ecosystem; verify broker and scheduler maturity |
| Dramatiq | simpler worker model, middleware, clear retries       | fewer built-in workflow features than Celery            |
| arq      | concise asyncio + Redis integration                   | Redis-specific and smaller ecosystem/feature surface    |

Ask about broker operation, delivery semantics, duplicate execution, scheduling, priority,
timeouts, cancellation, progress, dead letters, payload size, version compatibility, and
reconciliation. Do not select from fashion.

Persisted job acceptance, broker publication, and worker execution are three separate
durability claims. Use an outbox or reconciliation design when the required failure order
cannot tolerate a database/broker gap.

## Traffic and rate limits

Collect normal and peak RPS, bursts, concurrency, payload sizes, request cost, latency,
availability, and abusive-client behavior before designing limits.

Ask whether limits belong:

- at the edge/gateway for coarse global or network protection;
- in FastAPI for identity-, tenant-, resource-, or operation-specific policy;
- at both layers with non-conflicting semantics.

When FastAPI-level limiting is selected, use the project's existing library or the primary
Redis-backed `fastapi-limiter` recipe. Define keying, trusted identity, atomic counters,
window/burst semantics, response headers, fail-open/fail-closed behavior, and proxy
interaction.

## Caching

Do not add a cache without an expensive access path and explicit semantics. Ask:

- what is cached and who owns it;
- freshness and stale-read tolerance;
- invalidation trigger and race behavior;
- tenant and authorization isolation;
- stampede protection and key versioning;
- response when Redis is unavailable;
- interaction with HTTP caching and database-native optimization.

For application caching in the primary FastAPI recipe, use Redis with `fastapi-cache2`.
Prefer HTTP caching for safe public/private response semantics where it fits, but do not
assume HTTP caching solves application data reuse.

## Resource budgets

Calculate process-wide totals:

- ASGI workers x database pool size;
- web and task workers x broker/cache connections;
- outbound HTTP pools;
- thread/process executors;
- in-flight request and work limits.

More workers can amplify database exhaustion, duplicate work, and memory use. Tie scaling
to the measured bottleneck.

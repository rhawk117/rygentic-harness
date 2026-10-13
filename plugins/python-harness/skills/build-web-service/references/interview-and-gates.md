# Web-service requirements interview and gates

Ask two to four connected questions per round, then follow the answers. A complete user
specification may satisfy a round without repeating questions.

## Round 1: consumers, operations, and compatibility

Ask:

1. Who calls the service: browser, mobile app, CLI, internal service, webhook source, or
   external customer?
2. Is the application backend-only, or is it a backend for frontend (BFF)?
3. What operations exist, and which are commands, queries, streams, uploads, callbacks, or
   long-running requests?
4. Show representative accepted and rejected requests and responses.
5. Which clients, schemas, URLs, status codes, headers, or events must remain compatible?
6. What behavior already exists in another system?

If the application is a BFF, present these choices:

A. **Jinja templates + plain CSS/JavaScript:** scales poorly, but is acceptable for limited
interactivity.
B. **TypeScript + a client-side framework:** adds complexity but scales much better for
complex reactivity.
C. **TypeScript + a client-side framework + Tailwind CSS:** scales excellently, has the
most setup complexity, usually requires the least feature-level styling code, and is
easiest to work with once the toolchain is established.

Then ask:

- which browser interactions require client-side state or reactivity;
- whether FastAPI renders HTML, serves built static assets, or only fronts a separate
  frontend deployment;
- whether authentication uses same-origin cookies or bearer tokens;
- how CSRF, CORS, CSP, SameSite cookies, asset caching, frontend routing, and error
  rendering should work;
- whether frontend build, test, and deployment tooling already exists.

Gate: concrete consumers, backend-only/BFF shape, frontend choice when applicable,
operations, examples, and compatibility constraints exist.

## Round 2: complexity

Classify using the highest applicable band:

| Band                | Signals                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------- |
| bounded service     | synchronous path, few operations/effects, local state, modest traffic                       |
| workflow service    | durable state, multiple operations, integrations, retries, or deferred work                 |
| distributed/durable | queue/worker, multi-process coordination, high traffic, recovery, cross-service consistency |

Ask what makes the service more complex: authorization, state transitions, external
effects, concurrency, deferred work, availability, traffic, or deployment.

Gate: the band and its architecture-driving reasons are explicit.

## Round 3: identity and authorization

Ask:

1. Is identity browser/session, external OAuth2/OIDC, service-to-service, API key, or an
   existing custom mechanism?
2. Who issues credentials, which audience and claims are trusted, and how are keys rotated?
3. Which user, tenant, role, or client may perform each operation?
4. May one authenticated user discover that another user's resource exists?
5. Where is coarse scope/role policy enforced, and where is resource ownership checked?
6. Are cookies involved, and therefore CSRF, SameSite, CORS, and browser credential rules?

Preserve the existing identity architecture. For greenfield systems, prefer an external
OAuth2/OIDC provider rather than implementing an authorization server.

Gate: authentication and authorization are separate, with explicit trust and disclosure
boundaries.

## Round 4: persistence, database, and consistency

Ask:

1. What persists, and what identifies and owns each record?
2. Does the user require SQL or NoSQL? Which concrete database type is preferred?
3. Which reads/writes, transitions, uniqueness, history, and deletion rules matter?
4. What must commit atomically, and what may callers retry?
5. What happens on duplicate and concurrent submissions?
6. Does data already exist, and how are migrations deployed?

Invoke `design-persistence` for durable state.

Gate: a complete persistence packet exists before ORM code.

## Round 5: deferred work and external effects

Ask:

1. Which work exceeds request latency or must run independently?
2. Must accepted work survive process, host, or broker failure?
3. What retries, scheduling, priority, cancellation, progress, and dead-letter behavior are
   required?
4. Can work execute more than once?
5. What happens if a remote effect succeeds before persistence or publication fails?
6. Who operates the broker and workers?

Strongly discourage in-process queues for accepted deferred work. A durable queue does not
by itself make database acceptance and publication atomic; resolve the failure order.

Gate: sync/deferred boundaries, delivery semantics, worker topology, and durability claims
are explicit.

## Round 6: traffic, rate limits, and caching

Ask:

1. What are normal and peak RPS, burst duration, concurrent requests, and payload sizes?
2. What latency and availability targets apply by operation?
3. Which operations are expensive or abuse-sensitive?
4. Should limits be global, IP-, identity-, tenant-, resource-, or operation-scoped?
5. Does an edge/gateway already rate limit, and does the application need domain-specific
   quotas?
6. What is expensive enough to cache? What freshness, invalidation, isolation, and failure
   behavior are acceptable?

Use `fastapi-limiter` with Redis when application-level FastAPI limits are selected. Use
Redis with `fastapi-cache2` when application caching is selected.

Gate: capacity assumptions, limit ownership, and cache semantics are measurable.

## Round 7: deployment and lifecycle

Ask:

1. Where does the service run, behind which proxy, with how many processes and workers?
2. Which resources start and stop with the application?
3. What are the total database, broker, cache, and HTTP connection budgets?
4. How and when do migrations run?
5. What health, readiness, logging, metrics, tracing, and security signals are required?
6. How do shutdown and cancellation handle in-flight requests and outstanding work?

Gate: every resource and operational transition has one owner.

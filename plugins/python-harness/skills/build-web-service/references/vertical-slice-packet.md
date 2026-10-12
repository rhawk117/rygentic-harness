# Vertical-slice design handoff

Use this inline Markdown template after the requirements, contract, persistence, test, and
lifecycle gates pass. It is a design record for a later implementation phase, not an
invocation or generated artifact. Keep unresolved items explicit; do not hand off a design
that leaves caller behavior, authorization, transaction ownership, durability, or deployment
safety undecided.

## Service

- **Outcome:** `<user-visible capability>`
- **Consumers:** `<browser, service, CLI, or external caller>`
- **Shape:** `backend-only | BFF`
- **Frontend:** `not-applicable | jinja-plain | typescript-framework | typescript-framework-tailwind`
- **Browser security:** `<CSRF, CORS, CSP, cookie/token, and origin decisions>`
- **Complexity:** `bounded-service | workflow-service | distributed-durable-service`

## Requests and responses

- **Accepted request:** `<representative request>`
- **Rejected request:** `<request and reason>`
- **Accepted response:** `<status, headers, and body>`
- **Rejected response:** `<status, headers, and body>`

## Identity and authorization

- **Mechanism:** `<existing or selected mechanism>`
- **Issuer and trust:** `<trusted boundary>`
- **Authorization:** `<role, tenant, resource, and disclosure behavior>`

## Design inputs

- **Contract packet:** `<path or embedded contract design>`
- **Persistence packet:** `<path, embedded persistence design, or not applicable>`
- **Scenario-test packet:** `<path or embedded test design>`
- **Async boundary:** `synchronous | durable-queue | none`
- **Durability:** `<database, publication, and execution claims>`
- **Worker:** `<selected system or not applicable>`

## Capacity and lifecycle

- **Capacity:** `<normal RPS, peak RPS, latency, limits, and cache semantics>`
- **Startup:** `<resources and owners>`
- **Shutdown:** `<infrastructure disposal, client closure, and outstanding work>`
- **Migrations:** `<execution owner>`

## Observability

- **Logging:** `<structured format and propagated libraries>`
- **Correlation:** `<request/trace identifiers and response headers>`
- **Telemetry:** `<instrumented resources and provider shutdown>`

## Permitted paths and acceptance

- **Production paths:** `<paths the later implementation may change>`
- **Test paths:** `<paths the later implementation may change>`
- **Required outputs:**
  - `<one complete vertical slice>`
  - `<request and resulting-state evidence>`
  - `<literal check results>`
- **Acceptance criteria:**
  - `<authorized success>`
  - `<unauthenticated rejection>`
  - `<authenticated but unauthorized rejection>`
  - `<expected application and infrastructure failures>`
  - `<transaction and cleanup behavior>`
- **Unresolved:** `<none, or each blocking decision>`
- **Handoff status:** `ready | blocked`

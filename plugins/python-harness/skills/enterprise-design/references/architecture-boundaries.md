# Architecture boundaries

Choose roles from responsibility and dependency direction, not naming fashion.

| Role                         | Owns                                                                | Must not own                                                    |
| ---------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------- |
| Domain entity/value          | intrinsic invariants and valid transitions                          | database calls, HTTP calls, workflow coordination               |
| Use case/application service | one caller-visible operation, orchestration, result assembly        | vendor-specific persistence or transport details                |
| Domain service               | a stateless business decision spanning domain objects               | generic coordination or infrastructure access                   |
| Repository port              | domain-shaped load/save operations and persistence failure boundary | business workflow, transport DTOs, generic CRUD for convenience |
| Adapter                      | translating a database, API, queue, or filesystem into a port       | caller-facing business policy                                   |
| Input/output model           | immutable data crossing the use-case boundary                       | hidden dependencies or behavior requiring external state        |

## Boundary procedure

1. Start with the caller-visible use case and its input/output types.

2. Place intrinsic validation and transitions on domain values or entities.

3. Extract a domain service only when a rule needs several domain objects and
   no object naturally owns it.

4. Derive repository methods from the use case. Prefer `find_existing(ids)`
   and `add(order)` over an unbounded `execute(query)` or generic CRUD surface.

5. Put database/client exceptions behind the adapter and translate them into
   the concrete dependency error promised by the use case.

6. State transaction ownership. A repository is not automatically the
   transaction owner; use a unit-of-work boundary only when the operation
   genuinely spans an atomic commit.

7. Draw dependency direction:

   ```text
   caller -> use case -> domain types
                      -> repository port <- infrastructure adapter
   ```

## Required boundary table

| Component | Role                                                  | Public operations | Owns state/lifecycle | Depends on                | Translates failures          |
| --------- | ----------------------------------------------------- | ----------------- | -------------------- | ------------------------- | ---------------------------- |
| `<name>`  | entity/use case/domain service/repository/adapter/DTO | exact signatures  | owner and lifetime   | exact inward dependencies | source error -> public error |

Reject a design when “service” cannot be classified, a repository exposes
storage mechanics instead of domain operations, a domain type imports
infrastructure, or a use case hides dependencies in globals.

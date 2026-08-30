# Components & Architecture — Martin's Metrics and the Dependency Rule

Sources: *Agile PPP* (2002) package-design chapters, "Granularity" (1996),
"Stability" (1997), *Clean Architecture* (2017) chs. 12–14, 17–23, 26, and
the 2011–2012 blog posts. A "component" = unit of release/deployment; in
analysis practice, a top-level package/directory with a public surface.
`scripts/metrics.py` computes everything in §2 — your job is interpreting
it and doing §3–§5 by reading code.

## 1. Component cohesion — which files belong together

- **REP** (Reuse/Release Equivalence): "The granule of reuse is the granule
  of release." Shared code consumed by copy-paste/vendoring, or pinned to
  raw git SHAs with no versioning, violates it.
- **CCP** (Common Closure): "Gather into components those classes that
  change for the same reasons and at the same times" — SRP for components.
  Violation evidence: one logical change fans out across many packages
  (component-level shotgun surgery); git co-change history is the direct
  measurement when available.
- **CRP** (Common Reuse): "Don't force users of a component to depend on
  things they don't need" — ISP for components. The classic violator is the
  `utils`/`common` grab-bag where importing a string helper drags in a DB
  driver.

Tension triangle: REP and CCP make components bigger, CRP smaller. Early-
stage products legitimately favor CCP (develop-ability); mature shared
libraries favor REP/CRP. Weight findings accordingly — don't ding a young
app for imperfect reuse granularity, do ding a shared library.

## 2. Component coupling — the computable layer

- **ADP** (Acyclic Dependencies): "Allow no cycles in the component
  dependency graph." Any strongly connected component >1 node in the import
  graph is a violation; members of a cycle cannot be released, tested, or
  understood independently. Fix by DIP (invert one edge) or by extracting
  the shared piece. Function-local/deferred imports added to dodge circular
  import errors are a confession that a cycle exists.
- **SDP** (Stable Dependencies): "Depend in the direction of stability."
  Instability I = Ce / (Ca + Ce). For every edge A → B require I(A) > I(B);
  each violation means a hard-to-change thing rests on a flighty one.
- **SAP** (Stable Abstractions): stable components should be abstract.
  A = abstract types / total types. Main Sequence: the line A + I = 1.
  D = |A + I − 1|; near 0 is healthy.
  - **Zone of Pain** (I≈0, A≈0): concrete and heavily depended-on — painful
    if it is also VOLATILE (a churning `common` package). A stable schema or
    stdlib-like utility here is harmless; volatility is the qualifier.
  - **Zone of Uselessness** (I≈1, A≈1): abstractions nobody implements —
    dead speculation, delete-grade.

Granularity caveats: metrics.py counts dependencies at module level rolled
into top-level packages (use --package-depth 2 for single-package repos);
in dynamic languages A is a proxy (ABC/Protocol/interface counts) — treat A
and D as low-confidence there and lean on cycles + dependency direction,
which stay hard evidence in every language. On tiny repos (a handful of
modules) D is noise; read it only for components with real fan-in/out.

## 3. The Dependency Rule (Clean Architecture)

Circles inward: Frameworks & Drivers → Interface Adapters → Use Cases →
Entities. "Source code dependencies can only point inwards. Nothing in an
inner circle can know anything at all about something in an outer circle.
In particular, the NAME of something declared in an outer circle must not
be mentioned by the code in an inner circle."

- Entities: enterprise business rules; plain objects or data+functions.
- Use cases: application-specific rules; orchestrate entities; must not
  know the web, the DB, or the framework exist.
- Interface adapters: controllers/presenters/gateways; ALL SQL lives here
  or further out.
- Frameworks & drivers: glue. "The Web is a detail. The database is a
  detail."

Data crossing boundaries: "isolated, simple data structures" — never
Entities, never ORM rows, always in the form most convenient for the inner
circle.

## 4. Detection signatures for the judgment pass

- Domain/use-case files importing web frameworks (flask/django/express/
  spring-web/nestjs), ORMs (sqlalchemy/hibernate/prisma/ActiveRecord),
  UI toolkits, or vendor SDKs.
- Entities extending `models.Model`/`ActiveRecord::Base`, carrying
  `@Entity`/`__tablename__`/serializer annotations for a wire format.
- Use-case functions taking Request/Response objects, reading headers,
  returning framework responses, raising `Http404`/`abort(400)`.
- Raw SQL or query builders in domain modules.
- Controllers handing ORM rows straight to use cases; use cases returning
  Entities to serializers instead of DTOs.
- Construction of concrete infrastructure (`new`, DI wiring) outside
  Main/composition roots — "think of Main as a plugin to the application";
  Main is the dirtiest, most unstable component, and that is correct
  (I=1.0 for main is healthy, not a finding).
- **Screaming Architecture test**: do top-level directories scream the
  domain (billing/, claims/, onboarding/) or the framework (controllers/,
  models/, views/, or Spring's controller/service/repository)?
  "Architectures are not (or should not be) about frameworks."
- **Testability probe**: "you should be able to unit-test all those use
  cases without any of the frameworks in place." Do the use-case tests
  spin up an app/test-client or hit a real DB? That is the measurement.
- Humble Object check: at real boundaries you find a dumb, hard-to-test
  half (View, device, gateway impl) and a testable half (Presenter).
  Logic accumulating in the humble half (fat views, logic in templates,
  business rules in controllers) is the violation.

## 5. Boundary economics

Boundaries cost; Martin allows partial boundaries (facades, one-way
interfaces) where a full one isn't yet justified. So: absence of a
formal layer in a 500-line CLI tool is NOT a finding; business logic
fused to I/O in a system with multiple delivery mechanisms IS. Judge
the boundary against the system's actual size and change pressure —
and remember Needless Complexity cuts the other way: interface-per-class
ceremony with single implementations and no seams earns its own finding.

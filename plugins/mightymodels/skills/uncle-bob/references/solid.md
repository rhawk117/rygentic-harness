# SOLID — Rules, Detection Signatures, False Positives

Primary sources: Martin's principle papers (1996–2002), *Agile Software
Development: PPP* (2002), the PrinciplesOfOod page, his 2014 principle blog
posts, *Clean Architecture* (2017) chs. 7–11, and "Solid Relevance" (2020).
Every finding you report should cite the principle by name and, where useful,
the formulation ("Clean Architecture ch. 7" / "SRP paper, 2002").

Martin's own framing: these principles are about **dependency management**.
Badly managed dependencies produce his design smells — use these words in
findings, they are his diagnostic vocabulary:

- **Rigidity** — every change forces many other changes.
- **Fragility** — changes break conceptually unrelated parts.
- **Immobility** — parts cannot be disentangled for reuse.
- **Viscosity** — doing things right is harder than doing things wrong.
- **Needless Complexity** — infrastructure with no direct benefit (speculation).
- **Needless Repetition** — repeating structures that want a single abstraction.
- **Opacity** — code that does not express its intent.

Critical counterweight (his, not a critic's): a principle is applied when a
smell is PRESENT. Applying SOLID preventively against imagined change is
itself Needless Complexity. An abstraction with exactly one implementation
and no test seam or plausible second implementation is a finding *against*
the code, not for it.

## SRP — Single Responsibility Principle

Formulations, in order of refinement: "A class should have only one reason to
change" (2002) → "Gather together the things that change for the same
reasons. Separate those things that change for different reasons" (2014) →
"A module should be responsible to one, and only one, actor" (2017).

His explicit warning: SRP does NOT mean "a module does one thing" — that is a
function-level rule. SRP counts *actors* (distinct sources of change
requests: finance vs operations vs DBAs), not features.

Detect:
- One class/module mixing two or more of: domain computation, persistence
  (SQL/ORM/file I/O), presentation (HTML/JSON layout, formatting), transport
  (HTTP/sockets), logging/config policy. His canonical negative example:
  `Employee.calculatePay() + reportHours() + save()`.
- Imports spanning layers in one file (domain types + web framework + DB
  driver together).
- God classes named `Manager`, `Processor`, `Utils`, `Helper` aggregating
  verbs that serve different departments.
- Git evidence when available: one file changed in commits driven by
  unrelated requirement sources; recurring merge conflicts in one class.

Not a violation:
- A DTO/dataclass with many fields and no behavior — no divergent actors.
- Several steps serving the SAME actor in one module.
- Responsibilities that never change independently. His modem example:
  if dial/hangup and send/recv never change at different times, separating
  them "would smell of Needless Complexity." "An axis of change is an axis
  of change only if the changes actually occur."
- A facade that delegates to per-responsibility classes — that is his remedy.

## OCP — Open-Closed Principle

"Software entities should be open for extension, but closed for modification"
(after Meyer). 2014 plugin framing: extend the system without modifying it;
dependencies point from plugins toward the system, never outward. Component
form (2017): "If component A should be protected from changes in component B,
then B should depend on A."

Detect:
- The same type-tag switch/if-elif chain (on an enum, string kind,
  isinstance) repeated in 2+ places — adding a variant means editing every
  site. This is the load-bearing OCP signature and also smell G5/G23.
- Adding one variant historically required edits across N files (visible in
  parallel case arms across modules).
- Public mutable fields / module-level mutable globals — nothing is closed
  when any module can reach in.
- Core business modules edited every time a peripheral feature landed.

Not a violation:
- ONE switch, appearing once, creating polymorphic objects, hidden behind an
  abstraction — Martin's own factory exception (Clean Code ch. 3).
- Not being closed against every conceivable change: "No significant program
  can be 100% closed." Closure is strategic, chosen per likely change axis.
- Speculative extension points for changes that never occur — that is
  Needless Complexity, the opposite finding.

## LSP — Liskov Substitution Principle

"Functions that use references to base classes must be able to use objects of
derived classes without knowing it" (1996). 2020 restatement: "A program that
uses an interface must not be confused by an implementation of that
interface" — it is about subtyping generally (duck types, protocols, REST
implementations), not inheritance syntax. Contract rule (via Meyer): an
override may only *weaken* preconditions and *strengthen* postconditions.

Detect:
- Overrides that throw NotImplementedError/UnsupportedOperation or silently
  no-op ("degenerate functions in derivatives").
- Overrides that add validation the base does not have (strengthened
  precondition) or return null/partial state where the base guarantees more
  (weakened postcondition).
- Client code holding an abstraction but branching on concrete type
  (isinstance/instanceof chains, per-provider special cases, config tables
  of implementation quirks). His architecture example: the aggregator that
  checks `dispatchUri.startsWith("acme.com")`.
- Overrides with side effects the base contract does not imply (Square's
  setWidth mutating height).
- Subtypes raising exception types the base never raises.

Not a violation:
- Implementation-reuse inheritance with no polymorphic clients — the smell is
  latent until a client can be confused.
- Subtypes extending behavior: new methods, wider inputs, stronger
  guarantees are explicitly allowed.
- isinstance in a factory/serializer that does not dispatch divergent
  business behavior on an abstraction the code holds polymorphically.

## ISP — Interface Segregation Principle

"Clients should not be forced to depend upon interfaces that they do not use"
(1996). 2017 generalization: "it is harmful to depend on modules that contain
more than you need."

Detect:
- Interfaces/ABCs/protocols whose methods partition into groups used by
  disjoint client sets (cluster the call sites; >1 cohesive cluster = fat).
- Implementations forced to stub members: empty bodies, `pass`,
  `return null`, NotImplementedError for methods their clients never call
  (doubles as an LSP alarm).
- Base classes carrying hooks only one derivative uses (his TimedDoor/
  TimerClient pollution example).
- Barrel/`__init__` modules re-exporting everything so every consumer
  depends on everything.

Not a violation:
- A large interface whose methods are cohesive and used together by the same
  clients — ISP segregates by client, not by method count.
- A class implementing several small interfaces — that is the cure.
- Default methods that don't force implementers into lies.

## DIP — Dependency Inversion Principle

"A. High-level modules should not depend upon low-level modules. Both should
depend upon abstractions. B. Abstractions should not depend upon details.
Details should depend upon abstractions" (1996). Clean Architecture practice
list: don't refer to volatile concrete classes; don't derive from them; don't
override concrete functions; concrete wiring lives in Main/factories.

Detect:
- Domain/use-case modules importing concrete infrastructure by name: DB
  drivers, ORMs, HTTP clients, SDK classes, filesystem APIs inside policy
  code.
- `new`/direct construction of repositories, clients, mailers inside
  business logic instead of receiving an abstraction (constructor injection
  or factory).
- Abstractions owned by the low-level side (interface lives next to the DB
  implementation, not next to the policy that consumes it).
- Business rules inheriting framework base classes or annotated to the
  framework throughout (framework as master, not plugin).
- Hard-coded environment details (connection strings, endpoints, paths)
  inside policy code.

Not a violation:
- Depending on STABLE concretions: stdlib types, language runtime,
  `String`/`Path`/`Decimal`. Wrapping the stdlib in interfaces to satisfy
  DIP is Needless Complexity. Volatility is the trigger, not concreteness.
- Main/composition roots and factories being concrete — someone must build
  the object graph; the violation is construction *inside policy*.
- In dynamic languages a passed-in function or Protocol satisfies DIP —
  the abstraction need not be a keyword `interface`. Judge by dependency
  direction of imports, which stays checkable in any language.

## Beyond class-based OO

Martin, repeatedly and in writing: the word "class" does not scope these
principles. "A class is simply a coupled grouping of functions and data.
Every software system has such groupings" (2017). "The principles of software
design still apply, regardless of your programming style" (2014). Apply SRP
to modules/namespaces, OCP/DIP via higher-order functions and protocols,
LSP to any contract implementation, ISP to any required function-bundle.
Do not skip SOLID analysis because a codebase is functional or procedural;
judge by module boundaries and import direction.

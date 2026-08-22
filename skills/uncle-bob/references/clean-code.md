# Clean Code — Rules, Thresholds, and the Complete Smells Catalog

Source: *Clean Code* (2008). The ch. 17 catalog at the bottom is the finding
vocabulary: cite findings by ID (G23, F3, N7...) so reports are precise and
auditable. Framing rules that govern everything: code is read >10:1 over
written — optimize for the reader; and the Boy Scout Rule — "always check a
module in cleaner than when you checked it out."

Contents: 1. Names · 2. Functions · 3. Comments · 4. Formatting ·
5. Objects/Data · 6. Error handling · 7. Boundaries · 8. Tests · 9. Classes ·
10. Numeric thresholds · 11. Full smells catalog (C/E/F/G/N/T).

## 1. Meaningful Names (ch 2)

Intention-revealing ("if a name requires a comment, the name does not reveal
its intent"); no disinformation (`accountList` that isn't a List); meaningful
distinctions — no noise words (`ProductInfo`/`ProductData` vs `Product`), no
number series (`a1, a2`); pronounceable (`generationTimestamp`, not
`genymdhms`); searchable (name length scales with scope size); no encodings
(no Hungarian, no `m_`, no `IShapeFactory` — leave interfaces unadorned);
class names = nouns (never `Manager`/`Processor`/`Data`/`Info` if avoidable);
method names = verbs; one word per concept (not fetch+retrieve+get for the
same idea); no puns (add meaning arithmetic vs add-to-collection); solution-
domain names for programmer-facing concepts; context by enclosure
(`Address.street`), never gratuitous prefixes.

## 2. Functions (ch 3)

Small — "hardly ever be 20 lines long"; his ideal runs 2–4 lines. Blocks
inside if/else/while: one line (a named call). Indent depth ≤ 1–2. Do ONE
thing (test: can you extract another function whose name is not a restatement
of the implementation?). One level of abstraction per function; stepdown rule
(file reads high-level → detail, callers above callees). Switch statements:
tolerated only once per selection type, creating polymorphic objects, hidden
behind an abstraction (factory). Arguments: 0 best, 1–2 fine, 3 needs
special justification, more "shouldn't be used anyway"; no flag/boolean
arguments (they announce the function does 2+ things — split it); cluster
related args into objects (`Point`, not x+y). No side effects (no hidden
state changes behind an innocent name — `checkPassword` initializing a
session is his example of a lie); no output arguments (mutate the owning
object instead). Command-query separation: do something or answer something,
never both. Exceptions over error codes; extract try/catch bodies into named
functions; error handling is "one thing." DRY — "duplication may be the root
of all evil in software." Multiple returns are fine in small functions.

## 3. Comments (ch 4)

Doctrine: "comments are always failures" to express intent in code; "don't
comment bad code — rewrite it"; truth lives only in the code. Acceptable:
legal headers, informative (regex format), intent, clarification of
unchangeable library calls, warnings of consequences, TODO (groomed), public
API docs. Bad: redundant restatements, misleading, mandated-everywhere doc
comments, journal/changelog comments, noise (`/** default constructor */`),
position banners, closing-brace comments, attributions, HTML in comments,
nonlocal system facts in a local comment — and above all C5: commented-out
code, which is to be deleted on sight (VCS remembers).

## 4. Formatting (ch 5)

Small files preferred: typically ~200 lines, upper limit ~500 (FitNesse
averaged ~65). Newspaper metaphor: name = headline, high concepts on top,
detail descending. Blank lines between concepts; related lines vertically
dense; variables declared near first use; instance variables at class top;
caller above callee. Lines ≤ 120 chars, never scroll right. No aligned
declaration columns. One team style, applied by everyone — the codebase
should read as one author (inconsistency is G11).

## 5. Objects and Data Structures (ch 6)

Objects hide data, expose behavior; data structures expose data, no behavior.
Both are legitimate — hybrids (public-ish state + business methods) are "the
worst of both worlds." DTOs and Active Records are data structures: business
rules do NOT go in them. Law of Demeter: a method talks to its own class,
its parameters, objects it creates, and its instance variables — no train
wrecks (`a.getB().getC().doThing()`, G36); tell the object to do the thing
rather than fetching internals. Pure data-structure field navigation is
exempt.

## 6. Error Handling (ch 7)

Exceptions, not return codes. Unchecked exceptions (checked ones cascade
signature changes — an OCP violation). Every exception carries context:
operation attempted + failure type. Define exception classes by how callers
catch them; wrap third-party APIs so one type serves a region. Special
Case / Null Object pattern instead of branch-on-exception. DON'T return
null (foists checks on every caller — return empty collections or special
cases, or throw). DON'T pass null. Swallowed exceptions (`except: pass`)
are the worst form of return-code thinking.

## 7. Boundaries (ch 8)

Wrap third-party APIs behind your own interface: don't pass `Map`/vendor
types around the system; changes get absorbed at one seam. Write learning
tests against third-party behavior. For code that doesn't exist yet, define
the interface you wish you had and adapt to it later.

## 8. Unit Tests (ch 9)

Three Laws of TDD: no production code without a failing test; no more test
than suffices to fail; no more production code than suffices to pass. Test
code is as important as production code — dirty tests are "worse than no
tests" because they rot and get discarded, and with them goes the safety
that makes refactoring possible. F.I.R.S.T.: Fast, Independent, Repeatable,
Self-validating, Timely. Minimize asserts per test; ONE concept per test.
Coverage stance ("Testing Like the TSA", 2017): 100% is an asymptotic goal —
the number should always rise; test LOC roughly 1:1 with production. A
codebase with no tests at all is, in Martin's frame, unprofessional — "you
ought to know that it works. The only way to know this is to test it."

## 9. Classes (ch 10)

Small, measured in RESPONSIBILITIES, not lines. Name test: describable in
~25 words without "if, and, or, but"; weasel names (`Processor`, `Manager`,
`Super`) confess aggregation. Cohesion: few instance variables, each method
touching most of them; when a subset of methods shares a subset of variables,
a class is trying to get out — split it. Organize for change (OCP) and
isolate from change (DIP — depend on interfaces, stub them in tests).

## 10. Numeric thresholds (pure-mode defaults)

| Measure | Bob's line |
|---|---|
| Function length | flag > 20 LOC; ideal 2–4 |
| Block inside if/while | 1 line |
| Function nesting | ≤ 2 levels |
| Arguments | 0–2 ok; 3 justify; >3 violation |
| Flag/selector args | 0 (F3/G15) |
| File length | target ≤ 200, flag > 500 |
| Line width | ≤ 120 chars |
| Switches per selection type | 1, in a factory |
| Class size | 1 reason to change; ~25-word description |
| Asserts per test | minimize; 1 concept per test |
| Test:code LOC | ~1:1 aspiration; 0 tests = top-severity finding |

`scripts/metrics.py` computes the mechanical rows; you judge the rest.

## 11. Smells and Heuristics — full catalog (ch 17)

Comments — C1 inappropriate info (metadata belongs in VCS/trackers);
C2 obsolete comment; C3 redundant comment; C4 poorly written comment;
C5 commented-out code (delete on sight).

Environment — E1 build requires more than one step; E2 tests require more
than one step (one command each).

Functions — F1 too many arguments (>3 "avoided with prejudice"); F2 output
arguments; F3 flag arguments; F4 dead function (delete, VCS remembers).

General —
G1 multiple languages in one source file;
G2 obvious behavior unimplemented (least surprise);
G3 incorrect behavior at the boundaries (untested edge cases);
G4 overridden safeties (suppressed warnings, ignored failing tests);
G5 duplication — missed abstraction (copy-paste; repeated switch chains;
similar algorithms);
G6 code at wrong level of abstraction (low-level detail in high-level
container);
G7 base classes depending on their derivatives;
G8 too much information (wide interfaces; expose little);
G9 dead code (unreachable branches, never-thrown catches);
G10 vertical separation (definitions far from use);
G11 inconsistency (same thing done different ways);
G12 clutter (empty constructors, unused variables);
G13 artificial coupling (general utilities living inside specific classes);
G14 feature envy (method manipulating another object's getters/setters);
G15 selector arguments (booleans/enums selecting behavior);
G16 obscured intent (run-ons, Hungarian, magic numbers);
G17 misplaced responsibility (code where nobody would look for it);
G18 inappropriate static (methods that might ever need polymorphism);
G19 use explanatory variables;
G20 function names should say what they do (`date.add(5)` — days? weeks?);
G21 understand the algorithm (tweaked-until-passing code);
G22 make logical dependencies physical;
G23 prefer polymorphism to if/else and switch/case (ONE SWITCH rule);
G24 follow standard conventions;
G25 replace magic numbers with named constants;
G26 be precise (floats for money, unchecked casts, ignored locking);
G27 structure over convention;
G28 encapsulate conditionals (`shouldBeDeleted(timer)`);
G29 avoid negative conditionals;
G30 functions should do one thing;
G31 hidden temporal couplings (order-dependent calls with no structure);
G32 don't be arbitrary (structure must communicate a reason);
G33 encapsulate boundary conditions (`level + 1` scattered);
G34 functions descend one level of abstraction;
G35 keep configurable data at high levels (buried defaults);
G36 avoid transitive navigation (Demeter, shy code).

Names — N1 choose descriptive names; N2 names at the appropriate level of
abstraction; N3 standard nomenclature where possible; N4 unambiguous names;
N5 long names for long scopes; N6 avoid encodings; N7 names describe
side effects (`createOrReturnOos`, not `getOos`).

Tests — T1 insufficient tests (anything that could break, untested);
T2 use a coverage tool; T3 don't skip trivial tests; T4 an ignored test is
a question about ambiguity; T5 test boundary conditions; T6 exhaustively
test near bugs; T7 patterns of failure are revealing; T8 coverage patterns
are revealing; T9 tests must be fast.

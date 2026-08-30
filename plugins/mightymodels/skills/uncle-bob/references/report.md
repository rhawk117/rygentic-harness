# Report Template, Grading Rubric, and Severity Model

The report is the deliverable. Its authority comes from three properties:
every finding cites a specific principle by name/ID, every finding points at
file:line evidence you actually read, and the grade follows the rubric below
rather than vibes. A finding without evidence is not a finding.

## Severity model

- **Blocker** — endangers the system's ability to change safely:
  dependency cycles among core components (ADP); no tests at all on a
  nontrivial codebase (T1 + Martin's professionalism stance); a god
  class/module that most of the system routes through (SRP at scale);
  overridden safeties (G4); pervasive swallowed exceptions.
- **High** — violations with blast radius beyond their file: repeated
  type-switches across modules (OCP/G5/G23); domain importing
  infrastructure (DIP/Dependency Rule); entities bound to ORM/wire formats;
  null-return conventions (ch 7); LSP breaks clients special-case;
  functions grossly past limits (>60 LOC, >5 params); fat interfaces
  forcing stubs (ISP).
- **Medium** — catalog violations with local blast radius: functions
  21–60 LOC; flag arguments (F3); magic numbers (G25); commented-out code
  (C5); Demeter trains (G36); feature envy (G14); naming smells (N1–N7);
  duplicated snippets (G5, local); misplaced responsibility (G17).
- **Low** — polish: long lines, vertical-separation issues (G10), noise
  comments (C3), minor inconsistency (G11), clutter (G12).

Findings that would be Blocker/High on correctness grounds (a swallowed
exception hiding data loss) stay Blocker/High in every mode. Severity is
about blast radius, not about how much of the book a line violates.

## Modes

**Pure (default).** The book as written. Thresholds from
clean-code.md §10 apply exactly: a 25-line function is a finding, a
redundant comment is a failure, a switch outside a factory is G23, absent
tests are graded as Martin grades them. No softening language. (Still not a
caricature: the false-positive lists in solid.md apply in every mode —
Needless Complexity, the factory-switch allowance, and stable-concretion
DIP exemptions are HIS rules, not concessions.)

**Calibrated (only when the user asks for it).** Same analysis, two changes:
1. Findings whose only basis is contested doctrine are tagged `[contested]`
   and capped at Medium. Contested list: function-length findings in the
   20–40 LOC band; comments-are-failures applied to accurate, informative
   comments; polymorphism-over-switch where the switch is single-site and
   readable; test-order/TDD-process findings (tests existing but not
   test-first). Egregious cases (150-line functions, misleading comments)
   are consensus, not contested.
2. Append a short **Contested doctrine** section: Ousterhout (APoSD, 2025
   debate) argues tiny functions create shallow, entangled interfaces and
   that comments are a design tool; Muratori showed the polymorphism
   preference costs 1.5–25x in hot paths; Martin himself concedes
   over-decomposition is possible and offers the rules "for consideration,"
   not as law. Two or three sentences, then move on.

## Letter grades

Per category, from the findings in that category:

- **A** — no High/Blocker; at most scattered Medium/Low. The doctrine holds.
- **B** — no Blockers; isolated Highs or a consistent Medium pattern.
- **C** — a Blocker exists, or Highs form a pattern (the violation is a
  convention, not an accident).
- **D** — Blockers plus patterned Highs; the category is systematically
  ignored.
- **F** — the category's core protection is absent (no tests; cyclic core;
  business logic inseparable from I/O throughout).

Plus/minus is allowed. "Pattern" means three-plus independent instances or
any instance the codebase's structure forces on future code.

Overall grade = weighted mean on a 4-point scale (A=4 … F=0):
Tests ×2, Classes & SOLID ×2, Components & Architecture ×2,
Functions ×1.5, Error Handling ×1.5, Simplicity & Duplication ×1.5,
Names ×1, Comments ×0.5. Bands: ≥3.7 A, ≥3.0 B, ≥2.0 C, ≥1.0 D, else F
(use +/- near band edges).

Hard cap, Martin's economics ("the only way to go fast is to go well"):
a nontrivial codebase with zero tests caps the overall grade at **D** in
pure mode, **C** in calibrated mode, whatever the other categories earn.

## Categories

1. Names (ch 2; N1–N7)
2. Functions (ch 3; F1–F4, G15, G28–G30, G34)
3. Comments (ch 4; C1–C5)
4. Error Handling (ch 7; G4 where safety-related)
5. Tests (ch 9; T1–T9)
6. Classes & SOLID (ch 10; SRP/OCP/LSP/ISP/DIP)
7. Components & Architecture (ADP/SDP/SAP, Dependency Rule, screaming test)
8. Simplicity & Duplication (G5, G6, G8, G9, G12; Needless Complexity —
   over-abstraction lands HERE, as a finding, not as a virtue)

## Report structure

Write `UNCLE-BOB-REPORT.md` to the active ticket's
`.mightymodels/<task-slug>/review/` directory when one exists, else at the
repo root (or where the user says). ALWAYS use this template:

```markdown
# Uncle Bob Code Quality Report — <repo name>

Mode: <pure|calibrated> · Date · <N> files / <LOC> LOC analyzed
(<languages>) · <files read in full> read closely, <n> sampled

## Grade: <letter>

<One-paragraph verdict in plain prose: the two or three structural facts
that determine the grade, and the single most valuable repair.>

## Category grades

| Category | Grade | Determining evidence |
|---|---|---|
(all eight categories, one line of evidence each)

## The numbers

<Key rows from metrics.py: LOC, test ratio, cycles, worst-function table,
package Ca/Ce/I/A/D table. Numbers only — interpretation goes in findings.>

## Findings

### Blocker
- **[ADP] <title>** — `path/file.py:12`
  <1–3 line evidence quote or precise description>
  <Why it violates, citing the principle. What Martin prescribes as the fix.>
(repeat per finding; then ### High, ### Medium, ### Low)

## What holds up

<Honest positives with the same evidence discipline. If the codebase is
clean, this section is the report and the grade says so — a reviewer who
can only find fault has stopped measuring.>

## Repair sequence

<Five steps max, ordered by leverage — Boy Scout entry points, each tied
to findings above. First step should be the grade's binding constraint.>

## Coverage and method

<What was read vs sampled, what the script measured vs what was judged,
confidence caveats (JS function metrics approximate, A/D low-confidence in
dynamic languages, etc.).>
```

Volume discipline: detail at most ~25 findings (the highest-severity,
highest-leverage ones); roll the rest into counts by catalog ID inside the
relevant sections ("+ 14 further G25 instances across 6 files"). A report
nobody finishes reading fixes nothing.

Tone: neutral professional. Cite Martin, don't impersonate him. Quote him
only when the quote earns its place (one per section at most). No mockery
of the authors — the report criticizes code, not people.

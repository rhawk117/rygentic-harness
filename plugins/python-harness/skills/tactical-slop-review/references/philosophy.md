# expert's design philosophy: what the guide does not say

Read this with `review-guide.md` before judging anything. The guide is the review criteria; this file adds the principles expert applies on top of it and the decisions that override parts of it. When the two disagree, this file wins, because every override below is a decision expert made after the guide was written.

## Overrides of the guide

| Topic | Guide says | expert's decision |
| --- | --- | --- |
| Comments | not covered | No inline comments at all. A comment that explains behavior means the code failed to carry the meaning and must be restructured until names and shape do. Lint suppressions are the one exception and must carry a reason after the code. |
| Docstrings | §6 asks for a `Raises` section | Only a module docstring. Function and class docstrings are acceptable only where a framework consumes them as metadata: FastAPI route handlers (OpenAPI description), MCP tool functions (tool description), CLI framework help text. This applies to libraries too. |
| Failure documentation | §6 documents exceptions in `Raises` | Failure contracts are carried by types: one named exception class per failure, the return annotation when an error is returned, `NoReturn`/`Never` when a function never returns normally. |
| `match` | not covered | A smell almost everywhere, including where structural matching looks tempting: it does not honor an exception hierarchy the way `except` does. |
| Data containers | Pydantic at boundaries, dataclasses inside | Layered by role, judged against what the project already depends on: Pydantic for validated boundary input, msgspec for wire formats and serialization, `@dataclass(frozen=True, slots=True)` for dependency holders and internal values. |

## The review spine: make the bug unwritable

The strongest finding is one where the structure allows a class of bugs that a different structure would make impossible to express. expert's main lever is type cardinality: a type whose state space is wider than the domain admits illegal states, and every illegal state is a bug waiting for a caller. Two booleans whose combination is invalid, an optional field that is required in one mode, a status carried as a string compared against literals: each multiplies the states the code must defend against and the states a test suite must cover. The test space is the cardinality, so an oversized type can never be meaningfully tested.

When a module handles errors verbosely (checks, guards, `if x is None` ladders, runtime "must call open() first" errors) that the design could have prevented, the finding is the design, not the missing check. Recommend the shape that removes the state: a union of small types, an enum, a type returned only by the operation that establishes the invariant, a context manager that is the only way to obtain the resource.

## Complexity budget

Over-engineering means misallocated complexity: rigor spent on clever mechanics and micro-optimizations while the design is not airtight at the type and structure level. Rigor spent making illegal states unrepresentable is always worth it. Call out a micro-optimization or a clever compression every time it appears next to a design that still admits bad states.

Measure code in semantic units (distinct things that can independently be wrong), not lines. A terse line is not better: a crammed comprehension can look covered while most of what it does is never exercised. Prefer independent, readable expressions over dense one-liners.

The best abstractions are boring and foundational: small, reused, valuable for the guarantee they buy. Leverage is local; the right abstraction at one point beats a sweeping framework. Do not abstract when the goal does not need one. The deciding questions for any abstraction are coupling ("what does it cost me to change this later?") and testing ("does this give me a seam?"), not readability for its own sake.

## Lint limits are tripwires

expert's ruff limits (4 arguments, 3 positional, 6 branches, 20 statements, 8 locals, nesting 2, 2 statements in a `try`, 8 public methods) are signals of latent decomposition, not size caps. When one trips, the function usually holds a cohesive subset of its dependencies that wants to be its own small, independently testable unit, or several parameters that belong in an options object. A finding names that subset. Never recommend a `noqa` for these.

## Exceptions

- A good hierarchy makes clean handling fall out naturally. Errors live on the application's own hierarchy, never on invented generic category bases like `NotFoundError`.
- One exception class per failure, with the message built in `__init__` from typed fields. Error-code enums passed to a generic exception are a smell.
- More than two `except` blocks are usually the same behavior in disguise (re-raise, or tweak a returned value): duplication pretending to be dispatch. When the branches resolve to a value, extract a standalone, testable `error_handler` function that walks the exception chain, keeping the `try` thin. When a condition is unrecoverable, raise at the call site instead of routing it through a value-deriving handler.
- Raise as close to the call site as possible and always `raise NewError(...) from error` when translating. Tracebacks hold every frame and its locals, so lingering traceback artifacts can grow memory without bound.

## Classes, functions and visibility

- expert's style is procedurally object-oriented: frozen, public, immutable classes, Protocols and dataclasses define the domain and the seams; behavior flows through functions that take those values and produce new ones; dependencies are prepared at the edge and injected; side effects are pushed outward.
- Three kinds of class, built by different instincts: data classes (sparse methods and properties), logic or policy classes (a few constants plus methods enforcing an invariant), orchestration layers (coordinate logic through injected dependencies). Bad OO is coupling in the wrong places, not the presence of classes.
- Visibility defaults to public. Public plus immutable is the baseline value type because it forces the caller to prepare and inject dependencies. Private needs a specific reason: bypassing it would break an invariant.
- A free module-level factory beats a classmethod (it hides the concrete type from the consumer); `@staticmethod` bolts behavior onto a class that did not need to own it.
- A long `__post_init__` is acceptable only on a very small domain type; a constructor with side effects cannot be tested.
- Operator overloading passes only when a reader who does not know the operand types guesses the behavior correctly from the symbol and no clearer named method is displaced. pathlib's `/` fails this test (prefer `Path.joinpath`).

## Push decisions to the edge

Decisions belong in the layer that has the information to make them. Configuration is parsed at the entry boundary and passed inward as typed values. Opacity is earned per case: hide something only when hiding it buys a guarantee.

## Library mode and application mode

The skill infers the mode from `survey` and the user can override it.

- Library code is written for strangers who do not share expert's opinions: deliberately defensive, readable, with a narrow, sealed public surface (one entry point to import, configuration through builders or options with safe defaults and named presets, entry functions of about two arguments). Breadth of public surface is a finding here.
- Application code is boring and conventional by design, because the reader shares the author's priors. Do not demand a sealed surface or defensive validation inside the application; demand conventional structure and explicit dependencies.

## The maintenance-cost verdict

For every module with at least one finding, answer three questions in plain words, grounded in the cited facts:

1. **Cost of change.** What does it cost to change this module later: how many callers, how much hidden coupling, how many places repeat the same knowledge?
2. **Testability.** How easy is it to test: are dependencies injected or constructed inside, is there a seam, do the tests reach behavior or private steps?
3. **Prevention or handling.** Does the design prevent a class of errors by construction, or does it handle verbosely, at runtime, errors that structure alone could have prevented?

---
paths:
  - '**/*.py'
  - '**/*.pyi'
  - '**/pyproject.toml'
---

# Python

Ruff and ty enforce every mechanical rule. This file holds the judgment a linter cannot see.
Apply the reason behind each rule, not its surface shape.

## Workflow

- `uv` only: `uv init` to scaffold, `uv add`, `uv run python`. Never bare `python`, `python3` or `pip`.
- Use the project's ruff and ty config when it has one and never weaken it.
- Target the project's `requires-python`, default 3.14. Check current stdlib docs instead of trusting memory.
- When a requirement is missing, ask instead of guessing. When a pattern has no clean equivalent, say so.
- When editing existing code, keep its names and patterns. More code for the same result is never acceptable.
- No em dashes anywhere, including strings and docs.
- Never directly edit project dependencies; use `uv` to manage them.

## Design spine

- Make illegal states unrepresentable: narrow types, enums and frozen values so wrong code fails to typecheck. Spend rigor there, never on micro-optimizations.
- Count semantic units (things that can independently be wrong), not lines. Separate readable expressions beat dense one-liners and nested comprehensions.
- Abstract only when it buys a guarantee or a testing seam. Ask what the abstraction costs to change later.
- Procedural OO: frozen public data and policy types define the domain, module-level functions move values through it, dependencies are built at the edge and injected, side effects are pushed outward.
- Push each decision to the layer that holds the information it needs.
- Never hand-roll what an existing package, standard library module, or custom code base helper owns (pathlib, textwrap, contextlib, Pydantic/msgspec validation). Never override defaults without a demonstrated issue.

## Classes and values

- Three kinds of class:
  - Data: `@dataclass(slots=True, kw_only=True, frozen=True)` or `class Name(msgspec.Struct, frozen=True, kw_only=True)` public fields, a few properties.
  - Policy: constants plus methods enforcing one invariant. A check returns the violation (an error or `None`); the call site raises. Policies are classes which accept the inputs they are testing.
  - Orchestration: a frozen dataclass holding injected dependencies (use cases, services, unit of work).
- A method belongs on a class only if it reads that instance's fields; otherwise it is a module-level function. No `@staticmethod`. Prefer a module-level factory function over `@classmethod`.
- No hand-written `__init__` except for exception classes (see Errors) and genuinely abstract concepts; for abstract concepts always use `__slots__` to have a fixed set of members.
- Avoid `__post_init__` and use functional helpers to validate outside of the class that is testable in isolation and NEVER use `object.__setattr__` to mutate a frozen dataclass.
- No `ClassVar` on dataclasses.
- Public by default; immutability over private class members. Hide something only when a caller could misuse it and a public entry point guards it.
- No private classes. Use a frozen container plus a public function, or Protocol plus implementation plus a factory returning the Protocol.
- Protocol over ABC. Keep Protocols minimal; only resource-owning implementations are context managers and always use `@runtime_checkable` to catch interface drift early.
- Pydantic at validation boundaries, msgspec for serialization and hot internal state (frozen where possible)
- Values with different lifetimes live in different objects. Group state by concern, never one god object.
- Related constants become a StrEnum, or IntEnum when ordering means something, with `auto()` values and behavior as properties.
- Tunables live in a frozen options dataclass with defaults and derived properties, injected via `field(default_factory=...)` or `X | None` falling back to `X()`.
- When several parameters thread through helpers, collapse them into an options object.
- Lookup tables are dicts keyed by an ID enum, owned by a class with a clear lifecycle. No lambdas in them, no `partial` everywhere, no enums carrying data. A callable object is a class with `__call__`.
- No module-level mutable reference types, import-time I/O, constructors doing real work, generic setters, leaked mutable objects, or `del`.
- Overload an operator only when a reader who does not know the operand types would guess its behavior.
  - Example: `Path.joinpath()` instead of `/` ask yourself how it would read as an assignment `path /= other` **makes no sense** so it fails the test.

## Typing

- Declare long, repeated or constrained types once as PEP 695 `type` aliases. Never write `Annotated[...]` inline in a field or parameter, use a variable as an alias
- No `from __future__ import annotations`. `object` instead of `Any`.
- Annotate contextmanager functions as `Generator[...]`.
- Project-local msgspec or Pydantic base classes go in ruff's `runtime-evaluated-base-classes`.
- Inheritance is almost always the wrong abstraction, prefer composition and interfaces instead so behavior isn't implicitly coupled to a base class.
- For complicated types, use the `type Alias[T] = ...` to reduce output tokens, change propagation and readability.

## Control flow

- The walrus operator is welcome where it removes a repeated call and reduces output tokens
- Pipelines: a generator that selects items plus a function that maps one item, composed with `map`.
- Avoid `match`; it does not honor exception hierarchies and rarely beats guards or a dict dispatch.
- Hardly ever should `else` exist in any form aside from one line ternary expressions; restructure with guards or extraction.
- Use guard clauses, early returns, inverted conditions, extraction to prevent deep nesting.
- Nesting depth of at most 3 blocks, top-of-function guards excluded. Deeper means the function is several functions.
- Loops have one exit: no `return` inside a loop (use `next`). Assign a local, `break`, return once after the loop.
- Never write `while True` instead write the real exit condition, or expose an intent control such as `terminate()`, paired well with the walrus operator.
- `not x` and `parameter = parameter or default_factory()` are only for options objects you own that define neither `__bool__` nor `__len__`. For Protocols, containers, numbers and strings test `is None`: an injected empty fake with `__len__` would otherwise be silently replaced by the default.

## Errors

- One exception class per failure. Its hand-written `__init__` builds the message from typed fields. No `__slots__` on exceptions, `BaseException` already carries a `__dict__`.
- Raise as close to the cause as possible. Translate with `raise NewError(...) from err`.
- Keep `try` bodies thin. Two or more `except` blocks resolving to a value become one `error_handler` function that walks the exception chain, or a context manager that translates errors around a `yield`. Unrecoverable conditions raise at the call site.
- Make the safe path the only path: anything that must run inside a guard is handed out only by that guard, such as an adapter yielding its repository inside its error-translating context manager.
- `main()` returns an exit code; the module guard does `raise SystemExit(main())`.
- A function which exists solely to raise an exception is always wrong; a better pattern is to return an exception instance to the caller or None when it's not an error so tests can assert on the fields rather than catching per call and control flow is explicit at the call site.

## Tests

- Test behavior, not the current code. Arrangement and scenarios live in fixtures, never in the test body so what is tested can be changed without rewriting the test itself.
- Fixtures only used for a few set of tests should have locality inside class so they have narrow scope, use inheritance sparingly.
- Scenario data sits as class attributes beside the test. A repeated act-and-assert becomes a helper method on the class.
- Parametrize with `pytest.param(..., id=...)`. Hypothesis for input spaces; explicit params only for named boundaries and regressions.
- `@pytest.mark.usefixtures` for fixtures the body never references. Bundle collaborators into a frozen dataclass fixture.
- Fake repositories over mocks. Strict unit and integration separation. No side effects, no races, no inline imports of the code under test.
- Test support modules live in `src/<package>/<concept>/tests` for locality and load through conftest plugins and that stay out of the wheel. Tests live in top-level `tests/`.

## Comments and docstrings

- Zero comments. A module docstring is the only prose allowed in code. If you need a comment to explain the code, your implementation is wrong by design.
- You may find comments from the user and they will use `::<marker-name>::` as a delimiter for grepping. Leave them in place and never add your own.
- Docstrings are allowed only when a framework turns them into metadata (FastAPI routes, MCP tools).
- The one exception is the stated reason on a lint or type suppression.

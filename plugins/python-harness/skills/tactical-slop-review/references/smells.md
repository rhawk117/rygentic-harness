# Smell catalogs

What expert treats as a smell, why, and where the evidence comes from. `fact:` names the `collect_python_facts` kind that locates candidates mechanically; `pylens:` means the evidence needs reading. A fact is a candidate, never a finding: confirm it against the code, then decide whether it matters in this module. Do not report anything the gate's ruff run already reports.

## Control flow

| Smell | Why it matters to expert | Evidence | Direction |
| --- | --- | --- | --- |
| Any `else` block (if, for, while, try) | Many experienced readers do not parse `else` instantly; guard clauses and early returns reduce the invariants a reader holds | fact: `else_branch` | Invert the condition and return early; extract the branch |
| `while True` | The exit condition was not thought through | fact: `while_true` | Loop on the real condition; for a genuinely complex loop, expose a control such as `terminate()` |
| `while` ending in `break` or a bare `return` | Same smell as `while True` | fact: `break_in_loop`, `return_in_loop` | State the condition in the loop header |
| `return` inside a loop | Readers scan a loop for `continue`, `break`, `yield`, not `return`. Applies to loops only; function-level early returns are good | fact: `return_in_loop` | `next(...)`, `any(...)`, a comprehension, or assign, `break`, single return |
| Nesting deeper than 3 control-flow blocks (guards at the top excluded) | Deep nesting means the function is several functions | fact: `function_shape.max_depth` (`collect_python_facts` with `with_function_shapes`) | Extract the inner blocks into named functions |
| `match` | Does not honor an exception hierarchy; see `philosophy.md` | fact: `match_statement` | `except` hierarchy, a mapping keyed by an enum, or polymorphism |
| `del` | Called terrible by expert; usually manual lifetime management that structure should own | fact: `del_statement` | Scope the value so it ends naturally |
| Dense or nested comprehensions | Crammed lines hide semantic units from coverage and from readers | pylens or reading | Split into a generator that selects plus a function that maps one item, composed as `list(map(...))` |

## Structure

| Smell | Why | Evidence | Direction |
| --- | --- | --- | --- |
| `@staticmethod` | Bolts behavior onto a class that does not need to own it | fact: `staticmethod` | Module-level function |
| Classmethod factory | Exposes the concrete type to the consumer | fact: `classmethod` with `returns_cls_call` | Module-level factory, optionally returning a Protocol |
| Private class | Hides logic that would be clearer as a data container, a few public functions, or a Protocol implementation | fact: `private_class` | Frozen container plus public functions, or Protocol plus implementation plus factory |
| Hand-written `__init__` on a non-exception class | Dependency holders should be frozen slotted dataclasses with public fields; immutability over privacy | fact: `handwritten_init` with `exception_class: false` | `@dataclass(frozen=True, slots=True)` |
| Long `__post_init__` | A constructor with side effects cannot be tested neatly | fact: `post_init` (`statements`) | Move work into a factory function at the edge |
| `ClassVar` on a dataclass | Class-level state hidden among instance fields | fact: `classvar` with `in_dataclass` | A module constant or an options field |
| Module-level dict registry | A global mutable reference; `HANDLERS[Command(word)](...)` assumes the reader knows the whole codebase | fact: `mutable_module_global` | A dedicated class with a clear lifecycle, or a declarative table owned by an options object |
| Lambdas in lookup tables | expert calls them gross; untestable, unnamed behavior | fact: `lambda_in_collection` | Named module-level functions |
| Hidden state | Mutable defaults, module-global reads and writes, import-time I/O, constructors doing substantial work, generic setters, leaked mutable objects | fact: `mutable_default`, `global_statement`, `module_level_call`; pylens for leaks | Inject dependencies; make lifetimes explicit |
| `sys.path` mutation | Breaks editor intellisense; expert calls it disgusting | fact: `sys_path_mutation` | Proper packaging and entry points |
| `os.environ` reads deep in the code | Configuration read far from the edge; also expert prefers `os.getenv` | fact: `os_environ` | Parse settings at the entry boundary and pass typed configuration inward |
| `Path / segment` | Fails the operator-overloading test | reading | `Path.joinpath(...)` |
| Resource without a visible lifecycle | A reader must know to check that it is closed | pylens: resources | Context manager or `AsyncExitStack`; the safe path is the only path |
| Callers handed raw internals | A consumer can poke what it should not | pylens: callers | Intent methods (`cancel()`) instead of raw handles |
| Values of different lifetimes in one object | Per-line and per-document state mixed | reading | Separate objects |

## Typing and operators

| Smell | Why | Evidence | Direction |
| --- | --- | --- | --- |
| `from __future__ import annotations` | Not used in expert's code | fact: `future_annotations` | Remove; on 3.14 annotations are deferred |
| `TypeAlias` annotation | Old syntax | fact: `typealias_annotation` | PEP 695 `type X = ...` |
| `Annotated[...]` written inline in a field or parameter | Incredibly hard to read | fact: `inline_annotated` | A named alias, optionality applied at the use site |
| Bare `Any` | Opts out of checking | fact: `any_annotation` | `object`, a Protocol, or a precise type |
| ABC where a Protocol fits | expert prefers structural seams | fact: `abc_base` | `typing.Protocol` |
| `@runtime_checkable` without runtime checks | Unneeded cost and false confidence | fact: `runtime_checkable` plus a search for `isinstance` on the protocol | Remove |
| Operator overloads | Pass only the type-blind reader test | fact: `operator_overload` | A named method |
| Stringly-typed state | Widens the state space; see the review spine | pylens: state | `StrEnum` with `auto()`; `IntEnum` when ordering is meaningful |

## Async

| Smell | Why | Evidence | Direction |
| --- | --- | --- | --- |
| `asyncio.gather` | No structured cancellation | fact: `asyncio_gather` | `asyncio.TaskGroup` |
| `asyncio.to_thread` around a subprocess | A native async API exists | fact: `asyncio_to_thread` | `asyncio.create_subprocess_exec` |
| Nested `async with` towers | Hard to extend; resources cannot be pushed dynamically | reading | `contextlib.AsyncExitStack` |
| A server or long-lived service without a class-owned lifecycle | Lifecycle is implicit | pylens: resources | A class with dependency injection, an async context manager and a `serve()` method |
| Every implementation of a stream Protocol being a context manager | Bloats the Protocol | reading | Only resource-owning implementations manage context |

## Not smells

These look suspicious but are fine for expert; do not report them.

- Function-level early returns and guard clauses.
- The walrus operator.
- Module docstrings.
- Docstrings that a framework consumes as metadata (FastAPI routes, MCP tools, CLI help).
- `# noqa` with an explicit reason after the code.
- Small, cohesive classes with methods that depend on the instance's fields.

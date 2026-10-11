# Python Engineering and Code Review Guide

Use this guide when writing, refactoring, or reviewing my Python code. Apply the reasoning behind each convention. An implementation that copies the shape of an example without improving the design has missed the point.

My priority is code that is easy to understand, test, and change. A maintainer should be able to identify an operation's dependencies, ownership, effects, and failure behavior without reconstructing an undocumented sequence of obligations.

## 1. Apply the guide with judgment

- Inspect the actual implementation, callers, tests, supported Python versions, and project tooling before proposing changes.
- Treat the module layout and test organization below as defaults. Adapt them when the project provides a concrete reason, and explain how the alternative preserves the underlying goal.
- Work in small, coherent increments. Establish the behavior of a function or class, improve its design, and verify the affected behavior before expanding the change.
- Keep changes within the requested scope. A review should report findings; it does not authorize a repository-wide rewrite. A refactor should preserve behavior unless a behavior change is requested or agreed upon.
- Distinguish correctness defects, maintenance problems, and preference deviations. Explain the actual consequence of a finding rather than assigning severity because a pattern appears on a checklist.
- Use the project's real verification commands. Report what was checked and what remains unverified. The presence of tests does not prove that the design or behavior is correct.

**Review question:** What becomes easier to understand, safer to use, or cheaper to change because of this abstraction?

## 2. Put behavior at the right level

Prefer pure functions for transformations and decisions that can be expressed through explicit inputs and outputs. Formatting an error, deriving a name, or evaluating supplied data should not require constructing a service that has unrelated dependencies.

Use classes when they give cohesive state, configuration, dependencies, or resource ownership a meaningful home. Methods should operate on that responsibility. A class should not be a namespace for a collection of unrelated functions, and a standalone function should not repeatedly receive an object's entire state merely to imitate a method.

Keep orchestration readable as a sequence of meaningful operations. Separate it from the details of parsing, policy evaluation, serialization, and I/O where those responsibilities can be understood independently. Avoid fragmenting a simple operation into wrappers that add navigation without adding meaning.

Use immutable data containers when they clarify what an operation receives. A dataclass may have derived properties and cohesive behavior; it does not have to be a passive record. Immutability of its fields does not imply that methods are pure or that referenced resources cannot change.

**Review question:** Can the useful computation be exercised independently, and does each object have a reason to exist beyond grouping names?

## 3. Define the consumer interface deliberately

The documented consumer interface determines the compatibility promise. An unprefixed helper can be an internal, independently testable building block without becoming a supported API for outside consumers.

Prefer plainly named functions and classes when there is no concrete reason to restrict their use. Avoid private classes whose main purpose is hiding an implementation that would be clearer as a data container, a few functions, or an implementation behind a small protocol.

Use private members when bypassing the intended interface could violate an invariant, skip necessary protection, or misuse an owned resource. Explain that boundary through the design. An underscore is a convention; it does not enforce access control.

Make the supported entry point convenient. A factory is useful when it constructs dependencies, supplies defaults, validates configuration, or selects an implementation. Returning a protocol can communicate the operations consumers should rely on. Neither a factory nor a protocol makes the concrete object inaccessible at runtime, and a factory that only repeats a trivial constructor may add no value.

Use protocols for meaningful dependency boundaries and substitution. Add `@runtime_checkable` only when runtime protocol checks are actually needed; static use alone does not require it.

**Review question:** Is the intended interface clear and convenient without burying useful behavior behind arbitrary privacy?

## 4. Prefer established validation and library behavior

Use Pydantic's types, constraints, discriminated unions, and validators for boundary data when Pydantic is an approved project dependency. Use Pydantic Settings for environment-backed configuration where appropriate. Avoid parallel handwritten validation for behavior the schema already expresses.

Keep distinct responsibilities distinct: parsing input, validating its shape, and evaluating domain policy need not be the same operation. A validated model also does not prove that an external resource still exists or remains safe to use.

Prefer dataclasses for internal containers that do not need parsing or runtime validation. Use meaningful type aliases when repeated or complex annotations obscure the domain. Keep reusable constrained aliases named; apply optionality at the use site when it belongs to that particular field or parameter.

Using a library reduces the custom implementation and testing burden. Still test the rules, settings, and integration behavior the application depends on. A library is not proof that the chosen configuration is correct.

Use standard-library facilities when their semantics fit. For example, `textwrap.shorten` handles word-based shortening with whitespace normalization; it is not a drop-in replacement for every character limit, byte limit, or terminal-width requirement. Prefer familiar idioms over clever compositions that make the operation harder to read.

**Review question:** Are we maintaining custom behavior that an existing dependency already provides, and have we checked that the semantics match?

## 5. Give configuration a coherent owner

Group related settings into small, typed options objects. Use defaults that make the normal call site convenient, and allow explicit injection where variation matters. A test should be able to change a limit or policy through the same dependency boundary as any other caller.

Separate genuine constants from configuration and derived values:

| Kind | Appropriate treatment |
| --- | --- |
| A fixed format or protocol invariant | A named constant near the code that owns the contract |
| A limit, timeout, naming convention, or policy that can vary independently | A field on the relevant options or policy object |
| A value derived from other configuration | A calculation with one source of truth |
| Environment-provided configuration | Parse at an entry boundary and pass typed configuration inward |

For example, these settings belong together because they describe a shard's behavior:

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShardOptions:
    max_record_kib: int = 64
    lock_timeout_seconds: float = 10.0
    shard_suffix: str = '.jsonl'
    lock_suffix: str = '.lock'

    @property
    def max_record_bytes(self) -> int:
        return self.max_record_kib * 1024
```

Use `field(default_factory=...)` when a dataclass should construct an owned default dependency. In an ordinary constructor or factory, use an explicit `is None` check when only `None` means “use the default.” A supplied falsey dependency should not be silently replaced.

The reason for this design is cohesion, explicit dependencies, and easy substitution. Moving literals into a dataclass does not inherently reduce memory usage or guarantee that their lifetime matches an instance. A module-level immutable value is not a memory leak merely because it remains reachable.

Compute cheap derived values as properties. Make substantial work or fresh I/O visible as a method. If a property reconstructs a mapping on every access, decide whether that cost is acceptable; do not describe it as cached or prebuilt. Build expensive stable structures once when their owner's lifetime provides a natural boundary.

**Review question:** Can a caller see what this component depends on and vary it without monkeypatching or duplicated sources of truth?

## 6. Make failure contracts explicit

Choose between raising, returning an error, and returning a typed outcome per operation. Do not apply one mechanism indiscriminately throughout the codebase.

A policy object can evaluate supplied facts and return a specific error or `None`, leaving the calling operation to decide whether to raise, collect, or present the problem. This is useful when policy evaluation itself is meaningful behavior. Keep related checks together when they share configuration or enforce the same concept.

The following completes the policy-check pattern. This example operates on bytes already in memory; a stream reader must enforce its read cap before allocating the entire payload.

```python
from dataclasses import dataclass


class PayloadTooLargeError(ValueError):
    def __init__(self, actual_bytes: int, limit_bytes: int) -> None:
        super().__init__(f'Payload is {actual_bytes} bytes; maximum is {limit_bytes} bytes')


@dataclass(frozen=True, slots=True)
class PayloadPolicy:
    max_payload_bytes: int = 64 * 1024

    def check_size(self, size_bytes: int) -> PayloadTooLargeError | None:
        if size_bytes > self.max_payload_bytes:
            return PayloadTooLargeError(size_bytes, self.max_payload_bytes)
        return None


def validate_payload(payload: bytes, policy: PayloadPolicy) -> None:
    """Validate the size of an in-memory payload.

    Raises:
        PayloadTooLargeError: The payload exceeds the configured byte limit.
    """
    error = policy.check_size(len(payload))
    if error is not None:
        raise error
```

This makes the raising decision visible. It does not make the check mandatory for callers. When an invariant must hold for every write, the writer must enforce it internally before performing the write.

Annotate the contract accurately:

| Behavior | Annotation and documentation |
| --- | --- |
| Always raises or otherwise never returns normally | `NoReturn` or `Never` |
| Returns normally on success but may raise | The actual return type, plus documented exception types and conditions |
| Returns an error object on failure | Include that error type in the return annotation |
| Returns a successful value or a structured failure | A specific, distinguishable outcome type appropriate to that API |

`NoReturn` does not mean “may raise.” Python's standard type annotations do not list checked exceptions. Document anticipated exceptions in a `Raises` section or the project's equivalent convention. Do not invent a return union containing an exception that the function only raises.

Preserve useful diagnostics. Translate dependency errors at the boundary responsible for them, retaining the cause with `raise ... from error`. Catch the failures that boundary understands. Avoid replacing a precise domain message with a less informative generic one; apply redaction where the output contract requires it.

**Review question:** Can the reader identify what failure means, how it is represented, and who decides how to handle it?

## 7. Put required protection inside the abstraction

An operation should own the protections required for its contract. Callers should not have to remember a separate error-translation wrapper, lock, validation step, or cleanup procedure that the operation could provide itself.

Use context managers when a scoped lifetime is part of the interface. For generator-based `@contextmanager` implementations, use `collections.abc.Generator`; for `@asynccontextmanager`, use `collections.abc.AsyncGenerator`. Use the type-argument form supported by the project's minimum Python version. The explicit forms `Generator[Resource, None, None]` and `AsyncGenerator[Resource, None]` avoid relying on newer default type arguments.

Expose context management as part of acquiring or using the protected resource. Keep ownership clear: who opens or creates it, who may close it, and whether it remains valid after the context exits.

Be precise about what the design guarantees. Yielding a raw repository or handle does not stop a caller from retaining it. A frozen wrapper does not freeze the underlying repository, descriptor, or filesystem. When protection must accompany every operation, offer operations through an adapter that owns that protection.

Keep exception translation narrow. A context manager around arbitrary caller code can catch an unrelated exception raised inside the `with` body. Translate at a point where the operation and exception meaning are known.

**Review question:** Does the normal API provide the promised protection, or does correctness still depend on an undocumented caller ritual?

## 8. Organize by concept, then responsibility

Use concept packages to keep related behavior together. Within a concept, use predictable role names so the maintainer can locate definitions and follow dependencies. These are defaults, not a requirement to create empty layers.

| Module | Responsibility |
| --- | --- |
| `domain.py` | Domain types, enums, value objects, and representations independent of I/O |
| `schemas.py` | Validated boundary models and consumer-facing data shapes |
| `store.py` or `repository.py` | Data access, persistence, and dependency-specific operations |
| `services.py` or `use_cases.py` | Application orchestration |
| `policy.py` | Cohesive invariant or policy evaluation |
| `errors.py` | Domain and application exception definitions |
| `util.py` | Small, cohesive helpers shared within the concept |
| `tests/` | Tests and test support owned by that concept |

Choose one name where the table offers alternatives, and use it consistently. A module can become a package when its responsibilities grow. Add a layer because the implementation needs it, not because it appears in the table.

Keep foundational types independent of services and persistence. Place dependency contracts where consumers can use them without importing concrete infrastructure. Avoid forcing one concept to import another concept's implementation details to perform a common operation.

Provide a small shared home for cross-concept conventions such as timezone handling when the application already needs a consistent policy. Centralize the semantic decision, not every occurrence of similar syntax. A shared module should have a clear purpose and should not become a miscellaneous dependency hub.

**Review question:** Can someone unfamiliar with the repository predict where a responsibility lives and understand the direction of its dependencies?

## 9. Use names that carry the missing context

Name standalone operations with a meaningful verb and subject: `serialize_ledger_record` communicates more than `serialized`. A method may use a shorter name when the receiver supplies the subject, such as `record.serialize()`.

Use the containing object to remove redundant qualifiers. A coherent directory-names object can expose `tickets`; a detached global name needs more context. Brevity is useful when the context is visible.

Keep units explicit in limits and timeouts. Use aliases to make verbose types readable when the alias expresses a useful concept. Neither shorter names nor additional aliases are goals by themselves.

## 10. Keep tests close to the behavior they describe

Use the narrowest useful owner for fixtures, strategies, and helpers. A fixture used only by one test class belongs in that class. A strategy describing that class's scenarios should be visible near those tests, including as a class attribute when useful.

Distinguish fixture visibility from fixture lifetime. Placing a fixture in a class does not require making its lifetime class-scoped. Choose function, class, module, or session lifetime according to isolation and resource cost.

Prefer composition and local fixtures. Use fixture inheritance sparingly, only when it makes shared behavior clearer than local definitions or composition. Avoid forcing readers to search a hierarchy to understand setup.

Give repeated scenarios a meaningful helper when it removes distracting repetition. A helper should make the operation and expected outcome clear, execute the relevant action, and preserve useful assertions. Keep test-specific assertions visible or return the captured error for further inspection. A helper that merely renames `pytest.raises` without clarifying the scenario may add little.

Keep concept-owned support close to its implementation, ordinarily under `src/<package>/<concept>/tests/`. Adapt this placement when the repository has a concrete packaging or collection requirement. Production code must not depend on test helpers or require pytest to import a production package.

Use local `conftest.py` fixtures for local availability. Use pytest plugins for intentional broader sharing. Registering a fixture module as a plugin does not make its fixtures local to the importing concept; do not use nested `pytest_plugins` declarations as a scoping mechanism.

### Choose tests by the behavior they establish

- Use parametrization for a small, intentional table of distinct scenarios, explicit mappings, and known regressions.
- Use Hypothesis when a meaningful property should hold across a broad input space. Keep strategies understandable and close to their owner.
- State the property before designing the generator. A large collection of generated inputs without a useful assertion is not a valuable property test.
- Keep representative examples and regression cases even when property tests are present. They explain the contract and preserve known failures.
- Exercise pure policy and transformation behavior directly. Verify that integrations actually invoke necessary protections as well.
- Test application decisions and observable effects. Avoid mirroring private implementation steps or retesting library internals that the application does not customize.

**Review question:** Can someone understand the scenario locally, and what real regression would cause this test to fail?

## 11. Choose filesystem and platform APIs by their guarantees

Prefer `pathlib.Path` for path composition and ordinary path operations. Use `os` when the operation needs descriptor-based access, file metadata for an already-open object, flags, synchronization, truncation, or another capability without an equivalent high-level API.

An `os` call deserves an understandable reason, not automatic rejection. Replacing descriptor-based checks with separate path checks can change the safety properties. Explain relevant platform limitations and preserve the guarantees the operation needs.

Make format contracts explicit. A binary line format can intentionally use `b'\n'` on every platform. `os.linesep` describes a platform convention; it is not automatically the correct delimiter for a portable format. Text-mode translation is a separate concern.

Keep acquisition, validation, use, and cleanup coordinated. A path check performed earlier does not prove that a later operation refers to the same filesystem object. Handle partial operations and resource ownership at the boundary that can do so correctly.

**Review question:** Does this API provide the required behavior on supported platforms, and have we preserved the operation's actual guarantees?

## 12. Report findings so they can be acted on

For each substantive finding, provide:

1. The location and observed behavior.
2. The consequence for correctness, maintainability, testability, or callers.
3. The relevant principle and the smallest coherent improvement.
4. Any compatibility or behavior change the improvement requires.
5. A useful verification step, where one is needed.

Prioritize concrete defects and expensive maintenance problems. Group repeated instances of the same design issue where that makes the report clearer. Mark uncertainty and verify claims about language features, dependency behavior, and IDE diagnostics rather than guessing.

Before declaring the work complete, check that the implementation is understandable at its call sites, dependencies are explicit, failure contracts are accurate, required protections are owned, and the affected behavior has been meaningfully verified.

## Reusable preference summary

I prefer Python code that reduces the maintainer's memory burden: make dependencies, ownership, effects, and failure behavior clear where they matter. Use pure functions for independent computation and cohesive objects for state, policy, resources, and injected configuration. Make the intended consumer interface convenient and let it provide its required protections. Only the documented consumer interface carries a compatibility promise; an unprefixed helper may remain internal. Keep fixtures, strategies, and scenario helpers near their owners. Prefer predictable concept-based organization and established library behavior, adapting defaults when concrete project requirements justify it. Choose error representation per operation and accurately annotate and document its contract. Use `collections.abc.Generator` for generator-based context managers. Judge abstractions and tests by the clarity, correctness, and maintainable change they enable, rather than by resemblance to examples.

## Technical references

These references support language and library details; the preferences above remain the review criteria.

- [Python typing: `Never` and `NoReturn`](https://typing.python.org/en/latest/spec/special-types.html#never)
- [PEP 484: exception documentation](https://peps.python.org/pep-0484/#exceptions)
- [Python `typing`: generator annotations, protocols, and type aliases](https://docs.python.org/3/library/typing.html)
- [Python `contextlib`: generator context managers and exception handling](https://docs.python.org/3/library/contextlib.html#contextlib.contextmanager)
- [Python dataclasses: frozen instances and default factories](https://docs.python.org/3/library/dataclasses.html)
- [Pydantic validators](https://docs.pydantic.dev/latest/concepts/validators/)
- [pytest: loading plugins from test modules and `conftest.py`](https://docs.pytest.org/en/stable/how-to/writing_plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file)
- [Python `textwrap.shorten`](https://docs.python.org/3/library/textwrap.html#textwrap.shorten)
- [Python `os.linesep`](https://docs.python.org/3/library/os.html#os.linesep)

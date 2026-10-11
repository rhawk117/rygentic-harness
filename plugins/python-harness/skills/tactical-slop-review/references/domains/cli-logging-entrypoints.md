# Domain: CLIs, logging and entry points

Load when `survey` lists `cli`, or the surface contains `__main__.py`, a `main()` function, or logging setup.

## Entry points

- `main()` returns an exit code; `__main__` does `raise SystemExit(main())`. Calling `sys.exit()` inside the program is a finding.
- Configuration is parsed at the entry boundary (arguments, environment, files) into typed options and passed inward. `os.getenv` over `os.environ`; reading either deep inside the code is a finding.
- No `sys.path` manipulation and no runnable `src/` directory hacks.
- Library public surface: users import one entry-point class or function, not a pile of types; entry functions take about two arguments; configuration through builder methods with safe defaults and named presets.

## CLI output

- `rich` for human-facing output (progress, Markdown rendering via its built-in Markdown) where the project already uses it; tab characters instead of runs of spaces in aligned output strings.
- Group related string constants in a `StrEnum`; a set of notices or messages is better as a class that encodes them with per-notice methods than a `StrEnum` of templates, and templates must be hard to misuse.
- Enums use `auto()`; an enum may carry a property (for example a `slash()` that adds a prefix).

## Logging

- Dependency weight matches program size: stdlib `logging` (with `dictConfig`, and `RichHandler` behind a setup flag for colour) for small programs; loguru with declarative `logger.configure()` for larger ones. `remove()` followed by sequential `add()` calls is a finding where loguru is used.
- Long-lived services log full date plus time in UTC; time-of-day-only stamps are a finding.
- One configuration point; no handler setup scattered across modules.

## Decorators and serialization

- Decorators use `functools.wraps` or `update_wrapper`, never hand-assigned identity dunders.
- msgspec over stdlib `json` plus hand-rolled encoder tables where msgspec is a dependency; set Struct configuration (for example `rename='camel'`) once on a base class.
- Never hand-roll what the ecosystem provides (git parsing when a git library is present, custom XML escaping, YAML flavoring when msgspec has YAML support).

# Domain: frameworks (FastAPI, MCP, Pydantic, msgspec)

Load when `survey` lists `fastapi`, `mcp`, `pydantic` or `msgspec`.

## Use the framework's own idiom

- **Metadata from the framework's source of truth.** FastAPI route docstrings become OpenAPI descriptions and MCP tool names and descriptions come from the function name and docstring. These docstrings are the one sanctioned function docstring; never flag them, and flag a separate `description=` that duplicates them.
- **One error mapping.** Exceptions translate to responses or tool errors in one place (an exception handler, a single mapping), not in a wrapper repeated per route or tool.
- **Lifespans hold real lifecycles.** A server lifespan that only smuggles dependencies into global state is a finding; dependencies arrive through the framework's injection.
- **Runtime-evaluated annotations.** FastAPI and Pydantic read annotations at runtime, so moving their imports under `TYPE_CHECKING` breaks them; a reasoned `noqa: TC00x` there is correct.

## Validation and data containers

- Pydantic validates boundary input when it is a project dependency: types, constraints, discriminated unions, validators, Pydantic Settings for environment configuration. Parallel hand-written validation of what the schema already expresses is a finding (guide §4).
- Parsing, shape validation and domain policy stay distinct; a validated model does not prove an external resource still exists.
- msgspec for wire formats and serialization; Struct subclasses must not trip Pylance's frozen-inheritance error; configuration set once on a base class.
- Frozen slotted dataclasses for internal values and dependency holders.
- Constrained types are named aliases, never `Annotated[...]` inline in fields or parameters.

## Structure

- MCP servers follow expert's layout: `src/<name>/` with `__main__.py`, `cli.py` (argparse, `--transport stdio|http`, `--host`, `--port`, `--root`), `server.py` (server, context, registrations), `workspace.py` (root-contained paths, external binary dispatch), and `tools/<tool>/{schema.py, use_case.py}` with Pydantic input and output models plus a plain `run(workspace, params)` function registered centrally.
- FastAPI performance work (msgspec responses, custom route classes, ASGI middleware) is welcome but is a complexity-budget question: it must not come before an airtight design.

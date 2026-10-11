# `python-harness` CLI and MCP tools reference

Two commands run on the CLI, and the `python-harness` MCP server has eight tools: two documentation tools and six that read the project. The four project tools below are the ones the review calls. Each command and tool returns one compact JSON document. Paths in output are relative to the project root and use `/`, except `survey.root` and the config paths inside the gate's argv, which are absolute.

## CLI commands

Each prints its document on stdout. Run it from the reviewed project's root (the directory holding its `pyproject.toml`), or pass `--root DIR`. A failure the CLI understands prints `python-harness: <message>` on stderr and exits 2.

| Command | Exit code | Use |
| --- | --- | --- |
| `python-harness inspect survey` | 0 | Mode evidence, domains, ruff config, layout |
| `python-harness inspect gate --fallback-ruff-config ${CLAUDE_SKILL_DIR}/assets/ruff.toml` | 0 passed, 1 a tool failed | Runs the project's own ruff check, ruff format check, ty and pytest |

## MCP tools

Claude Code names each tool `mcp__plugin_python-harness_python-harness__<tool>`. The document is the tool's text result. The project root is the session's project directory, `CLAUDE_PROJECT_DIR`, and nothing else: there is no root input. Every path input is relative to that root; an absolute path outside it, a `..` path that leaves it, or a symlink that points outside it is a tool error, and a directory input skips entries that resolve outside it. A failure the tool understands is a tool error whose text is the message, not a JSON document.

| Tool | Inputs | Use |
| --- | --- | --- |
| `plan_review_surface` | `paths` (list), or `diff_base` with optional `diff_head` | Review surface as import-graph clusters, one pylens dispatch each |
| `collect_python_facts` | `paths` (list, required), `with_function_shapes` (boolean, default false), `detail`, `budget` | Mechanical AST facts per module |
| `map_python_calls` | `paths` (list, required), `symbol` (optional), `detail`, `budget` | Per-module coupling metrics and reference tallies; `symbol` lists one symbol's call sites |
| `check_citations` | exactly one of `path` and `text` | Checks every `path.py:line` citation and its quote in a Markdown document |

`collect_python_facts` and `map_python_calls` answer inside a budgeted envelope; the other project tools return their plain document and take no `detail` or `budget`. Every project tool's document carries the workspace diagnostics under `workspace`, in the envelope of the two budgeted tools and at the top level of the others: `{source_roots[], fallback_diagnostics[], unindexed_packages: [{name, directory}]}`. Always pass `detail: full` and `budget: 20000` to the two budgeted tools and read the document under `result`: the default is a summary that leaves facts out. When `degraded` is true, `result` holds a smaller document than the one asked for; halve the `paths` list and call again.

A missing target path is a tool error, never an empty result. Files that cannot be read or parsed (bad encoding, syntax errors) are listed under `unparsable` instead of stopping the tool. `check_citations` returns its report whether or not the citations hold; read `passed`.

## survey

```
{root, source_roots[], ruff_config: "ruff.toml" | ".ruff.toml" | "pyproject.toml" | null,
 ty_config: "ty.toml" | "pyproject.toml" | null,
 manifest: {name, requires_python, build_backend, entry_points[], classifiers[],
            dependencies[], dev_dependencies[], optional_dependencies[], declared_distributions[]} | null,
 layout: {has_py_typed, has_dunder_main, has_src_layout, has_tests_directory, has_uv_lock},
 mode: {mode: "library" | "application", reasons[]},
 domains: ["pytest" | "hypothesis" | "sqlalchemy" | "fastapi" | "mcp" | "pydantic" | "msgspec" | "cli" | "asyncio"],
 external_packages[]}
```

`mode` is an inference with its reasons; state the reasons when you state the mode. `dev_dependencies` holds only uv's default groups (`dev` unless `[tool.uv] default-groups` says otherwise); extras and other groups are `optional_dependencies`. `declared_distributions` is what the gate treats as installed with the project. `external_packages` includes the standard library.

## gate

```
{ruff_config_source: "repository" | "fallback" | "defaults",
 ty_config_source: "repository" | "fallback" | "defaults",
 results: [{command: {tool: "ruff_check" | "ruff_format" | "ty" | "pytest", program, arguments[], argv[]},
            outcome: {kind: "exited", exit_code} | {kind: "timed_out"},
            output_tail, passed, timed_out}],
 created_paths: {kind: "tracked", paths[]} | {kind: "not_tracked"},
 passed}
```

Declared tools run through `uv run --isolated` (plus `--frozen` when `uv.lock` exists), so the project's pinned versions apply without writing a lockfile, a `.venv` or caches. Undeclared ruff runs through `uvx ruff@<version>`, where the version is the plugin option `ruff_version` (default `0.16.9`, read by `inspect gate` from `PYTHON_HARNESS_RUFF_VERSION`); a project that declares ruff runs its own. Undeclared ty and pytest join the project environment with `--with`. pytest runs only when the survey found the pytest domain. `ruff check` runs with `--no-fix`, so a project config that sets `fix = true` does not change any file, and with `--statistics`, so its tail is a count per rule. Some build backends still write into the tree (setuptools writes `*.egg-info`): `created_paths.paths` lists every untracked or ignored path that appeared during the run; outside a git repository it is `{kind: "not_tracked"}`. Nothing is deleted. Options: `--skip TOOL` (repeatable), `--timeout SECONDS` (default 600). A `--fallback-ruff-config` path that does not exist is an error (exit 2); a relative one is resolved against the root. The fallback config's `src` is set to the roots the survey found, so first-party imports resolve for the reviewed project. `inspect gate` passes no ty fallback, so its `ty_config_source` is `repository` or `defaults`.

## plan_review_surface

```
{target: {kind: "codebase", paths[]} | {kind: "diff", base, head},
 clusters: [{id: "c01", modules: [{path, module, lines}], tests[], dependents[], lines}],
 unparsable: [{path, line, message}],
 options: {max_cluster_lines, dispatch_budget},
 dispatches, line_count, module_count, over_budget}
```

A cluster is a connected group of surface modules that import each other, split when it passes `options.max_cluster_lines` (1200; the tool has no input for it). `tests` are test modules that import a cluster module; `dependents` are other project modules that import it (callers outside the surface). Modules with no code (empty, comment-only, or only a docstring, such as most `__init__.py` files) are left out. `over_budget` compares `dispatches` with `options.dispatch_budget` (24; no input either). Several `paths` form one surface, and no `paths` and no `diff_base` means the whole project. A diff surface holds only the `.py` files added or modified between `diff_base...diff_head` (`diff_head` defaults to `HEAD`), relative to the root, and is read from the working tree, so the head must be the checked-out commit. `paths` together with `diff_base`, `diff_head` without `diff_base`, and a revision that starts with `-` are tool errors.

## collect_python_facts

```
{detail: "full" | "summary" | "counts", budget, tokens, truncated, degraded, result: <document>, workspace}
```

`detail` is the level of the document under `result`, which is the level that fit, not always the one asked for. `budget` is the token budget; it must be at least 256, and the default is 4000. `tokens` is the estimated size of the whole response. `truncated` is true when `result` leaves out items or when `degraded` is true. `degraded` is true when the requested detail did not fit the budget and the tool stepped down (`full` to `summary` to `counts`). A `counts` response that still does not fit is a tool error. `workspace` holds the workspace diagnostics. The `detail` argument is `full` (every fact), `summary` (the default: counts, the highest-ranked modules and a `narrowing` entry with the arguments for a full call) or `counts` (totals only). The document under `result` at `full` is:

```
{modules: [{path, line_count, counts: {kind: n},
            facts: [{line, symbol: "Class.method" | "function" | null, detail: {kind, ...fields}}]}],
 unparsable[]}
```

Kinds and their detail fields: `else_branch` (statement), `while_true`, `break_in_loop`, `return_in_loop`, `match_statement`, `del_statement`, `try_block` (handlers, statements_in_try, caught: list of names), `exception_base_handler` (caught: Exception, BaseException or bare), `raise_without_cause`, `staticmethod`, `classmethod` (returns_cls_call), `private_class`, `dataclass` (frozen, slots, kw_only: each `{kind: "constant", value}` or `{kind: "expression", source}`), `protocol`, `runtime_checkable`, `abc_base`, `handwritten_init` (statements, exception_class), `post_init` (statements), `classvar` (in_dataclass), `operator_overload` (operator), `mutable_default`, `mutable_module_global` (name), `global_statement`, `module_level_call` (call), `sys_path_mutation`, `os_environ`, `lambda_in_collection`, `inline_annotated`, `future_annotations`, `any_annotation`, `typealias_annotation`, `comment` (text), `docstring` (owner), `asyncio_gather`, `asyncio_to_thread`.

`function_shape` (parameters, positional, statements, max_depth, is_async, returns_annotated), one per function, is left out unless `with_function_shapes` is true: it is most of the output, and the gate's ruff statistics plus the per-module maxima from `map_python_calls` already show where size limits trip. Ask for it on the modules where they do.

Modules come out in path order, each once, however the `paths` overlap. Names match as written: `from asyncio import gather` followed by `gather(...)` is not detected.

## map_python_calls

```
{detail: "full" | "summary" | "counts", budget, tokens, truncated, degraded, result: <document>, workspace}
```

The envelope keys, `detail` values, defaults and budget minimum are those of `collect_python_facts` above. At `summary`, `result` holds `counts`, the highest-ranked `modules` (without `symbol`), `top_referenced_symbols` and a `narrowing` entry with the arguments for a full call; at `counts` it holds totals only. At `full`, `result` is one of the two documents below.

Document under `result` without `symbol`:

```
{modules: [{metrics: {path, module, fan_in, fan_out, instability, public_symbols, private_symbols,
                      function_count, max_function_statements, max_parameters, test_paths[]},
            external: [{name, kind: "function" | "class" | "constant", line,
                        referencing_paths[], context_counts: {call?, import?, annotation?, name?}}],
            internal_only: [name],
            unreferenced: [name]}],
 unparsable[]}
```

`external` holds the symbols other files reference, with who references them and how; `internal_only` names symbols used only inside their own module; `unreferenced` names symbols nothing references.

Document under `result` with `symbol` (a bare name or `module.name`):

```
{name, symbols: [{definition: {module, path, name, kind, line, is_public},
                  references: [{path, line, context}], context_counts, reference_count, referencing_paths[]}],
 unparsable[]}
```

A symbol's reference count is the sum of its `context_counts`; it is private when its name starts with `_`. `referencing_paths` leaves out the defining file and includes tests. Resolution is static: imports, aliases and dotted attribute chains are followed; method calls on instances, re-exports through `__init__` and star imports are not. A symbol with no references may still be used dynamically; treat that as a question for pylens, not as proof it is dead. `instability` is `fan_out / (fan_in + fan_out)`, null when both are zero.

## check_citations

```
{document, checked: int,
 failures: [{citation: {document_line, path, start, end, quote},
             problem: "outside_workspace" | "missing_file" | "unreadable_file"
                    | "line_out_of_range" | "missing_quote" | "quote_not_found"}],
 uncited_rows: [document_line],
 passed}
```

A citation is `path.py:12` or `path.py:12-14`; its quote is the first backticked span after it on the same line, and it is required: a citation without a quote, or with a quote under 3 characters, fails as `missing_quote`. Quotes compare with whitespace collapsed and must appear within the cited lines. Citations inside fenced code blocks are ignored. `uncited_rows` lists Markdown table data rows (outside fences, not header or separator rows) that hold no `path.py:line` citation, such as `#L34` or `:34` styles; `passed` needs no failures and no uncited rows. `checked` counts the citations that were parsed. `path` names a document inside the project; `text` is the document itself, so a pylens return never has to be written to disk or passed through a shell. `document` is that path, or `<text>` for inline text. A document that cannot be read, a `path` outside the project, and both or neither of `path` and `text` are tool errors.

---
name: tactical-slop-review
description: Review a Python PR, branch or codebase against an expert's engineering guide and write PYTHON-REVIEW.md (findings) or REFACTOR-PLAN.md (a refactor plan). Use when asked to review Python code, find slop, check a PR before merge, or plan a cleanup once code exists. Facts come from the python-harness MCP tools and cited pylens subagents; the review never edits code.
argument-hint: "[pr <num|branch> | codebase [path]] [report|plan]"
paths:
  - "**/*.py"
  - "**/*.pyi"
  - "**/pyproject.toml"
allowed-tools:
  - Read
  - Grep
  - Glob
  - AskUserQuestion
  - Agent
  - mcp__plugin_python-harness_python-harness__survey
  - mcp__plugin_python-harness_python-harness__gate
  - mcp__plugin_python-harness_python-harness__plan_review_surface
  - mcp__plugin_python-harness_python-harness__collect_python_facts
  - mcp__plugin_python-harness_python-harness__map_python_calls
  - mcp__plugin_python-harness_python-harness__check_citations
  - mcp__plugin_python-harness_python-harness__search_python_docs
  - mcp__plugin_python-harness_python-harness__read_python_docs
  - Bash(git rev-parse HEAD)
  - Bash(git symbolic-ref --short refs/remotes/origin/HEAD)
  - Bash(git fetch origin *)
  - Bash(gh pr view *)
disallowed-tools:
  - Edit
  - NotebookEdit
---

# Tactical slop review

<purpose>
You review Python code against the expert's engineering guide and the expert's design philosophy, and you deliver either a findings report or a refactor plan. The work is split on purpose. Deterministic tools on the `python-harness` MCP server find everything an AST can find exactly and for free. pylens subagents, running on a lighter model, call the fact tools for their cluster, read the code and return cited, neutral facts, including the ones that need reading to find. You hold the rules and make every judgment, because a gatherer that judges sees what it expects. Every citation is checked by a tool before it can support a finding, so a hallucinated fact costs nothing. The review never edits code: the expert decides what to change.
</purpose>

<inputs>
- Stages that hand to this skill once code exists: design-tests, data-engineering, data-analysis and automate-task. It can also be invoked directly, by name or when the request matches the description.
- Arguments: a target (`pr <number>`, `pr <branch>` or `codebase [path ...]`, default path `.`) and an output (`report` or `plan`).
- The plugin's MCP server exposes eight tools: `survey`, `gate`, `plan_review_surface`, `check_citations`, `collect_python_facts` and `map_python_calls`, plus `search_python_docs` and `read_python_docs`. Claude Code names each one `mcp__plugin_python-harness_python-harness__<tool>`; the steps below use the short names. The project tools take no root argument: the reviewed project is the session's project directory (`CLAUDE_PROJECT_DIR`), the directory holding its `pyproject.toml`. Every path they take is relative to it, and they refuse paths outside it. If these tools are not available, stop: the server did not start. Tell the user to check the plugin in `/plugin` (its Errors tab) and the server in `/mcp`.
- When the user points at a sub-project, stop and ask them to start Claude Code inside it; from the parent directory the tools would resolve the sub-project's imports against the wrong root.
- Every project-tool response preserves its tool-specific fields and adds a `workspace` object with `source_roots`, `fallback_diagnostics` and `unindexed_packages`. Treat `fallback_diagnostics` as non-fatal workspace discovery context when explaining the results.
- Paths below that start with `references/` or `assets/` are inside this skill's directory, `${CLAUDE_SKILL_DIR}`.
- Read now: `references/philosophy.md` (the expert's principles and the decisions that override the guide), `references/judging.md` (how facts become findings, and the finding format), `references/review-guide.md` (the guide itself), `references/smells.md` (catalogs, and the fact kind behind each smell). Read `references/inspect-cli.md` whenever a tool's output is unclear.
</inputs>

<workflow>
### 1. Settle the request

Parse the arguments. Anything missing or ambiguous is an `AskUserQuestion` question, not an assumption. Note any mode override the user wrote in free text ("treat this as application code").

- **PR number:** run `gh pr view <number> --json baseRefName,headRefName,headRefOid`, then `git fetch origin <baseRefName>` so the base is current. The diff base is `origin/<baseRefName>`.
- **Branch:** the base is the repository's default branch (`git symbolic-ref --short refs/remotes/origin/HEAD`, or `main`/`master` when that ref is missing; ask if neither exists or the user named another).
- **HEAD must be the reviewed head.** The tools and pylens all read the working tree, so reviewing a branch that is not checked out reviews the wrong code. If `git rev-parse HEAD` differs from the PR's head commit or the branch tip, stop and ask; offer `gh pr checkout <number>` or `git switch <branch>` only with the user's confirmation, since it changes their working tree.

### 2. Survey

Call `survey`. Take the inferred mode and its reasons; apply the user's override if there was one and keep both for the report. Record `ty_config` from the survey: it is `ty.toml` when that user config exists, `pyproject.toml` when it declares `[tool.ty]`, and `null` otherwise. Load the domain references the survey's `domains` result calls for:

| Domain | Reference |
| --- | --- |
| pytest, hypothesis | `references/domains/pytest.md` |
| sqlalchemy | `references/domains/sqlalchemy.md` |
| cli (or any `__main__.py`, `main()`, logging setup in the surface) | `references/domains/cli-logging-entrypoints.md` |
| fastapi, mcp, pydantic, msgspec | `references/domains/frameworks.md` |

### 3. Gate

Call `gate`. It runs the project's own ruff check, ruff format check, ty and pytest in isolated environments. The server supplies the expert's bundled ruff config (`assets/ruff.toml`) only when the project has no Ruff configuration, and its bundled ty config (`assets/ty.toml`) only when `ty_config` is null; a project configuration always takes precedence. A failed check is returned as report JSON, which is a fact for the report, not a reason to stop. Whatever the gate reports is not repeated as a finding. If `created_paths.paths` is non-empty (some build backends write `*.egg-info`), list those paths in the report's Run facts and tell the user; do not delete them.

### 4. Plan the surface and respect the budget

Call `plan_review_surface` with `paths` (one entry per codebase path), or with `diff_base` set to the base and `diff_head` set to `HEAD`; never both. If `module_count` is 0, stop and tell the user: there is nothing to review (no changed Python files, or only empty modules). Each cluster is one pylens dispatch. When `over_budget` is true (more than 24 dispatches), show the clusters (id, modules, lines) and ask with `AskUserQuestion`: run all of them, narrow to paths the user names (call `plan_review_surface` again with every named path in one `paths` list), or keep the largest N. Do not dispatch until the user answers. Record what was left out for the report's Not reviewed section. The budget covers every dispatch in the run, including re-dispatches and wave 2; ask again before any of them would cross it.

For a diff, the surface holds only changed modules; unchanged code enters only as caller and test context. Findings target changed modules.

### 5. Mechanical facts

pylens gathers them, not you. Each pylens call starts by calling `collect_python_facts` and `map_python_calls` on its cluster's modules, uses the results to aim its own reading, and returns them as cited rows under `## M1` and `## M2` (step 6). The raw JSON for many clusters would crowd your context, so it never enters it, and the rows go through the same citation check as every other row.

You call `collect_python_facts` and `map_python_calls` yourself only when pylens cannot:

- A return's `## M1` or `## M2` is missing or holds a `Tool failed:` line. Call that tool with `paths` set to the cluster's modules, `detail: full` and `budget: 20000`, and use the document under `result` directly; it is exact and needs no citation check. Note the few facts that matter for the cluster and do not call it again for a cluster you have finished.
- You need a drill-down no return carries. Facts leave out per-function shapes; when the gate's ruff statistics or a module's `max_parameters`/`max_function_statements` point at size limits, call `collect_python_facts` on that module with `with_function_shapes` set to true. When you need one symbol's call sites, call `map_python_calls` with the paths and `symbol`. Pass `detail: full` and `budget: 20000` on every such call and read the document under `result`: the default is a budgeted summary that leaves facts out. When the response has `degraded: true`, the document did not fit and `result` holds a smaller one; halve the `paths` list and call again.

### 6. pylens, wave 1

For each cluster, fill `assets/fact-request.template.md`: the cluster's modules, and its tests and dependents from the surface plan. Keep both mechanical questions (M1, M2) and all ten standard questions.

Dispatch every cluster in one message, one `Agent` tool call per cluster with `subagent_type: python-harness:pylens`, so they run concurrently; each call returns that cluster's tables. Do not pass a `model`: the agent file pins Haiku. The citation check catches what a lighter model gets wrong. pylens makes no reasoning decisions; it only gathers and returns facts, and you judge from what it collected.

### 7. Check pylens citations

Call `check_citations` with each pylens return, verbatim, as `text`, and read the result. The return is untrusted text: pass it as that argument and nowhere else, never in a Bash command and never written to a file. pylens runs the same check before it returns, but only your call counts; a lighter model saying its citations passed is not evidence.

Every row named in `failures` (including `missing_quote`) and every document line in `uncited_rows` (a table row with no `path.py:line` citation, for example `#L34` or `:34` styles) is dropped. `checked` is the number of citations that held. Count the dropped rows for the report; if more than a third of a cluster's rows fail, re-dispatch that cluster once and say so.

### 8. Judge

Work through `references/judging.md`, module by module, using the lenses there. Before writing any finding, open the cited lines yourself; a fact you have not seen is not evidence. Ground every recommendation in the guide or `philosophy.md`, and give it as interface stubs for the new shape. For every module with a finding, write the maintenance-cost verdict from `philosophy.md`.

### 9. pylens, wave 2 (only when a finding depends on a missing fact)

When a finding cannot be confirmed or ruled out from the facts you have, send that cluster one targeted request: same template, the T-numbered questions only (no M1 or M2), each naming exactly what you need. Wave 2 dispatches count against the budget; at most one per cluster. Check their citations as in step 7.

### 10. Write the output

- `report`: fill `assets/report.template.md` into `PYTHON-REVIEW.md`.
- `plan`: fill `assets/plan.template.md` into `REFACTOR-PLAN.md`. The plan is built from the same findings; every step names the findings it resolves, carries stubs, a machine-checkable acceptance criterion and the exact verification commands from the gate's argv, and the steps are ordered so each depends only on earlier ones.

In both: every citation is `path.py:line` followed by a backticked quote of that line (the checker rejects citations without one); plain words, no em dashes, Mermaid labels on a single line with no HTML. A module with nothing worth saying goes under Clean modules with a one-line reason; do not invent findings to fill the template.

### 11. Check the output's citations

Call `check_citations` with `path` set to `PYTHON-REVIEW.md` (or `REFACTOR-PLAN.md`). Fix or remove every failing citation and call it again until `passed` is true. A review that ships a broken citation has asserted something nobody checked.
</workflow>

<dispatch>
Each pylens call in steps 6 and 9 is one `Agent` call to this agent:

- agent: `python-harness:pylens`
- model: haiku
- effort: low
- tools: Read, Grep, Glob, `mcp__plugin_python-harness_python-harness__collect_python_facts`, `mcp__plugin_python-harness_python-harness__map_python_calls`, `mcp__plugin_python-harness_python-harness__check_citations`, `mcp__plugin_python-harness_python-harness__survey`

If `python-harness:pylens` is not an available agent type, stop. The plugin's agents did not load: tell the user to check the plugin in `/plugin` (its Errors tab) or run `claude plugin validate` on it, then start a new session. Do not substitute another agent: the user chose pylens for its read-only tools.
</dispatch>

<gates>
- The server's tools must be available before step 2, and the sub-project rule in `<inputs>` must hold.
- HEAD must be the reviewed head (step 1) before any tool reads the working tree.
- `module_count` of 0 stops the run; `over_budget` waits for the user's answer before any dispatch (step 4).
- A pylens row counts as evidence only after `check_citations` passes it in this session (step 7); a finding needs cited lines you opened yourself (step 8).
- You write exactly one file in the repository: `PYTHON-REVIEW.md` or `REFACTOR-PLAN.md` at its root. If that file already exists and you did not write it in this session, ask before overwriting. Everything else stays in your context. Edit and NotebookEdit are disallowed for this skill.
- The output file ships only when `check_citations` returns `passed: true` (step 11).
</gates>

<output>
One file at the repository root, shaped exactly by its template, plus a chat summary:

- the file path and the target reviewed;
- the mode and whether it was overridden;
- the gate result in one line;
- the three most consequential findings by id, one line each;
- dispatch count and dropped-citation count;
- anything unverified.
</output>

<handoff>
Say what was reviewed, what was left out and why, and that no code was changed (plus any `created_paths` the gate reported). Tell the user that every citation in the file passed `check_citations` in this session, and how to re-check after they edit it: the check is an MCP tool with no shell command, so they ask Claude Code, in a session started in this project with the plugin enabled, to call `check_citations` on `<file>`.
</handoff>

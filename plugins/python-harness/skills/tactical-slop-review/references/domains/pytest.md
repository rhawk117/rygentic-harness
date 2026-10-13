# Domain: pytest and Hypothesis

Load when `survey` lists `pytest` or `hypothesis`. These extend guide §10; the guide's points still apply.

## What bad pytest reads like to expert

- **Arrangement in the test body.** Arrangement belongs in fixtures. A test file with no fixtures is testing the current code rather than the behavior, which makes it brittle under refactoring.
- **Badly scoped fixtures.** A fixture lives in the narrowest owner that uses it (inside the test class when only that class uses it). Visibility and lifetime are separate decisions: a fixture inside a class does not have to be class-scoped.
- **Missing test classes** where scenarios share setup.
- **Parametrize without `pytest.param`.** Always `pytest.param(..., id='...')`; names as a tuple, values as a list, rows as tuples.
- **Unused fixture parameters** relied on for side effects. Use `@pytest.mark.usefixtures(...)`.
- **Inline imports of the code under test.** Needing one means the code is already designed wrong (import-time side effects, cycles).
- **Side effects or races** between tests.
- **Helpers used wrongly.** A repeated act-and-assert becomes a helper method on the class; a helper that only renames `pytest.raises` adds nothing.
- **Comments in tests.** Excessive comments signal bad test design rather than explaining it.
- **Mocking private steps.** Tests that patch private helpers or assert on internal calls mirror the implementation and break on every refactor. expert finds refactoring frequently breaks tests; this is the usual cause. Prefer fakes at real seams (the fake repository pattern) and assertions on observable outcomes.
- **Too many fixture arguments.** His lint caps a test at 4 arguments, 3 positional; bundle collaborators into a frozen dataclass fixture.
- **Unit and integration mixed.** Keep the separation strict.

## Placement

- Tests live in top-level `tests/`. Concept-owned test support (helpers, Hypothesis strategies, fixture plugins) lives beside the concept in `src/<package>/<concept>/tests/`, is loaded through `pytest_plugins` in a conftest, and is excluded from the wheel. Production code never imports test helpers.
- `@given` scenarios and scenario data sit as class attributes beside the test, not as constants at the top of the file.
- Local `conftest.py` for local availability; pytest plugins only for intentional broad sharing; never nested `pytest_plugins` as a scoping trick.

## Choosing the test

- Parametrize a small, intentional table of distinct scenarios, named boundaries and known regressions.
- Use Hypothesis when a property should hold across a broad input space. State the property before designing the strategy; keep representative examples and regression cases beside property tests.
- Exercise pure policy and transformation behavior directly; also verify that integrations actually invoke required protections.

## Evidence

- `map_python_calls`: `test_paths` per module shows which modules have tests at all.
- pylens tests question: which tests exercise which public functions, what they patch, where arrangement lives.
- `collect_python_facts` on test files: `comment` counts; `collect_python_facts` with `with_function_shapes` for `function_shape.parameters` (fixture-argument pressure).

---
name: design-tests
description: >-
  Designs the tests that give evidence for a Python contract: scenarios chosen by ranked risk,
  each aimed at public behavior and able to fail for a plausible broken implementation. Writes no
  files: it briefs the test-engineer agent to write and run the tests, strict XFAIL where the
  implementation is missing, and hands the scenario-test packet and test files to
  tactical-slop-review.
when_to_use: >-
  Use when tests are brittle, over-mocked or would still pass against a broken implementation,
  when behavior needs tests before it is implemented, or when the user wants to know which tests
  are worth writing. Typical requests are "what tests would prove this", "write scenario tests for
  X" and "these tests break on every refactor". Not for deciding the contract (enterprise-design),
  tests for data pipelines or analytical code (data-engineering) or reviewing finished code
  (tactical-slop-review).
argument-hint: "[behavior to test]"
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
  - mcp__plugin_python-harness_python-harness__collect_python_facts
  - mcp__plugin_python-harness_python-harness__map_python_calls
  - mcp__plugin_python-harness_python-harness__search_python_docs
  - mcp__plugin_python-harness_python-harness__read_python_docs
  - mcp__plugin_python-harness_python-harness__check_citations
disallowed-tools:
  - Edit
  - Write
  - NotebookEdit
---

# Design tests

<purpose>
Design evidence for observable Python contracts rather than maximizing test count. Work in **lead mode** for a testing request and **contributor mode** when `enterprise-design` or another skill supplies a contract packet.

This skill designs the scenarios, briefs the agent that writes them and reads its results. It writes no project files itself: `python-harness:test-engineer` writes the test files, because this skill denies Edit and Write. The scenario-test packet is a design record kept in the conversation, not generated workflow state.
</purpose>

<inputs>
- The service track hands to this skill from design-persistence, with its accepted persistence packet and the contract packet. It can also be invoked directly, by name or when the request matches the description.
- Paths below that start with `references/` are inside this skill's directory, `${CLAUDE_SKILL_DIR}`. Read now:
  - [Shared operating method](references/shared-method.md)
  - [Interview branches and decision gates](references/interview-and-gates.md)
  - [Scenario-test packet and worked example](references/test-packet.md)
- The plugin's MCP server names each tool `mcp__plugin_python-harness_python-harness__<tool>`; the steps below use the short names `survey` and `gate`. The project tools take no root argument: the project is the session's project directory (`CLAUDE_PROJECT_DIR`). If these tools are not available, stop: the server did not start. Tell the user to check the plugin in `/plugin` (its Errors tab) and the server in `/mcp`.
- Require:
  - the shared brief;
  - public contract files or a contract packet;
  - existing tests and repository test commands;
  - executable external systems and unavailable boundaries;
  - permitted test and fixture paths;
  - whether production implementation exists.
- Call `survey` for the project root, the Python version and the toolchain; the dispatches below rely on them.
- Read existing evidence before asking the user to restate it.
- Consume the accepted contract and persistence decisions from the shared brief. Record the scenario-test packet with the inline Markdown template in `references/test-packet.md`. If a required contract or persistence decision is unavailable, stop and return that blocker to the lead.
</inputs>

<workflow>
### Testing priorities

Apply these in order. When time or infrastructure is constrained, preserve the higher priority and report what remains:

1. **Business correctness:** reject implementations that violate invariants, transitions, authorization, duplicate semantics, or partial-success rules.
2. **Failure correctness:** distinguish expected rejection from dependency failure and prove state remains valid after failure.
3. **Boundary correctness:** verify use-case orchestration, repository-port behavior, transaction ownership, and adapter error translation at the narrowest realistic level.
4. **Regression value:** choose examples that catch plausible production defects and preserve intentional compatibility.
5. **Refactor resilience:** assert public results and committed state, not private methods, incidental calls, formatting, or non-semantic ordering.
6. **Clarity and determinism:** keep setup local, IDs descriptive, failures diagnosable, randomness seeded, and resources explicitly cleaned up.

Coverage percentage, test count, mocking convenience, and mirroring the implementation are never higher priorities than these.

### 1. Identify public promises

Run Interview Round 1. Separate documented behavior from accidental current output. Map meaningful promises to:

- accepted behavior;
- boundary behavior;
- duplicate behavior;
- expected rejection;
- partial success;
- dependency failure and recovery.

Pass Gate 1 only when each promise has an observable.

### 2. Choose test boundaries

Run Interview Round 2. Test pure rules without infrastructure. Use an integration boundary when a fake cannot establish adapter compatibility, transaction behavior, serialization, or a real service contract.

Use scenario fixtures with explicit ownership and teardown. A fixture owns only the state or resource it constructs. Do not make application startup a prerequisite for testing a domain rule.

Pass Gate 2 with a level and boundary rationale for every scenario.

Choose among these test kinds:

- **domain unit tests:** pure entity, value, and domain-service invariants;
- **use-case contract tests:** caller-visible results, errors, side effects, and orchestration through repository or gateway ports;
- **repository contract tests:** one reusable behavior suite that every repository adapter must satisfy;
- **adapter integration tests:** real serialization, queries, transactions, protocol compatibility, and external error translation;
- **end-to-end tests:** only critical paths whose behavior cannot be established at a narrower boundary;
- **characterization/regression tests:** existing behavior that must survive a fix or refactor;
- **property tests:** broad invariants where generated inputs add value;
- **concurrency/fault tests:** only when overlap, retry, cancellation, or partial side effects are contractual.

Do not create one test of every kind. Select the smallest set that can falsify the important contract.

### 3. Resolve semantics

Run Interview Round 3. Assert ordering only when callers rely on it. Otherwise assert membership, counts, mapping by identity, or another invariant. Keep expected values near the scenario. Parameterize equivalent behavior with descriptive IDs; keep materially different setup or recovery in separate tests.

Pass Gate 3 before authoring tests.

### 4. Select substitutes and optional tools

Prefer small fakes for meaningful behavior and mocks at interaction boundaries. Patch where a dependency is looked up, never the operation under test.

Inspect the target project's dependency manifest and lock before using optional libraries:

- **pytest-mock:** use when call interaction is itself contractual or its cleanup improves on manual patching. If absent, prefer `unittest.mock`, `monkeypatch`, or a fake unless the user approves a project-local dependency.
- **Hypothesis:** use when invariants over a broad input space are more useful than enumerated examples. If absent, provide the exact project-local dependency change as guidance; do not edit dependency files without approval.

There is no universal installation assumption. Each target project requires inspection.

When a substitute or an assertion rests on standard-library behavior for the project's Python version (`unittest.mock` semantics, `asyncio` cancellation, `contextvars`, `datetime` or `time` handling), dispatch `python-harness:pep-talk` with the question and the Python version from `survey`. Treat its return as cited facts: open the cited lines before relying on them.

### 5. Author scenario tests

Dispatch `python-harness:test-engineer` to write the test files, because this skill denies Edit and Write; the Test Engineer owns test files, and this skill owns the scenario-test packet. Brief it with the accepted contract and persistence decisions, the scenarios with their kinds, levels, substitutes and fixture owners, the permitted test and fixture paths, and the project root and Python version from `survey`. Tests must:

- target public behavior;
- use readable scenario fixtures;
- use descriptive parameter IDs;
- avoid private-state assertions;
- distinguish duplicate, rejection, partial success, and dependency failure;
- cover ordering only when semantic;
- carry a plausible broken implementation challenge.

For a use case with a repository boundary, separately decide whether evidence is needed for:

1. domain rules without I/O;
2. use-case behavior with a fake repository;
3. the adapter against its real compatible dependency;
4. parity between every adapter and the repository contract suite.

For **every test**, ask:

> What plausible broken implementation would still pass this test?

Strengthen the assertion or record the remaining gap. Do not add assertions about incidental calls merely to make the test look stricter.

### 6. Label tests awaiting implementation

When no implementation exists, have `python-harness:test-engineer` apply strict XFAIL with a reason naming the missing implementation:

```python
@pytest.mark.xfail(
    strict=True,
    reason="awaiting implementation: the production capability is not present",
)
```

Have it run the tests and report the XFAIL count. A broken import or fixture is not an acceptable expected failure; collect and execute far enough to reach the missing behavior.

### 7. Return design friction

If a test needs unrelated infrastructure, private state, string parsing, ambiguous identity, or incidental ordering, stop expanding fixtures. Return a friction packet to `enterprise-design` containing:

- the contract promise being tested;
- the setup or assertion that is impossible or misleading;
- the plausible defect that cannot be distinguished;
- the smallest interface decision that would resolve it;
- the gate to reopen.

Resume only after the revised contract is supplied.

### 8. Execute and report

Have `python-harness:test-engineer` run the smallest focused pytest command, then applicable integration and type checks, and read its result. Call `gate` for the repository's ruff, ty and pytest checks. Record the literal command, exit code, passed/failed/XFAIL counts, and what the run does not prove.

Complete the inline scenario-test packet with status `ready` only when design friction is empty. Each scenario's covered rule identifiers must resolve to the accepted contract, and every contract rule must have coverage. Return diagnostics to the relevant design gate.
</workflow>

<dispatch>
Each dispatch in steps 4, 5, 6 and 8 is one `Agent` call to one of these agents. Pass the project root and Python version from `survey` in the request; do not pass a `model`.

- agent: `python-harness:test-engineer`
- model: sonnet
- effort: high
- tools: Read, Grep, Glob, Bash, Edit, Write, `mcp__plugin_python-harness_python-harness__survey`, `mcp__plugin_python-harness_python-harness__collect_python_facts`, `mcp__plugin_python-harness_python-harness__map_python_calls`, `mcp__plugin_python-harness_python-harness__gate`, `mcp__plugin_python-harness_python-harness__search_python_docs`, `mcp__plugin_python-harness_python-harness__read_python_docs`

- agent: `python-harness:pep-talk`
- model: haiku
- tools: Read, Grep, Glob, `mcp__plugin_python-harness_python-harness__search_python_docs`, `mcp__plugin_python-harness_python-harness__read_python_docs`, `mcp__plugin_python-harness_python-harness__survey`, `mcp__plugin_python-harness_python-harness__check_citations`

If an agent type is not available, stop. The plugin's agents did not load: tell the user to check the plugin in `/plugin` (its Errors tab) or run `claude plugin validate` on it, then start a new session. Do not substitute another agent.
</dispatch>

<gates>
| Gate             | Required evidence                                                            | Return path         |
| ---------------- | ---------------------------------------------------------------------------- | ------------------- |
| Priority         | ranked contract risks and the highest-value test attacking each              | Test plan           |
| Promises         | scenario-to-contract map and observable for each promise                     | Interview Round 1   |
| Boundary         | test kind, level, substitute, fixture owner, and teardown                    | Interview Round 2   |
| Semantics        | meaningful ordering, wording, numeric, and serialization assertions          | Interview Round 3   |
| Defect challenge | each test names a plausible broken implementation it rejects                 | Test Engineer       |
| Executability    | collection succeeds and missing behavior is strict XFAIL, not import failure | Fixture/test author |
| Design friction  | no unresolved public-contract obstacle remains                               | `enterprise-design` |

Complete when:

1. ranked risks determine which tests exist and which are deferred;
2. every selected test has an explicit kind and reason;
3. important promises map to readable scenarios;
4. test levels and fixture ownership are explicit;
5. each test rejects a named plausible defect;
6. optional dependencies follow target-project evidence;
7. awaiting-implementation tests report strict XFAIL;
8. focused execution results and meaningful gaps are recorded;
9. interface friction has been returned through a decision gate rather than hidden by more mocking.

Edit, Write and NotebookEdit are disallowed for this skill: `python-harness:test-engineer` writes the test files.
</gates>

<output>
The completed scenario-test packet in the conversation, plus a chat summary:

- the ranked risks and the scenarios chosen, with the test files `python-harness:test-engineer` wrote;
- each gate and whether it passed;
- the focused test run and the `gate` result reported separately, with the literal command, exit code and passed/failed/XFAIL counts;
- limitations and checks not run;
- design friction returned, or a statement that none remains.
</output>

<handoff>
The next stage is tactical-slop-review, once code exists. Pass it the scenario-test packet and the test files, and say which gates passed, which are open, and which tests are strict XFAIL awaiting implementation.
</handoff>

---
name: enterprise-design
description: >-
  Turns business intent into a caller-facing Python contract before implementation: outcomes, a
  rule table, the architecture boundary, and the exact public types, signatures and error classes,
  shown to the user as declarations. Keeps partial success, duplicates, expected rejection and
  dependency failure distinct. Writes no project files and hands the contract packet to
  design-persistence.
when_to_use: >-
  Use when a Python feature has business rules, partial outcomes, ownership boundaries or expected
  failures that must be made concrete as types, signatures and errors before anyone implements
  it. Typical requests are "design the interface for X", "what should this return when some items
  fail" and "pin down the rules before we code it". Not for designing storage
  (design-persistence), designing the tests (design-tests) or a whole HTTP service
  (build-web-service).
argument-hint: "[what to design]"
paths:
  - "**/*.py"
  - "**/*.pyi"
  - "**/pyproject.toml"
allowed-tools:
  - Read
  - Grep
  - Glob
  - AskUserQuestion
  - mcp__plugin_python-harness_python-harness__survey
  - mcp__plugin_python-harness_python-harness__gate
disallowed-tools:
  - Edit
  - Write
  - NotebookEdit
---

# Enterprise design

<purpose>
Turn business intent into an executable caller-facing Python contract before implementation. Work in **lead mode** when this skill owns the outcome and interview; work in **contributor mode** when another skill supplies the shared brief and needs only the contract phase.

This skill writes no project files and dispatches nothing. The accepted contract and handoff are design records kept in the conversation, in the inline Markdown templates of the references, not generated workflow state.
</purpose>

<inputs>
- The service track hands to this skill from build-web-service, with its shared brief. It can also be invoked directly, by name or when the request matches the description.
- Paths below that start with `references/` are inside this skill's directory, `${CLAUDE_SKILL_DIR}`. Read now: `references/shared-method.md` (shared operating method), `references/architecture-boundaries.md` (architecture boundaries), `references/interview-and-gates.md` (interview branches and decision gates), `references/contract-packet.md` (contract packet and worked example) and `references/implementation-handoff.md` (implementation handoff).
- The plugin's MCP server names each tool `mcp__plugin_python-harness_python-harness__<tool>`; the steps below use the short names `survey` and `gate`. The project tools take no root argument: the project is the session's project directory (`CLAUDE_PROJECT_DIR`). If these tools are not available, stop: the server did not start. Tell the user to check the plugin in `/plugin` (its Errors tab) and the server in `/mcp`.
- Start from the shared brief. Require:
  - the intended operation and caller;
  - one accepted example and one consequential rejection;
  - inspected repository evidence or an explicit statement that none exists;
  - paths the design may create or change;
  - compatibility and verification constraints.
- Call `survey` for the project root, the Python version and the toolchain when the declarations or the verification depend on them.
- In contributor mode, return missing questions to the lead instead of opening a second project interview.
- If required evidence is unavailable, stop rather than creating a freehand substitute.
</inputs>

<workflow>
### 1. Establish vocabulary and outcomes

Run Interview Round 1 from the question tree. Define actors, operation names, domain terms, and caller-visible outcomes. Keep these outcomes separate:

- **partial success:** the operation completes with accepted and non-accepted item results;
- **duplicate operation or item:** the caller can distinguish a repeat from invalid input;
- **expected rejection:** a business rule declines an item without pretending infrastructure failed;
- **dependency failure:** an unavailable or failed external boundary prevents reliable completion and is represented by a concrete exception.

Do not collapse duplicates into rejection or dependency failure into an empty result. Pass Gate 1 before designing signatures.

### 2. Expose rules and ownership

Run Interview Rounds 2 and 3. Produce a rule table with preconditions, postconditions, side effects, retry meaning, transaction ownership, concurrency assumptions, and compatibility constraints. Every material answer must change an observable type, signature, result, error, or documented rule.

Use a protocol only for a meaningful boundary with multiple implementations, a useful test substitute, or a caller-owned dependency. Prefer a concrete function, class, data class, enum, or value object otherwise.

Pass Gates 2 and 3 before defining components.

### 3. Define the architecture boundary

Name each required role before naming classes:

- **domain model:** entities and value objects that own intrinsic invariants;
- **use case:** one application operation coordinating domain decisions and boundaries;
- **domain service:** a stateless business rule spanning multiple domain objects, used only when no entity naturally owns the rule;
- **repository port:** a domain-facing persistence boundary with methods derived from the use case, not generic CRUD;
- **adapter:** infrastructure code implementing a port and translating external failures;
- **input/output model:** caller-facing immutable values crossing the use-case boundary.

Do not use “service” as a generic suffix. State whether it is an application use case, domain service, or infrastructure adapter. Dependencies point inward: the use case depends on domain types and ports; adapters depend on ports; domain types do not import frameworks, databases, or clients.

Produce a boundary table with responsibility, state ownership, dependencies, public operations, transaction ownership, and failure translation. Pass Gate 4 before proposing files.

### 4. Show interfaces and signatures to the user

Before delegation, present the actual proposed Python declarations in the conversation, not only a prose packet. Include every public type, constructor, function, method, protocol member, return type, and concrete exception needed by the representative caller.

Use compilable declarations such as:

```python
class ImportOrders:
    def __init__(self, orders: OrderRepository) -> None: ...

    def execute(self, request: ImportOrdersRequest) -> ImportResult: ...


class OrderRepository(Protocol):
    def find_existing(self, order_ids: set[OrderId]) -> set[OrderId]: ...

    def add(self, order: Order) -> None: ...
```

Explain why each boundary exists, who constructs it, and which side owns transactions and error translation. Ask for a decision only where an alternative changes caller behavior or dependency ownership.

Pass Gate 5 when the user can review the exact API surface and the representative call has no hidden steps.

### 5. Author the contract

This skill owns the contract phase. Use the shared brief, repository evidence, permitted paths, and acceptance criteria to return:

- importable public types;
- exact function, constructor, protocol, and method signatures;
- a concrete use-case entry point;
- the boundary table and dependency direction;
- repository operations derived from business needs;
- business-rule documentation;
- concrete error classes and their conditions;
- normal, partial-success, duplicate, rejection, and dependency-failure usage;
- side-effect and ownership constraints;
- unresolved choices that block tests or implementation.

Complete the inline contract packet with status `ready` only after the interface has been shown to the user and consequential choices are accepted. Pass the contract gate before tests consume it.

Explain Python-specific choices for a highly technical developer with intermediate-to-advanced Python knowledge. Discuss semantics and trade-offs, not elementary syntax.

### 6. Validate caller ergonomics

Run the caller-ergonomics interview. Walk the representative caller through normal use and expected recovery using the declarations already shown. The caller must not inspect exception strings, private attributes, or undocumented sentinel values.

Pass Gate 6 only when the examples can express every required outcome without hidden coordination.

### 7. Delegate executable expectations

Invoke `design-tests` in contributor mode with the contract packet and shared brief once the persistence decision exists or the brief records that there is no durable state. The Test Engineer owns scenario tests. Contract tests that precede implementation use:

```python
@pytest.mark.xfail(
    strict=True,
    reason="awaiting implementation: <missing domain capability>",
)
```

Strictness matters: the expected absence reports as XFAIL, while an unexpected pass fails and forces the marker to be removed deliberately.

### 8. Treat test friction as design feedback

Review the test-friction packet before implementation. Return to the relevant gate when tests require unrelated infrastructure, private-state assertions, ambiguous outcome identity, incidental ordering, or broad exception matching. Change the interface first when the friction exposes a contract defect.

The worked example changes `Iterable[OrderDraft]` to `Sequence[OrderDraft]` and adds `input_index` because duplicate and rejection results must identify the original occurrence without consuming a one-shot iterator twice.

### 9. Resolve the design handoff

Complete the inline handoff template in `references/implementation-handoff.md` after the contract, persistence, and scenario-test decisions are complete. Include each required input, permitted relative path, required output, acceptance criterion, unresolved decision, and verification limitation. The handoff is a design record for a later implementation phase; do not select or dispatch an agent here.

### 10. Verify and report

Call `gate` for the repository's ruff, ty and pytest checks, and run the focused contract checks, type checks, and compatibility checks that the repository actually provides through it; name any check the gate cannot run as a limitation. Distinguish:

- design inspection;
- manual design walkthrough;
- implementation-backed test success;
- strict XFAIL awaiting implementation.

Never call an XFAIL-only suite an implemented success.
</workflow>

<dispatch>
This skill dispatches no agent. Scenario tests are designed in step 7 by invoking the skill named there, and the handoff in step 9 selects no agent.
</dispatch>

<gates>
| Gate             | Required evidence                                                                            | Return path            |
| ---------------- | -------------------------------------------------------------------------------------------- | ---------------------- |
| Operation        | caller, operation, accepted example, rejected example, vocabulary                            | Interview Round 1      |
| Rules            | invariants and separate partial, duplicate, rejection, dependency outcomes                   | Interview Round 2      |
| Boundaries       | dependency, transaction, state, overlap, retry, compatibility ownership                      | Interview Round 3      |
| Architecture     | each model, use case, domain service, repository, and adapter has one defined responsibility | Boundary definition    |
| Interface review | exact Python declarations and dependency direction are shown to the user                     | Interface presentation |
| Ergonomics       | normal and recovery examples need no hidden coordination                                     | Caller review          |
| Testability      | scenario tests observe public behavior and identify a plausible broken implementation        | Contract phase         |
| Handoff          | the design handoff names the capability and has no unresolved blocker                        | Lead                   |

The design phase is complete only when:

1. the user has been shown the exact proposed public declarations;
2. the contract packet contains public types, signatures, architectural boundaries, rules, errors, ownership, examples, and contract tests;
3. partial success, duplicate, expected rejection, and dependency failure are distinct contract elements;
4. the scenario-test packet maps every important promise to evidence;
5. all test friction has been resolved or recorded as blocking;
6. awaiting-implementation tests are strict XFAIL;
7. the design handoff names the required capability and stops before agent dispatch.

Edit, Write and NotebookEdit are disallowed for this skill: it creates no project file.
</gates>

<output>
The completed contract packet and implementation handoff in the conversation, plus a chat summary:

- the operation, the caller and the contract's public declarations;
- each gate and whether it passed;
- design inspection, manual walkthrough, implementation-backed success and strict XFAIL reported separately, with the `gate` result;
- limitations and checks not run;
- unresolved decisions, or a statement that none block the handoff.
</output>

<handoff>
The next stage of the service track is design-persistence. Pass it the accepted contract packet and the implementation handoff, and say which gates passed, which are open, and that no code or file was changed. A stage this workflow already ran in contributor mode with an accepted packet is complete, so hand to the first stage that has not run.
</handoff>

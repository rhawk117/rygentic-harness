# Judging facts into findings

You, the primary, hold the rules; pylens and the `python-harness` tools hold none. This file is how you turn their facts into findings expert would sign. Read it before the first finding.

## The lenses

Organize your reasoning per module through these eight lenses. They are how you think, not dispatch units: every lens draws on the same facts.

| Lens | Sources | Facts to consult |
| --- | --- | --- |
| 1. Types and state space | philosophy (review spine), guide §4, smells: typing | `dataclass`, `classvar`, `inline_annotated`, `any_annotation`; pylens: state, data shapes |
| 2. Failure contracts | guide §6, philosophy (exceptions, overrides) | `try_block`, `exception_base_handler`, `raise_without_cause`; pylens: failure paths |
| 3. Ownership and protection | guide §7, smells: async, hidden state | `module_level_call`, `mutable_module_global`, `global_statement`; pylens: resources, callers |
| 4. Behavior placement and interface | guide §2 and §3, smells: structure | `staticmethod`, `classmethod`, `private_class`, `handwritten_init`, `post_init`; calls: public symbols, references |
| 5. Configuration and dependency reuse | guide §4 and §5 | `os_environ`; pylens: configuration, dependencies, duplication |
| 6. Control flow and complexity | smells: control flow, philosophy (complexity budget, tripwires) | `else_branch`, loop facts, gate rule statistics, calls `max_parameters`/`max_function_statements`; `function_shape` via `collect_python_facts` with `with_function_shapes` |
| 7. Organization, naming, platform | guide §8, §9, §11 | survey layout; calls: fan-in, fan-out, instability; reading |
| 8. Tests | guide §10, `domains/pytest.md` | calls: `test_paths`; pylens: tests |

## From fact to finding

1. **Confirm.** Open the cited lines yourself before writing a finding. pylens runs on a lighter model; a fact you have not seen is a fact you do not have. If the code does not say what the fact says, drop it and note the discrepancy in Run facts.
2. **Decide whether it matters here.** A smell in the catalog is a candidate. Ask the guide's review question for that section and philosophy's coupling and testing questions. Mode matters: a broad public surface is a finding in a library, usually not in an application.
3. **Do not report what the gate reports.** If ruff or ty flags it, it is in the gate result; do not restate it. Lint limits are the exception only when you can name the cohesive subset that wants extracting (philosophy: tripwires).
4. **Group.** Repeated instances of one design problem become one finding with every location listed.
5. **Find the root.** Several symptoms with one cause (a status string compared in five places, a ritual repeated by every caller) are one finding about the cause.
6. **Recommend the smallest coherent improvement**, shaped as interface stubs (Python signatures) for the new structure. Prefer the change that makes the bug unwritable over the change that adds a check.

## Classification

Every finding carries one kind and one certainty.

| Kind | Meaning |
| --- | --- |
| correctness defect | Behavior is wrong or can be made wrong by a normal caller today |
| maintenance problem | Behavior is right, but changing, testing or using the code correctly is costlier than it needs to be |
| preference deviation | Departs from expert's conventions without a concrete cost beyond inconsistency |

| Certainty | Meaning |
| --- | --- |
| observed | You read the code that exhibits it |
| derived | It follows from observed facts by reasoning you state |
| heuristic | A pattern that usually signals the problem; say what would confirm it |

Order findings by consequence, not by checklist position. A module with only preference deviations gets one short line, not a section.

## Finding format

Exactly this shape, so citations can be checked and runs compared:

```
#### F<n>: <claim in a short sentence>

- Location: <path.py:line[-end]> `<quote from that line>`
- Kind: <correctness defect | maintenance problem | preference deviation>
- Certainty: <observed | derived | heuristic>
- Observed: <what the code does, citing facts>
- Consequence: <what goes wrong, for whom, when>
- Principle: <guide section or philosophy heading> and the smallest coherent improvement
- Compatibility: <behavior or API change the improvement requires, or "none">
- Verify: `<command or test that would prove the improvement>`
```

Additional locations go on further `- Location:` lines. Every location is a citation in the `path.py:line` form followed by a backticked quote of that line, because `check_citations` checks both.

## What not to do

- Do not invent findings to fill the template. A clean module gets "No findings" and a one-line reason.
- Do not recommend comments, docstrings (outside framework metadata), `Raises` sections, `noqa` for limits, `match`, or `else`.
- Do not recommend new dependencies the project does not have unless the finding is that it hand-rolls what a dependency it already has provides.
- Do not mark a heuristic as observed.
- Do not edit code. Ever.

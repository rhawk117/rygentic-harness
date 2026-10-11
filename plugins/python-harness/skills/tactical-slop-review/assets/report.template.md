# Python review: {{TARGET}}

## Run facts

- Target: {{codebase PATH | branch BRANCH against BASE | PR #N (HEAD...BASE)}}
- Mode: {{library | application}} (inferred {{library | application}} from {{survey reasons}}{{; overridden to application/library at the user's request}})
- Gate: ruff config {{repository | fallback | defaults}}; ruff check {{passed | failed: rule counts}}; ruff format {{passed | failed}}; ty {{passed | failed: N diagnostics}}; pytest {{passed | failed | not run: reason}}
- Surface: {{N}} modules, {{N}} lines, {{N}} clusters; pylens dispatches: {{wave 1}} + {{wave 2}}
- Mechanical facts: {{the counts that mattered, for example "staticmethod 1, try_block 3, mutable_module_global 1"}}
- Gate leftovers: {{created_paths from the gate, or "none"}} (left in place)
- Citations: {{N}} checked by `check_citations`; {{N}} pylens facts dropped because their citation failed
- Unverified: {{what this review did not establish, or "nothing"}}

## Summary

{{Two to five sentences: the overall shape, the most consequential problems, and what is in good shape. Plain words; no padding.}}

## Modules

### {{path/to/module.py}}

**Maintenance cost.** Cost of change: {{...}} Testability: {{...}} Prevention or handling: {{...}}

**Proposed shape**

```python
{{interface stubs: signatures and frozen dataclass fields for the structure that removes the findings, bodies as ...}}
```

```mermaid
flowchart LR
  {{plain single-line labels, no HTML, no em dashes: the dependency shape after the change}}
```

#### F1: {{claim in a short sentence}}

- Location: {{path.py:line}} `{{quote of that line}}`
- Kind: {{correctness defect | maintenance problem | preference deviation}}
- Certainty: {{observed | derived | heuristic}}
- Observed: {{what the code does, citing facts}}
- Consequence: {{what goes wrong, for whom, when}}
- Principle: {{guide section or philosophy heading}}; {{the smallest coherent improvement}}
- Compatibility: {{behavior or API change required, or "none"}}
- Verify: `{{command or test that would prove the improvement}}`

## Clean modules

- {{path}}: {{one-line reason it needs nothing}}

## Not reviewed

- {{path or package}}: {{outside the narrowed scope | unparsable | over budget}}

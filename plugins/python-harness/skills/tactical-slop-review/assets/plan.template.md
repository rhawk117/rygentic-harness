# Refactor plan: {{TARGET}}

## Intent

{{What this refactor achieves, in terms of the classes of bugs that become unwritable and the changes that become cheaper. Two to four sentences.}}

```mermaid
flowchart LR
  {{target dependency shape; plain single-line labels, no HTML, no em dashes}}
```

## Context

- Mode: {{library | application}} (inferred {{...}} from {{survey reasons}}{{; overridden at the user's request}})
- Gate today: {{ruff check, ruff format, ty, pytest results; config source}}
- Findings this plan resolves:
  - F1 {{claim}}: {{path.py:line}} `{{quote}}`
  - F2 ...

## Invariants

These hold after every step, not only at the end:

- {{Public behavior that must not change, unless listed under a step's Compatibility}}
- The project gate passes: `{{exact ruff check command}}`, `{{exact ruff format command}}`, `{{exact ty command}}`, `{{exact pytest command}}`
- {{Any further invariant: no new dependencies, public import paths kept, ...}}

## Steps

### Step 1: {{name}}

- Resolves: {{F-numbers}}
- Depends on: {{none | Step N}}
- Change: {{what moves where, in one or two sentences}}

```python
{{interface stubs for the new shape}}
```

- Compatibility: {{none | the API or behavior change and who it affects}}
- Acceptance: {{a check a machine can run: a named test that must exist and pass, a grep that must return nothing, a command that must exit 0}}
- Verify: `{{exact command}}`

## Non-goals

- {{What this plan deliberately leaves alone and why}}

## Risks

- {{Risk}}: {{how it would show up}}; handling: {{what the executing session does}}

<!-- Always-on repo-wide instructions. Read by every session, so every line costs.
     Place at AGENTS.md (Copilot native) or .github/copilot-instructions.md or CLAUDE.md.
     Target under 200 lines. Delete any section you do not have a concrete answer for. -->

# Project

One or two sentences on what this is, only if the name and README do not make it obvious.

## Commands

Commands the agent cannot guess from the repo. Include the ones that are unusual, not the ones
a package manager would reveal.

- Test: `<command>`
- Lint: `<command>`
- Typecheck: `<command>`
- Local dev: `<command>`

## Conventions that differ from defaults

Only conventions a competent engineer would get wrong by default. Anything a linter enforces
belongs in the linter, not here.

- <rule>
- <rule>

## Boundaries

Directories or files the agent must not modify, and why.

- <path>: <reason>

## Gotchas

Non-obvious behavior that has already bitten someone.

- <gotcha>

## References

Pitch each one. State what it contains and when to read it.

- `<path>`: <what it covers> - read when <condition>.

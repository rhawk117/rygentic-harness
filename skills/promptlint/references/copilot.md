# Target: GitHub Copilot

Copilot spans three surfaces with different prompt shapes. Identify the surface first; it changes the deliverable more than anything else. One cross-cutting fact: Copilot routes to different underlying models (GPT and Claude families, user-configurable), so keep prompts model-agnostic — clear structure and explicit criteria over any model-specific tricks. XML-tagged sections parse well across current models and remain the house format; front-load the objective either way.

## Surface: Copilot CLI (agentic session)

Closest to Claude Code — an agentic loop with file and shell tools. The house architecture applies fully: objective, context, discovery, constraints, verification, output.

- **Persistent config layers exist**: `copilot-instructions.md` (repo and/or `~/.copilot`) plus custom agent profiles (`.agent.md`). Don't restate what lives there; reference it. If the user runs custom worker agents, ask whether the prompt targets a specific profile — a delegation-only planner needs a different action default than an engineer profile with write tools.
- **Verification gate is still the core.** Exact commands, expected results, evidence in the report.
- **GitHub's structural advice applies**: start with the broad goal, then list specific requirements; provide example inputs/outputs where format matters; break large asks into sequenced smaller ones rather than one omnibus instruction.

## Surface: Copilot Chat (IDE)

Interactive and context-scoped — the prompt is one turn in a conversation, not a mission brief.

- **Context comes from the workspace, not the prompt.** Tell the user: open the relevant files, close irrelevant ones, highlight the code in question, use `@workspace` (VS Code) / `@project` (JetBrains) for repo-wide questions. The prompt should name exact functions/files, never "this code" unqualified.
- **Decompose.** One well-scoped request per message beats a compound ask; sequence follow-ups. Generated deliverable for chat: a short primary prompt plus, when the task is multi-step, the ordered follow-up prompts.
- **Examples pull hard here**: example input → expected output pairs, or "write tests first, then ask for an implementation that passes them."
- Keep chat prompts compact — a few sentences to a short structured block. Full six-section architecture is usually overkill; objective + constraints + verification ask is the common shape.

## Surface: Copilot coding agent (async, issue → PR)

The prompt is an issue body the agent picks up unattended. GitHub's guidance: treat the issue description as an AI prompt.

Required shape:

- **Problem** — clear description of the work and why.
- **Acceptance criteria** — checkable list defining done, including whether tests are expected and which framework.
- **File guidance** — where to work (paths); the agent can search, but pointers cut wasted exploration.
- **Out of scope** — explicit, since nobody is watching to course-correct.
- **Verification** — commands the agent (and CI) will run; note `copilot-setup-steps.yml` to the user if deps need preinstalling.

Fit matters — steer the user when the task is wrong for this surface: good fits are bug fixes, test coverage, UI tweaks, docs, tech-debt cleanup in a well-tested repo. Poor fits are cross-repo refactors, production-critical changes, and security-sensitive work — flag it and suggest an interactive surface instead. Keep tasks small and self-contained; two small issues beat one large one. Iteration happens via PR review: batch comments in one review, mention `@copilot` to request changes.

## Pitfalls specific to this target

- Underlying model varies per user config — never rely on model-specific behaviors (thinking triggers, self-verification habits). Make every expectation explicit in the prompt.
- IDE chat quality depends on workspace state the prompt can't control — always emit the "attach when running" notes (which files to open/highlight).
- The coding agent runs unattended in CI — missing acceptance criteria don't get caught until PR review, so vagueness is expensive. Be concrete or downscope.

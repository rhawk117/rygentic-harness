# Surfaces

What carries between hosts, what does not, and which mechanisms are not skills at all.

Details here reflect documentation current when this skill was written, and several of these
mechanisms are in preview. Check before building anything load-bearing on them — and prefer
`skilleng doctor --probe-hooks`, which answers the host questions empirically.

## Contents

- [What is portable](#what-is-portable)
- [Install locations](#install-locations)
- [Copilot: the other mechanisms](#copilot-the-other-mechanisms)
- [Triggering is per surface](#triggering-is-per-surface)
- [Copilot cloud agent](#copilot-cloud-agent)
- [Claude Code specifics](#claude-code-specifics)
- [When no host CLI is available](#when-no-host-cli-is-available)

## What is portable

The skill artifact itself is fully portable. Copilot implements the same Agent Skills
specification: same frontmatter, same limits (name 64, description 1024, compatibility 500),
same three-level progressive disclosure, same 500-line body guidance. A SKILL.md that lints
here works on both hosts unchanged.

The harness is portable because it depends on exactly four things both hosts have: headless
CLI invocation, hook-based instrumentation, spec-compliant skill install, filesystem outputs.
Anything else is an adapter concern and belongs in `skilleng/runners/`, not in the core.

| Concern | Claude Code | Copilot CLI |
|---|---|---|
| CLI | `claude -p` | `copilot -p` |
| Config dir override | `CLAUDE_CONFIG_DIR` | `COPILOT_HOME` |
| Hook config | settings, PascalCase events | `hooks/*.json`, lowerCamelCase events |
| Explicit invocation | `/skill-name` | `/skill-name` |
| Subagents | Task tool, `.claude/agents/` | custom agents, `.github/agents/*.agent.md` |

Claude Code also offers `--output-format stream-json`. This harness deliberately does not use
it: one detector across both hosts is worth more than a slightly richer one on a single host,
and a shared code path gets exercised twice as often. Building the Copilot adapter first is
what forces that discipline — Copilot offers no transcript to scrape, so the temptation to
take the shortcut never arises.

## Install locations

| Scope | Claude Code | Copilot |
|---|---|---|
| Project | `.claude/skills/<name>/` | `.github/skills/`, `.claude/skills/`, `.agents/skills/` |
| Personal | `~/.claude/skills/<name>/` | `~/.copilot/skills/`, `~/.agents/skills/` |

`.claude/skills/` is read by both, so a repo that wants one location can use it. Org- and
enterprise-level skill distribution on Copilot was announced as coming rather than shipped;
verify before promising it.

## Copilot: the other mechanisms

A skill is often not the right artifact. Copilot has several injection mechanisms with
genuinely different triggering, and each needs a different kind of evaluation:

| Mechanism | Location | Fires | How to evaluate it |
|---|---|---|---|
| Skill | `.github/skills/<name>/` | model-invoked, or `/name` | trigger rate — this harness |
| Path instructions | `.github/instructions/*.instructions.md` | `applyTo` glob match | **glob coverage**, not trigger rate |
| Repo instructions | `.github/copilot-instructions.md` | always | token cost and interference |
| `AGENTS.md` | anywhere; nearest wins | always | token cost and interference |
| Custom agent | `.github/agents/*.agent.md` | selected, ≤30k char body | task success under tool restriction |
| Hook | `.github/hooks/*.json` | deterministically, on events | it either fired or it did not |

Two consequences worth acting on. Path instructions are selected by glob, so the right test is
whether the pattern matches the files it should and nothing else — a completely different
evaluation that this harness does not perform. And anything currently written as a rule the
model might ignore ("always run the formatter after editing") is usually better expressed as a
`postToolUse` hook: if the evals show a rule being dropped, converting it to a hook is a
stronger fix than rewording it. Hook timeouts fail open, so hooks are a productivity
mechanism, not a security boundary.

## Triggering is per surface

A Copilot skill can run under the CLI, VS Code agent mode, the cloud agent and code review,
and the surrounding instruction mechanisms differ between them — path-specific instructions
apply to the cloud agent and code review but not to Chat on github.com; prompt files are
effectively VS Code only. A description tuned on the CLI can under-trigger in code review.

Trigger rate is therefore a matrix, not a number. Record `--surface` on every run so
provenance carries it, and do not generalise a CLI measurement to code review without saying
that is what you are doing.

## Copilot cloud agent

Runs on GitHub Actions with a 59-minute hard limit. Environment setup goes in
`.github/workflows/copilot-setup-steps.yml`, and the job must be named `copilot-setup-steps`
or it is ignored. Only `.github/hooks/*.json` is read from the repo — user-level hooks do not
apply — and non-interactive mode means a hook decision of "ask" is treated as "deny".

Outbound network is governed by a default-on allowlist, and blocked requests append a warning
to the pull request rather than failing. See `references/security.md`.

It is also the natural place to run evals at scale: one Actions job per eval per arm gives
real isolation and parallelism for free, with results uploaded as artifacts. That is a runner
worth adding, and it lives beside the CLI adapters rather than replacing them.

## Claude Code specifics

Skills load from project and personal directories and from plugins. Cloud and browser-hosted
sessions do not execute bundled scripts, so a script-dependent skill degrades to
non-functional documentation there — declare that in `compatibility` and keep the fallback
path in prose.

## When no host CLI is available

`lint`, `package` and the security report need only Python. Everything that produces a
measurement needs a host, and when none is present the honest output is "not measured" — not
a zero, and not an estimate. Say which one you are giving.

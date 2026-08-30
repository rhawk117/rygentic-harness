# Explorer prompts

Two dispatch prompts for step 2. Fill every `{placeholder}` before dispatching; both explorers run in parallel on the model the user chose in step 1. Explorers are read-only — they report, you write.

Placeholders used by both prompts:

- `{repo_root}` — absolute path to the repository under analysis.
- `{platforms}` — the platform answer from step 1 (Claude Code, GitHub Copilot, or both), so the explorer knows which existing instruction files matter most.

## Explorer A — toolchain and verification

```text
You are a read-only explorer in {repo_root}. Establish how this repository is built, tested, and verified. Report facts with file-path evidence; do not write or modify anything.

Find, in priority order:

1. CI workflows (.github/workflows/*.yml or the platform equivalent): every command CI actually runs, verbatim, with the file that runs it. CI is ground truth — when it disagrees with README claims, report both and flag the conflict.
2. The command runner and entry points: Makefile/justfile targets, package.json scripts, pyproject/uv, cargo, gradle. Which wrapper do commands go through (uv run, pnpm, make)?
3. Test, lint, format, and typecheck invocations, with real flags. Run a command only when it is obviously safe, fast, and read-only (a --help, a --version, a lint on one file); mark everything you did not run as inferred.
4. Validation scripts and git hooks the repo carries (scripts/, .pre-commit-config.yaml, husky).
5. Anything a fresh agent must do before its first edit (bootstrap step, env file, submodule, codegen).

Report as one <report> element:

<report explorer="toolchain">
  <verified>
    <finding source="path/to/file:line">the exact command or fact</finding>
  </verified>
  <inferred>
    <finding source="path/to/file:line" rests-on="what the inference depends on">the probable command or fact</finding>
  </inferred>
  <conflicts>README or docs claims that disagree with CI, if any</conflicts>
</report>

A command is verified only if you ran it or extracted it verbatim from CI or hook config. Everything else is inferred. An empty section stays present and empty.
```

## Explorer B — conventions and structure

```text
You are a read-only explorer in {repo_root}. Establish this repository's layout, conventions, and existing agent instructions. Report facts with file-path evidence; do not write or modify anything.

Find, in priority order:

1. Layout that is NOT obvious from the top-level listing: where handlers/entry points/generated code actually live. Skip anything a directory listing already explains.
2. Git conventions from history: run git log --oneline -30 and report the observed commit-message convention (conventional commits? scopes? tense), not the one a doc claims.
3. Existing instruction files for {platforms} and any other agent tooling: AGENTS.md, CLAUDE.md, .github/copilot-instructions.md, cursor/windsurf/cline rules. Quote the rules worth keeping verbatim, with their source path; note rules that contradict what you can see in the repo today (those are stale, and the synthesizer decides).
4. Style deviations from ecosystem defaults, each with the config or code evidence that proves it is deliberate (a linter setting, a repeated pattern), plus the why when a comment or doc states one.
5. Testing patterns: where tests live, naming, fixtures, markers, anything a new test must conform to.
6. Boundary signals: generated directories, migration dirs, vendored code, CODEOWNERS-guarded paths — anything an agent should not touch or should ask about first.

Report as one <report> element:

<report explorer="conventions">
  <verified>
    <finding source="path/to/file:line">the fact</finding>
  </verified>
  <inferred>
    <finding source="path/to/file:line" rests-on="what the inference depends on">the probable fact</finding>
  </inferred>
  <keep-worthy>
    <rule source="path/to/existing/instruction-file">verbatim rule worth migrating</rule>
  </keep-worthy>
</report>

A convention is verified only when config or repeated code evidence backs it; a single occurrence is inferred. An empty section stays present and empty.
```

## Consuming the reports

Trust order when reports disagree: CI workflow files, then config files, then code patterns, then prose docs. Only `<verified>` findings feed the Commands section of AGENTS.md unmarked; `<inferred>` content enters prefixed `(unverified)` or not at all. `<keep-worthy>` rules go through the step 4 merge, where anything contradicting a verified finding is dropped and listed as dropped.

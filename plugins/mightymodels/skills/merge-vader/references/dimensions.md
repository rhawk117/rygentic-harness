# Review dimensions

Checklists for the four dimensions, with severity anchors and a scout question bank per dimension. Read top to bottom once per review; the point is priming your diff read, not box-ticking. Repository reality overrides any item here: a repo with no docs directory has no doc drift to find, and saying so in one line beats inventing findings.

Contents:

1. Security
2. SDLC regressions
3. Quality and maintainability
4. Documentation drift

## 1. Security

What counts: defects an attacker can use, secrets, and weakened defenses. The unit of analysis is the trust boundary: where does data from outside (users, other services, files, environment) first touch the changed code, and which sink does it reach?

Diff-visible signals:

- String-built SQL, shell commands, or filesystem paths that interpolate a parameter (f-strings, concatenation, format calls, template literals). Parameterized before, concatenated now, is the classic regression.
- Deserialization of external data: pickle, yaml.load without SafeLoader, eval, exec, and their equivalents in other ecosystems.
- Auth surface: any hunk touching middleware, decorators, route registration, permission checks, session or token handling. A route registered without the guard every sibling route has is a finding even before an exploit is written out.
- Weakened comparisons: `hmac.compare_digest` replaced by `==`, constant-time checks removed.
- TLS and crypto: `verify=False`, `InsecureSkipVerify`, MD5 or SHA1 in an auth context, static IVs or salts, home-rolled primitives.
- Secrets: literals shaped like keys, tokens, passwords, or connection strings, in code, tests, fixtures, or CI. A recognizable prefix (`sk_live_`, `AKIA`, `ghp_`, `xoxb`, `BEGIN RSA`) plus entropy is enough to flag.
- Suppression markers added: `nosec`, gosec-class `nolint`, eslint-disable on security rules, semgrep ignore. Unexplained means High.
- Logging: secrets or PII flowing into log lines; stack traces returned to callers.

History check, always: grep `git log -p <merge-base>..<branch>` for secret shapes. A credential added in commit 3 and deleted in commit 5 merges anyway, inside the history. Severity is Critical and the fix is rotation plus history rewrite, not deletion.

Scout question bank:

- "List every route registered in `<router file>` and whether each is wrapped by `<guard>`. file:line."
- "Show the 5 lines preceding each call to `<sink function>` at `<call sites already located>`."
- "Grep `<paths>` for `sk_live_|AKIA|ghp_|xoxb|BEGIN RSA` and report file:line only; do not print the matched values."
- "What version does the lockfile resolve `<new dependency>` to, and does the manifest pin it?"

Severity anchors: reachable injection or a committed secret is Critical. A guard missing on one endpoint among guarded siblings: High, or Critical when the endpoint exposes data or mutation. Unexplained suppression marker: High. Sensitive data into logs: High or Medium by sensitivity.

## 2. SDLC regressions

What counts: changes that weaken the pipeline's ability to catch the next defect. The shipped code can be perfect and the branch still fails this dimension. The net is part of the product.

Diff-visible signals:

- Tests: files deleted, cases deleted, `skip` or `xfail` or `.only` or `fdescribe` or `@Disabled` added, assertions weakened (`assertEqual` becomes a not-None check), timeouts raised or retries added around flaky assertions.
- CI config: steps removed or commented out, `continue-on-error` or `allow_failure` added, `|| true` appended, matrix entries dropped, triggers narrowed (a growing `paths-ignore`), a job renamed. A renamed job silently unbinds from branch-protection required checks, and the GitHub-side setting is invisible from the repo, so that lands as `UNKNOWN-BLOCKED` plus a condition.
- Gates: coverage fail-under lowered, lint or type strictness reduced (`strict: false`, `noImplicitAny: false`, a shrunken select list), pre-commit hooks removed.
- Build and release: version pins loosened, lockfile out of sync with its manifest, Dockerfile moved to `latest`, signing or SBOM steps dropped.
- Migrations: schema change without a migration, migration without a rollback.

Scout question bank:

- "On `<base>`, show the steps of `<workflow file>` in order, with any `continue-on-error`, `fail-under`, or `allow_failure` values. file:line."
- "List test files referencing `<module>`. file:line."
- "Show `<coverage or lint config file>` as it exists on `<base>`."
- "Run `<one targeted test file>` and report the tail of the output." (one run, narrowest scope)

Severity anchors: a deleted or skipped test without a stated replacement, and any weakened CI gate: High. New logic with no tests at all: Medium, because it never had a net; distinguish that from removing one. Renamed CI job: High finding phrased as risk, plus a Not verified entry for the branch-protection binding.

## 3. Quality and maintainability

What counts: changes that make the next change harder, or the current one wrong in quiet ways. This is a merge review, not a full clean-code audit: weigh regressions this branch introduces over debt the repo already carried.

Diff-visible signals:

- Duplication: logic copy-pasted from elsewhere in the repo and lightly edited. The tell is a hunk that reads like an existing function with three lines changed.
- Divergence: the branch introduces a second way to do a thing the repo does one way (a second HTTP client, a second config reader, a second logger setup).
- Shape: functions accreting flag parameters and nested conditionals where the codebase uses guard clauses; god functions doing parse plus validate plus IO plus format in one body.
- Error handling: broad except-and-pass or catch-and-continue, error returns ignored, promises unawaited.
- Leftovers: dead code kept "just in case", commented-out blocks, debug prints, TODO or HACK or FIXME introduced by this branch.
- Contract erosion: public API changed without a deprecation path; internal types leaking across layer boundaries.
- Broken callers: anything renamed or re-signed whose call sites the diff does not fully cover. This is the highest-value scout dispatch in the dimension.

Scout question bank:

- "List call sites of `<old symbol>` outside `<changed files>`. file:line."
- "Does a function similar in name to `<new helper>` already exist under `<src dir>`? Search `<pattern>` and report matches, file:line."
- "Which modules import `<changed module>`? file:line."

Severity anchors: a confirmed broken caller outside the diff: High. Copy-paste duplication of nontrivial logic, or swallowed exceptions on a path that matters: Medium. Naming, comments, style divergence: Low. When quality issues cluster in one new module, one finding per issue class with all locations listed beats ten one-line findings.

## 4. Documentation drift

What counts: statements that were true before the branch and are false after it. Rank by who reads the document: onboarding and operational docs outrank inline comments.

Where to look, in order:

- README and quickstarts: setup commands, env var tables, endpoint lists, CLI flags.
- `.env.example` and sample configs: every new required env var or config key belongs there; a missing one breaks the next deploy or the next hire.
- API contracts: OpenAPI, proto, or GraphQL schemas versus handlers; public docstrings versus new signatures.
- Operational: runbooks, deploy docs, compose files referencing services, ports, and variables.
- Changelog or ADRs where the repo maintains them: significant behavior change with no entry.
- Inline: comments and docstrings inside the diff contradicting the code beside them. You see these while reading; no scout needed.

Method: while reading the diff, accumulate the rename-and-removal list (symbols, flags, env vars, endpoints, config keys). Then one scout per batch: grep the doc surfaces for each old name and each new name. An old name still present is drift. A new required name absent from `.env.example` or the README env table is drift.

Scout question bank:

- "Grep `README.md`, `docs/`, `.env.example` for `<old name>` and `<new name>`. file:line per hit."
- "List env vars read under `<src dir>` (os.getenv, process.env, env::var) and the vars listed in `.env.example`. file:line."

Severity anchors: drift that breaks a setup or deploy path (missing env var, wrong endpoint in a quickstart): Medium, High when the doc is the primary onboarding path. Stale API docs on a public contract: Medium. An inline comment contradicting adjacent code: Low, but worth fixing in the same PR since the diff already touches the file.

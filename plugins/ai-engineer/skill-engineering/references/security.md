# Security

Two threat surfaces: what the harness does to the person running it, and what the packaged
skill does to whoever installs it.

## Contents

- [Eval output is untrusted input](#eval-output-is-untrusted-input)
- [Blast radius](#blast-radius)
- [The packaging security report](#the-packaging-security-report)
- [Firewalls and network](#firewalls-and-network)
- [Permissions](#permissions)
- [What not to build](#what-not-to-build)

## Eval output is untrusted input

The executor agent acts on a prompt someone supplied and often reads files someone supplied.
Everything it writes is therefore attacker-influenced, and every path that renders it is a
sink.

The concrete instance: `json.dumps` does not escape `</script>`. Embed an eval output
containing an HTML file with an inline script into a `<script>` block and the HTML parser ends
the element early. The benign consequence is that the viewer renders blank — which happens
constantly, because skills that generate HTML are a common thing to build. The adversarial
consequence is arbitrary JavaScript on the reviewer's `localhost` origin, reachable through
indirect prompt injection into the executor.

`skilleng.report.safe_json_for_script` handles it, and a test pins it. The general rule is
that no output file's content ever reaches a page without escaping, and none of it is ever
interpolated into a shell command.

## Blast radius

The harness spawns autonomous agent sessions. Design constraints:

- Every run uses a throwaway config directory. Never the person's real one.
- The skill is installed into that sandbox. Never into their live configuration.
- The working directory is the run's own outputs directory. Never `$HOME`, never their repo.
- Nothing is written to their project tree.
- Parallelism and run counts are printed before spending.

Mechanical assertions are the exception worth naming: `check` commands run as shell in the
outputs directory. They are authored by whoever wrote the eval file. Treat an eval file from
an untrusted source exactly like a script from an untrusted source, because that is what it
is.

## The packaging security report

A `.skill` file is a zip of instructions **and executable scripts** that someone installs and
an agent then runs. GitHub's own documentation tells users to pre-approve shell access only
for skills whose scripts they have reviewed — so the tool that mints the artifact should
produce the thing that makes review possible.

`skilleng package` emits `SECURITY.md` alongside the archive and inside it:

- **Secret scan.** AWS keys, GitHub and Slack tokens, Google and model-provider API keys,
  private key blocks, bearer tokens, assigned-secret patterns. A hit **blocks** packaging.
- **Exclusions.** `.git`, `.env`, `.venv`, key material, credential files, state files. A
  `.git` directory inside a shared archive carries full history and sometimes credentials.
- **Script inventory.** Every bundled script, with the behaviours detected in it: shell
  execution, network access, writes outside the workspace, deletion, credential/environment
  reads, dynamic evaluation.
- **Network endpoints.** Every host referenced, so the installer can check them against their
  own egress policy.
- **Permissions.** The declared `allowed-tools` next to the minimum the bundled scripts
  actually imply.

`evals/` ships with the package by default. A distributed skill that cannot re-verify itself
after a model upgrade is a skill nobody can maintain, and stripping the test suite at package
time is exactly backwards.

## Firewalls and network

On Copilot's cloud agent, outbound access is governed by a default-on allowlist, and a blocked
request appends a warning to the pull request rather than failing the run. That is a
silent-degradation shape — the same shape as an uncalibrated harness — so a skill whose
scripts fetch anything needs its endpoints declared and allowlisted. The security report's
endpoint list is what you hand to whoever administers that.

## Permissions

Propose the minimum. A skill that declares broad tool access because it once needed it is a
standing grant nobody revisits. The report's proposed `allowed-tools` is derived from what the
scripts demonstrably do; if the declared set is wider, narrow it or write down why.

## What not to build

Skills must not contain malware, exploit code, credential harvesting or data exfiltration, and
must not surprise the person who installs them relative to their stated purpose. A skill whose
description and behaviour disagree is the problem, whatever the behaviour is.

Roleplay, persona and style skills are fine. The line is deception about what the artifact
does, not subject matter.

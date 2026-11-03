# Security

## Reporting

Report vulnerabilities privately through GitHub's security advisories on this repository
(Security tab, "Report a vulnerability") rather than in a public issue. Include what an attacker
gains and the shortest path to reproducing it.

## What counts as a vulnerability here

This repo ships instructions that agents execute with real tool access, so the threat model is
wider than the code. In scope: anything that lets skill or agent text escalate what an agent
does beyond what the user approved, prompt-injection amplifiers in the skill bodies, and
an eval run executing fixture content it should only read.

One standing property reviewers should hold this repo to: no skill uses `allowed-tools` to
pre-approve shell access, and a change introducing that needs a security rationale in the PR, not
just a convenience one.

mightymodels and terraform-harness are developed in their own repositories, so reports about them
go to [mightymodels](https://github.com/rhawk117/mightymodels) and
[cc-terraform-harness](https://github.com/rhawk117/cc-terraform-harness).

No script in this repository scans skill and agent text for prompt-injection indicators. The
mechanical checks are `claude plugin validate --strict` on each plugin and the marketplace, which
cover manifests and frontmatter; the text itself is held to the standards above by review.
Reports about gaps in those checks are in scope for vulnerability reports.

## Dependencies

The vibe-code CLI pins its Python floor (3.12) and carries two runtime dependencies, msgspec and
PyYAML, pinned by version in its launcher. Dependency updates go through the normal gate; there is
no vendored code. `vibe-code tune route` starts headless `claude -p` sessions on your account, one
per trigger request, with project settings only and the `Skill` tool as their only tool; each runs in
a temporary directory that holds stub skills (name and routing frontmatter, never a body).

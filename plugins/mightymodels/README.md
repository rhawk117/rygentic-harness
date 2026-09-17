# mightymodels

Ticket-scoped agent development loop for Claude Code: skills, agents, an MCP
server that carries the loop's writes, and a hook layer that keeps a session
on the contract.

## Install

```text
/plugin marketplace add <owner>/rygentic-harness
/plugin install mightymodels@rygentic-harness
```

The server and the hooks are Python 3.14 and run through
[uv](https://docs.astral.sh/uv/), which Claude Code invokes for them; nothing
is installed into the host project. Create the environment once after
installing.

Marketplace install, using the directory `/plugin install` reports (for
example `~/.claude/plugins/cache/rygentic-harness/mightymodels/<version>`):

```bash
uv sync --project ~/.claude/plugins/cache/rygentic-harness/mightymodels/<version>
```

Working checkout, the case the Activation section below describes, from the
repository that holds the plugin:

```bash
uv sync --project plugins/mightymodels
```

The first SessionStart hook has a 60-second budget, and resolving dependencies
on that first run can spend most of it.

## Activation

The installed copy lives in the marketplace cache, so a working checkout is
activated for a session with its own directory:

```bash
claude --plugin-dir plugins/mightymodels
```

Edits to the skills, agents, hooks, or server are picked up with
`/reload-plugins`.

## MCP server

`.mcp.json` registers one stdio server, `mightymodels`, backed by the
`mightymcp` package under `src/`. Claude Code launches it with `uv run
--project ${CLAUDE_PLUGIN_ROOT} mightymcp`. Every tool returns a `refusals`
list and writes nothing while that list is non-empty, so a refused call leaves
the ticket as it found it.

When more than one ticket directory is present under `.mightymodels/`, the
server picks the one whose `handoff-context.branch-name` matches the checked
out branch; if none matches, it falls back to the `MIGHTYMCP_TICKET`
environment variable, and refuses if neither resolves a ticket.

| Tools | What they do |
| --- | --- |
| `fleet_roster`, `resolve_model`, `route_ramp`, `route_finding` | Which worker and which model a piece of work goes to |
| `ticket_read`, `ticket_create`, `ticket_update_context`, `sprint_status` | The ticket state under `.mightymodels/` |
| `brief_open`, `brief_append_done`, `brief_read`, `task_record_attempt` | The two-half task brief and the attempt ledger behind escalation |
| `report_write`, `checklist_render`, `whats_broken_write`, `whats_broken_close`, `handoff_write`, `handoff_prompt`, `decision_record` | The sprint's own artifacts |
| `parse_report`, `findings_merge`, `review_verdict`, `grade_compute`, `review_report_write`, `pr_comment_render`, `blast_radius_questions` | Worker reports and the review gate |
| `dialectic_score`, `dialectic_record_write`, `crashout_add`, `crashout_stats`, `crashout_last`, `metrics_run` | Tie-breaks and the skills' own scripts |
| `ticket_prunable`, `ticket_archive`, `ticket_delete` | Closing a finished ticket out |

Resources are read at the `mm://` scheme, so a worker loads a contract by URI
instead of being handed a path:

| URI | What it returns |
| --- | --- |
| `mm://fleet` | Every agent the plugin ships, one line per worker |
| `mm://ref/{skill}/{name}` | One reference file of one skill |
| `mm://agent/{name}` | One agent contract, frontmatter included |
| `mm://template/{role}` | The promptlint dispatch template for a role |
| `mm://template/engineer/{task}` | The engineer template carrying that task's ASKED half |
| `mm://ticket/{slug}` | A ticket's `ticket.yml`, as written |
| `mm://ticket/{slug}/brief/{task}` | One task brief, every half it carries |
| `mm://ticket/{slug}/status` | Where the sprint stands, one line per task |

The roster and the bundled markdown are read at call time, so they follow the
files on disk rather than a copy that can drift from them.

## Hooks

`hooks/hooks.json` registers nine Python hooks, each run through the same
project as the server: SessionStart injects the roster and the ticket state,
PreToolUse guards Agent dispatches, Write and Edit, and Bash, SubagentStart
injects a worker's context, SubagentStop gates the report and logs the
dispatch, PreCompact writes a ticket snapshot, PostToolUse captures `gh pr` and
`gh issue` numbers into `ticket.yml`, and Stop reminds about an uncommitted
DONE half. No hook exits non-zero and none returns `ask`, so a hook that breaks
degrades to silence rather than to a stuck session.

Set `MIGHTYMCP_OFF` to any non-empty value to stand the whole layer down for a
session. The workflow still runs as written: every tool writes a file a human
could have written by hand.

```bash
MIGHTYMCP_OFF=1 claude --plugin-dir plugins/mightymodels
```

## Live confirmation

The test suite covers the tools and the hook functions, not Claude Code's
substitution of `.mcp.json` or its hook dispatch. Confirm those three things
once against a live session, in a repository with an active ticket:

1. `.mcp.json` substitution: `/mcp` lists the `mightymodels` server and its
   tools, and `ticket_read` returns the ticket of the repository you are in
   rather than a refusal about the project directory.
2. The SubagentStop gate: dispatch a scout whose report is malformed, for
   instance one missing its verdict line, and confirm the stop is blocked once
   with the parser's own reason, and that the retry is allowed through.
3. The Bash guard: run `git push --force` and confirm it is denied exactly
   once, with the never-rule named in the reason.

## Development

The package is a member of the repository's uv workspace. From the repository
root:

```bash
uv sync
uv run pytest -q plugins/mightymodels/tests
```

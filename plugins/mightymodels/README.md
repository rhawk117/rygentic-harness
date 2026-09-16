# mightymodels

Ticket-scoped agent development loop for Claude Code: skills, agents, and an MCP
server that answers questions about the plugin itself.

## MCP server

`.mcp.json` registers one stdio server, `mightymodels`, backed by the `mightymcp`
package under `src/`. Claude Code launches it with `uv run --project
${CLAUDE_PLUGIN_ROOT} mightymcp`, so the plugin carries its own dependencies and
needs nothing installed in the host project.

| Capability | Name | What it returns |
| --- | --- | --- |
| Tool | `fleet_roster` | Every agent the plugin ships, as structured `name` / `job` / `model` records |
| Resource | `mm://fleet` | The same roster as one text line per agent |

Both read `agents/*.md` at call time, so the roster follows the agent files
rather than a copy that can drift from them.

## Development

The package is a member of the repository's uv workspace. From the repository
root:

```bash
uv sync
uv run pytest -q plugins/mightymodels/tests
```

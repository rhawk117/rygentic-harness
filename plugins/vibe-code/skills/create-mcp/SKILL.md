---
name: create-mcp
argument-hint: "[what the server should let the agent do]"
when_to_use: >-
  Use when the user says "expose X as tools", "let Claude call our API", "wrap this CLI or service for the agent", "add an MCP server to my plugin", or asks about MCP tools, resources, prompts, elicitation, stdio versus HTTP, or how to configure a server in Claude Code, even without the letters MCP.
description: >-
  Interview-driven builder for MCP servers in Python (uv project, official `mcp` SDK, src layout with one package per tool). Use it to create, scaffold, design or add an MCP server for Claude Code. It asks where the server is installed (plugin, project, local or user scope), whether it is local only or a network service, what it does and what problem it solves, then one round per tool (inputs, outputs, side effects, whether it pauses to ask the person), infers resources and prompts, records the interview as a spec, generates the project from the bundled template, runs ruff, ty and the in-process tests, implements each use case with the user, writes the Claude Code config for the chosen scope and proves the entrypoint starts.
---

# Create an MCP server

An MCP server gives the model capabilities it cannot get from the shell and the filesystem: a typed contract over an external system, a guarded operation that should ask before acting, state that outlives one command, or an API the model should not hit with raw curl. The cost is a process Claude Code has to start, a schema the model reads on every turn, and one more thing that can be misconfigured silently. This skill is an interview that ends in a working uv project, because the mistakes in MCP servers are made before the first line of code: the wrong transport for where it runs, tools whose descriptions the model cannot act on, a server that guesses which directory the project is in, and confirmation flows the client never shows.

Ask every question with the `AskUserQuestion` tool: single select, multi select, or free text through its other option. It is removed when a run uses `--permission-prompts none`, so the interview cannot run headless.

| phase                     | what happens                                                                       | user involvement             |
| ------------------------- | ---------------------------------------------------------------------------------- | ---------------------------- |
| A. Install                | scope (plugin, project, local, user); where it lives; how it finds the root        | one question                 |
| B. Reach                  | local only, network service, or both, in plain words                               | one question                 |
| C. Purpose and route      | what it does, what problem it solves; is an MCP the right mechanism                | free text, one confirmation  |
| D. Tools                  | one round per tool: purpose, inputs, outputs, side effects, size, duration         | one question per tool        |
| E. Pauses                 | which tools pause to ask the person; interview-style tools                         | one question                 |
| F. Resources and prompts  | inferred from the answers, confirmed                                               | one yes or no                |
| G. Record                 | the spec JSON, signed off                                                          | one confirmation             |
| H. Generate and verify    | `vibe-code mcp scaffold`, `uv sync`, ruff, ty, pytest, shown                     | results                      |
| I. Implement              | each use case, asking every question that arises                                   | conversational               |
| J. Configure and hand off | config for the scope, validated, registered, entrypoint proven                     | results                      |

Read `references/mcp-sdk-facts.md` once at the start: the SDK is on its 2.x line and the names differ from what most examples online show (`MCPServer`, not `FastMCP`; transport options on `run()`; elicitation through `Resolve`). Read `references/mcp-config.md` in phases A and J: the config files, the entry keys and the Claude Code limits live there, and a key or limit outside it is unverified. The bundled template under `assets/template/` is the plugin owner's layout; do not invent a parallel one, and `assets/spec.example.json` is the copyable spec.

The rule for the whole workflow: anything the user has not said is a question, not an assumption. When the user has answered everything upfront ("everything you'd otherwise ask me: ..."), use those answers, skip the question, and say which default you took for anything they did not cover.

## Phase A: where it is installed

Single select, the scope of the server:

- plugin: the project lives at `<plugin-root>/mcp/NAME/` and a `.mcp.json` at the plugin root launches it with `uv run --project` and the plugin-root variable (the exact file is the plugin shape in `references/mcp-config.md`). Claude Code connects the server when the plugin is enabled or reloaded. Choose where the server is declared: the `.mcp.json` file, or the `mcpServers` key of `.claude-plugin/plugin.json`, which takes an inline map, a path or an array, and also a packaged `.mcpb` file.
- project: the project lives at `mcp/NAME/` in the repository and `.mcp.json` at the repository root, committed, launches it. The whole team gets it, after each person approves it.
- local: the same project, registered for this person in this project only; Claude Code stores it in `~/.claude.json` under the project's path and it is the default of `claude mcp add`.
- user: registered for this person in every project; the project directory is then an absolute path, because the server has no repository to be relative to.

Local and user servers are registered with `claude mcp add` (phase J). When one name is defined in several scopes, the highest precedence wins, whole entry, in this order: local, project, user, plugin.

Then decide how the server finds the project root, because it must not guess. Single select, set as `root_source` in the spec:

- `env`: the server reads `CLAUDE_PROJECT_DIR`, which Claude Code sets in its environment to the project root. The default choice for a server that acts on the repository.
- `roots`: the server asks the client for `roots/list`, which answers with the launch directory plus every directory added with `--add-dir`. Choose it when the server must keep to the allowed directories and follow changes to them.
- `parameter`: every tool takes a `root` parameter that the model fills from its own working directory. Use it when the server must work without either of the above.
- `cwd`: the server uses its own working directory. Claude Code does not document where a stdio server starts, so say this plainly and prefer another value.

Then ask for the server name (kebab-case; it becomes the `uv run` script and the config key, and tools reach the model as `mcp__NAME__tool`, or `mcp__plugin_<plugin>_<server>__<tool>` from a plugin). Check the target directory does not already exist.

## Phase B: how far it reaches

Single select, worded for someone who does not live in this ecosystem:

- local only: Claude Code starts it on this machine and talks to it over standard input and output; nothing listens on a port; no network exposure. This is stdio, and it is the right answer for anything that reads files or runs commands here.
- network service: it runs somewhere as a service and clients connect over HTTP; it needs a host, a port, and eventually authentication. This is streamable HTTP. Right when several people or machines share one instance, or the server holds state or credentials that should not live on every laptop.
- both: one server, transport picked by a flag at start (`--transport stdio|streamable-http`). Only when both situations are real; otherwise it is surface area nobody tests.

For a network service, ask whether it will ever be reached through a hostname other than localhost; if so the hand-off includes `transport_security` (DNS-rebinding protection allows localhost only by default) and says that authentication is not generated.

## Phase C: purpose, and whether an MCP is the right mechanism

Ask for two things in the user's words: what the server should let the agent do, and what problem it solves (what goes wrong today). Restate each in one sentence and confirm.

Then route. An MCP is the wrong mechanism, and you should say so with the concrete reason, when:

- the tools would only wrap commands the model can already run in the shell with the same arguments: that is a skill whose frontmatter pre-approves the commands, for example `allowed-tools: Bash(uv *)` in the skill the user builds, cheaper and with no process to start (`create-skill`).
- it is a persona or a procedure with judgement in it, not a capability: a subagent (`create-subagent`) or a skill.
- it must happen automatically at a lifecycle point: a hook (`create-hooks`).

An MCP is right when the model needs a typed contract (structured inputs and outputs), a guarded operation (confirmation before acting), access to something the shell cannot reach (an API with credentials, a database, a long-lived connection), or a capability shared across repositories from a plugin. Offer a single select: switch to the better mechanism, or "Don't care, build it as an MCP anyway". Honour the override and record it in the hand-off.

## Phase D: the tools, one round each

Ask how many tools and their working names, then run one `AskUserQuestion` round per tool with these fields, defaults pre-filled from the purpose statement:

- description, written for the model: what it does, when to call it, what it returns. This text is the whole contract the model sees, so a vague description produces vague calls.
- inputs: name, type (`str`, `int`, `float`, `bool`, `list[str]`, `list[int]`, `dict[str, str]`, `list[dict[str, str]]`), one-line description, required or default. Fewer, well-described inputs beat a kitchen sink; the model has to fill every field correctly on every call.
- outputs: name, type, description. Structured output is what lets the model reason on the result instead of parsing prose; a bare summary string is the fallback, not the default. Claude Code warns when a result passes 10,000 tokens and cuts it at 25,000. A tool that must return more sets `max_result_chars` in the spec, up to 500,000, which the scaffold writes as the `anthropic/maxResultSizeChars` key of the tool's `_meta`.
- side effects: read-only, writes, or destructive. This becomes the tool annotations (`read_only_hint`, `destructive_hint`, `idempotent_hint`) that clients use to decide whether to prompt, so it must be honest.
- duration: how long a call takes at worst, and whether the server can report progress. A call in the main conversation that runs past two minutes moves to a background task, and a call with no response and no progress is aborted after 30 minutes on stdio (five on HTTP). Set the entry's `timeout` (milliseconds) for a call that needs longer.
- confirmation: should this tool pause and ask the person before acting? Default yes for destructive, no otherwise. Phase E explains how.
- external binary: does it run a command (`git`, `terraform`, `kubectl`)? Then the binary goes into the server's required list, the workspace runs it with a timeout and captured output, and the use case receives a `CommandResult` rather than calling `subprocess` itself. Ask for the exact argument list.
- paths: if it takes a path, it is resolved inside the workspace root and rejected outside it; say so, because that containment is the security boundary of a filesystem tool.

The server's `instructions` text matters too. Claude Code defers tool definitions until the model searches for them (tool search), and the instructions tell the model what category of task the tools serve and when to search. Write them for that. If the server has a few tools the model needs on every turn, set `always_load` in the spec, which writes `"alwaysLoad": true` into the config entry; each such tool costs context in every session, so ask before setting it.

Show the accumulated tool table after each round so the user can see the shape forming and rename or drop tools before anything is generated.

## Phase E: pauses and interview-style tools

Two questions, because they decide whether the elicitation machinery is generated at all:

- Should any tool pause mid-call and ask the person something (confirmation, a choice between options, a missing value)? Each yes becomes a resolver on that tool: `Annotated[ElicitationResult[Model], Resolve(fn)]`, with a flat schema of primitive fields. Claude Code shows the dialog with no configuration. Whether it drives the resolver's multi-round-trip on the installed version has not been proven here, so the hand-off includes a one-call manual check in an interactive `claude` session.
- Should there be an interview-style tool, one whose whole job is to gather answers from the person in sequence (an onboarding wizard, a "collect the release details" tool)? If yes, design it as one tool with one resolver per question, each question a separate flat model, and warn that every question is a round trip the client has to render; three questions is fine, twelve is a form that belongs in a web page.

A destructive tool gets a second guard. The scaffold sets `anthropic/requiresUserInteraction` to `true` in its `_meta`, which makes Claude Code show the tool's permission prompt on every call, even in `bypassPermissions` mode, and allow rules do not skip it. Tell the user this is on for each destructive tool, and that a `dontAsk` run denies the call.

A `claude -p` run has nobody to answer. With `--permission-prompts none`, an elicitation that no `Elicitation` hook answers is cancelled, so the hand-off says a headless run needs such a hook, and the generated tests call the tool through a client with a callback that accepts.

## Phase F: resources and prompts, inferred

Do not ask "do you want resources?"; most servers do not, and the word means nothing to someone outside the ecosystem. Instead look back at the answers:

- something the model should be able to read without calling a tool (a config, a schema, a document, the current state of X) is a resource; propose a URI like `NAME://{id}/thing` and ask yes or no. Tell the user the exact way to use it: `@NAME:NAME://ID/thing` in a prompt.
- a canned way to start a conversation with this server ("review the plan at PATH", "onboard a new service") is a prompt; propose the name and its arguments and ask yes or no. Tell the user the exact way to run it: `/mcp__NAME__PROMPT ARGUMENTS`.

If nothing in the answers points at either, say so in one line and move on.

## Phase G: the record

Write the spec JSON from `assets/spec.example.json` with everything gathered: name, package, description, instructions, scope, reach, `root_source`, `always_load`, binaries, tools, resources, prompts. Claude Code truncates each server's instructions at 2,048 characters, so keep the instructions short and put the critical details first; the scaffold warns past that length. Show the spec and ask for sign-off. The spec is the record of the interview; it is copied into the generated project as `mcp-spec.json`, and re-running the scaffold from it reproduces the skeleton.

## Phase H: generate and verify

Run, and show every output:

```
vibe-code mcp scaffold SPEC.json TARGET_DIR
cd TARGET_DIR && uv sync
uv run ruff format . && uv run ruff check .
uv run ty check
uv run pytest
```

`vibe-code mcp scaffold --help` lists `--template DIR` and `--force`. The scaffold writes the project from `assets/template/` (pyproject with strict ty and ruff, `src/PKG/{__main__,cli,server,workspace}.py`, one `tools/NAME/{schema,use_case}.py` per tool, `tests/test_NAME.py` per tool, README, and `config/` snippets `mcp.plugin.json`, `mcp.project.json` and, for a network reach, `mcp.network.json`). Generated code passes ruff and ty after `ruff format`. The listing tests pass immediately (each tool is registered with its schema and annotations); the call tests fail with `NotImplementedError` until the use case is implemented. A binary-backed tool with no inputs and string outputs is implemented outright (run the command, map stdout); one with inputs or typed outputs gets the command call generated and a stub for the mapping, because the argument list and the parsing are exactly the questions phase I asks. That is deliberate: a red test per tool is the to-do list for phase I, and green means the model can call it.

## Phase I: implement each use case, with the user

For each tool, open `tools/NAME/use_case.py` and write `run(workspace, params) -> Output`. Every question that arises is asked, not guessed: which command and arguments, how a failure should read to the model (`ToolError` text is what the model sees; anything else becomes a generic error), what to return when there is nothing to report, whether a path should be a file or a directory, what the timeout should be. Use the workspace for paths and commands (`workspace.resolve_relative`, `workspace.execute_tool`, `workspace.execute_concurrently`) rather than `subprocess` or bare `Path` calls, because that is where containment and timeouts live. Adjust the generated test to set up the state the tool needs (a git repository, a sample file) and keep it calling through the MCP client, not the function directly, so the schema and structured output stay under test. Rerun ruff, ty and pytest after each tool and show the output.

## Phase J: configure and hand off

Write the config for the scope from `config/` (the scaffold already rendered it; `references/mcp-config.md` holds the plugin shape, the entry keys and the `env` and `headers` forms) and validate it:

```
vibe-code mcp validate FILE --kind plugin --check-command
vibe-code mcp validate FILE --kind project --check-command
vibe-code mcp validate FILE --kind user --check-command
```

Pick the `--kind` that matches the scope. It runs `claude plugin validate` on the servers first, then the checks that command misses, and `--check-command` runs `uv run --project ... NAME --help` to prove the entrypoint resolves. A first run in a fresh checkout builds the environment, which is why the project shape raises `timeout` to 120000. For a plugin, finish with `claude plugin validate --strict` on the plugin directory.

How each scope is written:

- plugin: copy `config/mcp.plugin.json` to `.mcp.json` at the plugin root. It launches the server with `uv run --project` into the plugin's `mcp/NAME` through the plugin-root variable, which Claude Code expands.
- project: copy `config/mcp.project.json` to `.mcp.json` at the repository root. It has `"type": "stdio"` and a raised `timeout`. Say that Claude Code asks each person for approval before it uses a project server in an interactive session, that `claude mcp reset-project-choices` resets the answers, and that `claude -p` loads project servers without asking. The alternative to hand-writing the file is `claude mcp add --transport stdio --scope project NAME -- uv run --project mcp/NAME NAME`.
- local or user: `claude mcp add --transport stdio --scope local NAME -- uv run --project PROJECT_DIR NAME`, with `--scope user` for the user scope and an absolute `PROJECT_DIR`. `claude mcp add-json` takes the entry as a JSON string instead. `claude mcp remove NAME` undoes either.
- network service: the config is an `http` entry with the URL; the server has to be running before the session starts. For authentication see the remote section of `references/mcp-config.md`.

To check that the server loaded, run `claude mcp list` (a health status per server) or `claude mcp get NAME`, or open `/mcp` in a session. A plugin server shows as `plugin:PLUGIN:NAME`. In a `claude -p --output-format stream-json` run, the `system/init` event lists `mcp_servers` and, for a skipped `--mcp-config` entry, `mcp_server_errors`.

Hand off with: the paths written; how to start it by hand (`uv run NAME`, `--transport streamable-http --port N`); how to add a tool (a new package under `tools/`, a registration in `server.py`, a test); the permission rules to narrow or allow its tools (`mcp__NAME__tool` in `permissions.allow` or `--allowedTools`); the elicitation manual check if any tool confirms; anything routed away or overridden in phase C; and what is unverified: the resolver round trip, the install step for a plugin's Python environment, and `ty` being a beta whose rules can change between releases.

# Template: terry-toolchain dispatch

For the one environment survey of a game-plan run, sent before the plan is drafted. terry-toolchain surveys the harness's tools, the installed skills, plugins and agents, the repository's own toolchain and the sandbox and permission limits. Its standing contract (the four surveys, the fallback to manifests when a CLI command is refused, the command allow-list, the report format and its 80-line cap) lives in the terry-toolchain agent file; carry only what varies per dispatch. Only the main conversation dispatches it, and only game-plan does: no worker's dispatch row names it, and one-shot tickets get no survey.

**Ten-second checklist:** the summary is the ticket's own `summary`, verbatim, because terry-toolchain judges which skills and agents bear on the ticket from it · the paths named are the packages the ticket touches, or the line is left out · nothing in the packet asks for a recommendation, which is yours to make · the model is `sonnet`.

```text
<objective>Survey the environment for ticket <slug> before its plan is drafted.</objective>
<context>
Ticket slug: <slug>. Summary: <the ticket's summary, verbatim>.
<Packages or paths the work will touch, when the ticket names them.>
</context>
```

Slots: slug · summary · optional packages or paths.

## When it comes back

- Save the report verbatim as `.mightymodels/<slug>/toolchain.md`: terry-toolchain writes no file. A later game-plan run on the same ticket replaces it.
- Read `## Not seen` first. A survey that could not see something the plan depends on (the hooks, the lint configuration, the permission rules) is a Risk in the draft, with the missing sight as its signal, not a gap to fill from memory.
- A `[declared]` line was read from a manifest or a configuration file and not seen to take effect. Treat it as you treat `INFERRED`: open the cited line yourself before it drives a decision.
- The plan's commands are the ones the `Repository toolchain` section reports. A hook, ban or denial a task would run into becomes an invariant, a criterion or a Risk, and its line goes into that task's ASKED stanza through the engineer template's `toolchain:` slot.

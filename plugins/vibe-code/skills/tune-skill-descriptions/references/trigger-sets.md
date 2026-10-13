# Building a trigger set

The loop optimizes toward the trigger set, so its quality bounds the result. Build it with the user and get their sign-off before `init`.

## Format

YAML or JSON, a list of requests with the skills that should load:

```yaml
- request: "my sprint ticket has been stuck in review for a week, can you check who owns it"
  skills: [jira]
- request: "give PR #214 a proper review before I merge"
  skills: [pr-review]
- request: "write a haiku about autumn"
  skills: []
```

Quote every request. In YAML an unquoted `#` starts a comment, so `give PR #214 a review` silently becomes `give PR`; `init` refuses a file where that happened. Each request appears once. Every skill named must be one of the skills passed to `init`.

## What makes a useful set

- **Size.** At least 20 requests, and at least 3 positives per skill being tuned. The CLI holds out about 30 percent for validation, stratified by expected skills, so very small sets give noisy decisions.
- **Realistic phrasing.** Write what users actually type: context, file names, abbreviations, casual wording. Requests that quote the skill's description back to it test nothing.
- **Near misses.** The most valuable negatives share vocabulary with a skill but need something else, such as asking about Jira the company rather than a Jira ticket, or explaining a Python concept rather than locating a symbol. Include several per skill.
- **Overlaps.** If two skills compete, include requests that belong to each side of the boundary, and a few that genuinely need both.
- **True negatives.** Include requests no skill should take, so the score rewards abstaining.
- **Built-in competition.** With the `claude-code` judge, Claude Code's built-in skills (such as `code-review` or `debug`) are listed next to the stubs. A request a built-in skill serves well belongs in the set as an empty list unless the user's skill should win it.

## Sources

The best requests come from real use: past prompts where a skill misfired or failed to load, issues the user remembers, and the skill's own documented use cases. Ask the user for examples before inventing them.

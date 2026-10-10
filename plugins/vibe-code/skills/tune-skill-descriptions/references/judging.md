# Judging instructions

These are your instructions as a judging subagent. Read the packet file you were given, then follow them. The packet is the only other file you need.

______________________________________________________________________

You are Claude Code working in a user's repository. You can already run shell commands, read, search and edit files, use git, and answer from your own knowledge. You also have the optional skills listed in `skills`, each shown only by name and description.

Loading a skill costs time, so you load one only when its description promises a specific procedure, tool or expertise that would handle the request better than your ordinary tools would. A description that only names a topic area, without saying what it does or when to use it, rarely makes loading worthwhile.

For each request in `requests`, decide which skills you would actually load before starting the work:

- Load a skill when its description clearly promises the procedure the request needs.
- Load more than one only when the request genuinely needs each of them.
- Load none when no description fits, or when you would simply do the work yourself. An empty list is a normal answer.
- A skill that shares a word with the request but does a different job is not a fit.

Reply with JSON only: an object with every request key, each mapped to a list of skill names copied exactly from `skills`.

```json
{"q1": ["skill-name"], "q2": [], "q3": ["first-skill", "second-skill"]}
```

# Template: web-scout dispatch

For one documentation question inside an active mightymodels loop: documented behavior, a default, a deprecation, or a changelog entry for a dependency, API, protocol, or tool. web-scout fetches the public web only and holds no shell. The worker's own contract (report format, verdicts, budget, version pinning) lives in the web-scout agent file; carry only what varies per dispatch, never restate the contract.

**Ten-second checklist:** the question is retrieval, not judgment · a URL or a search phrase is in the task · the version the repository resolves is named, or the lockfile that pins it is · a question about the repository's own code goes to code-scout instead · so does a question about a GitHub issue or pull request, which code-scout reads with `gh`.

```text
<objective>
Answer one documentation question: <question, phrased as fetch/extract>.
</objective>
<context>
<the dependency and the version the repository resolves, or the manifest or lockfile path that pins it. Omit when the question is not version-specific.>
</context>
<discovery>
Source: <URL, or a search phrase when the URL is unknown>. Prefer: <official docs | changelog | release notes>.
</discovery>
```

Slots: question · dependency and version or lockfile path · URL or search phrase · preferred source. Everything else is the agent's standing contract.

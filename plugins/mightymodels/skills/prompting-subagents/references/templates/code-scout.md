# Template: code-scout dispatch

For one repository retrieval question inside an active mightymodels loop: a definition, call sites, a config value, a resolved version, git history, a GitHub issue or pull request read, or one read-only command or test. The worker's own contract (report format, verdicts, budget, command allow-list) lives in the code-scout agent file; carry only what varies per dispatch, never restate the contract.

**Ten-second checklist:** the question is retrieval, not judgment (a "should/why/is it sound" question bounces back NEEDS-ANALYSIS and wastes the dispatch) · exact paths, symbols, and search terms are in the task, because code-scout has not seen your diff, ticket, or ledger · scope is the narrowest that answers it · a documentation question goes to web-scout instead · a GitHub read is `gh issue view`, `gh pr view`, or `gh search` with `--json`, and nothing else from `gh`.

```text
<objective>
Answer one repository retrieval question: <question, phrased as locate/list/extract/run>.
</objective>
<context>
<only facts code-scout cannot discover and needs: branch name, the change that prompted the question, 1-3 lines. Omit the section when the question stands alone.>
</context>
<discovery>
Search scope: <paths or packages>. Terms/symbols: <exact strings, quoted>. <File-type filter if useful.> <Command to run, verbatim, when the question is "run".> <Issue or pull request number, or the `gh search` terms, when the question is a GitHub read.>
</discovery>
```

Slots: question · scope paths · exact terms · optional command · optional issue or pull request reference · optional context lines. Everything else is the agent's standing contract.

# Template: scout dispatch

For one retrieval question inside an active mightymodels loop. The scout's own contract (report format, verdicts, budget) lives in agents/scout.md — carry only what varies per dispatch, never restate the contract.

**Ten-second checklist:** the question is retrieval, not judgment (a "should/why/is it sound" question bounces back NEEDS-ANALYSIS and wastes the dispatch) · exact paths, symbols, and search terms are in the task — the scout has not seen your diff, ticket, or ledger · scope is the narrowest that answers it.

````
<objective>
Answer one retrieval question: <question, phrased as locate/list/extract/run>.
</objective>
<context>
<only facts the scout cannot discover and needs: branch name, the change that prompted the question — 1-3 lines. Omit the section when the question stands alone.>
</context>
<discovery>
Search scope: <paths or packages>. Terms/symbols: <exact strings, quoted>. <File-type filter if useful.> Exclude vendored trees.
</discovery>
````

Slots: question · scope paths · exact terms · optional context lines. Everything else is the agent's standing contract.

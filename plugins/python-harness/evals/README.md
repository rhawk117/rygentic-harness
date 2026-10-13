# Smoke evals

Six cases check whether a skill loads in a real session. For automate-task, data-analysis and
data-engineering there is one request the skill should take (`<skill>-loads`) and one near-miss
that should leave it unloaded (`<skill>-stays-out`). Each case grades a single thing: whether the
Skill tool was called for that skill.

Run one case from the plugin root:

    claude plugin eval . --case automate-task-loads --scaffold --no-publish --runs 1 --ablation none

Run all six:

    claude plugin eval . --tag smoke --scaffold --no-publish --runs 1 --ablation none

Every run starts a model session with your credentials. It counts against your plan usage, or
against your API bill if an API key is set in your environment.
The `fixture.sh` scripts run on your machine outside the sandbox, and only with `--scaffold`.
Raw results go to `evals/results/`, which git ignores.
`RESULTS.md` records what the six cases did in one run.

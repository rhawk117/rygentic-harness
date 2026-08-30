from plugin_evals.cases import CaseSpec
from plugin_evals.evaluators import FileContains, FileContainsAll, FileExists

PLUGIN = 'ai-engineer'


def _build_migration_reviewer_agent() -> CaseSpec:
    task = (
        'Add a Claude Code subagent that reviews database migration files before '
        'they merge: it should flag missing rollback scripts and destructive schema '
        'changes. Create the agent definition file so it is ready to dispatch.'
    )
    agent = '.claude/agents/migration-reviewer.md'
    return CaseSpec(
        name='build-an-agent-migration-reviewer',
        plugin=PLUGIN,
        skill='build-an-agent',
        fixture='fx-webapp',
        task=task,
        sim_notes='',
        checks=(
            FileExists(check='agent definition file created', path=agent),
            FileContainsAll(
                check='frontmatter carries name and description',
                path=agent,
                needles=['name:', 'description:'],
            ),
            FileContains(
                check='scoped to migration review', path=agent, needle='migration'
            ),
        ),
    )


SPECS: tuple[CaseSpec, ...] = (_build_migration_reviewer_agent(),)

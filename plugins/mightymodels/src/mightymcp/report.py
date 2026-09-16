from pydantic import BaseModel, Field

from mightymcp.artifacts import bullets, cap_refusals, ticket_directory

REPORT = 'REPORT.md'
REPORT_CAP = 50


class ShippedTask(BaseModel):
    """One task's line in the report: what shipped, and the commit it shipped in."""

    task_id: str = Field(description='Brief stem, e.g. task-03')
    shipped: str = Field(description='What the task shipped, in one line')
    commit: str = Field(description='The commit the task landed in')


class ChecklistTask(BaseModel):
    """One task's box in the issue checklist, checked once it carries a commit."""

    label: str = Field(description='Checklist label, e.g. T1')
    title: str = Field(description='What the task does, in a few words')
    sha: str = Field(default='', description='The commit; empty leaves the box unchecked')


class ReportWrite(BaseModel):
    """REPORT.md as regenerated, or why nothing was written."""

    path: str | None = Field(default=None, description='Absolute path of REPORT.md')
    text: str = Field(default='', description='The report as written')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was written'
    )


class Checklist(BaseModel):
    """The issue's Tasks block, one line per task."""

    lines: list[str] = Field(default_factory=list, description='The rendered task lines')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was rendered'
    )


def report_write(
    slug: str,
    tasks: list[ShippedTask],
    residuals_fixed: int,
    escalated: list[str],
    open_threads: list[str],
) -> ReportWrite:
    """Regenerate REPORT.md: what shipped per task, residuals, escalations, threads."""
    directory, refusals = ticket_directory(slug)
    text = _render_report(slug, tasks, residuals_fixed, escalated, open_threads)
    refusals.extend(cap_refusals(REPORT, text, REPORT_CAP))
    if directory is None or refusals:
        return ReportWrite(refusals=refusals)

    path = directory.joinpath(REPORT)
    path.write_text(text, encoding='utf-8')
    return ReportWrite(path=str(path), text=text)


def checklist_render(tasks: list[ChecklistTask]) -> Checklist:
    """Render the issue's Tasks block: a checked box carries the commit it shipped in."""
    refusals = [
        f'checklist entry {number} is missing a label or a title'
        for number, task in enumerate(tasks, start=1)
        if not task.label.strip() or not task.title.strip()
    ]
    if refusals:
        return Checklist(refusals=refusals)
    return Checklist(lines=[_checklist_line(task) for task in tasks])


def _checklist_line(task: ChecklistTask) -> str:
    if task.sha:
        return f'- [x] {task.label} {task.title} ({task.sha})'
    return f'- [ ] {task.label} {task.title}'


def _render_report(
    slug: str,
    tasks: list[ShippedTask],
    residuals_fixed: int,
    escalated: list[str],
    open_threads: list[str],
) -> str:
    lines = [f'# REPORT: {slug}', '']
    lines.extend(f'- {task.task_id}: {task.shipped} ({task.commit})' for task in tasks)
    lines.extend(('', f'residuals fixed: {residuals_fixed}', 'escalated:'))
    lines.extend(bullets(escalated))
    lines.append('open threads:')
    lines.extend(bullets(open_threads))
    return '\n'.join(lines) + '\n'

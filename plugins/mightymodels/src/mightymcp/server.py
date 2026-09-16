from mcp.server import MCPServer

from mightymcp.attempts import task_record_attempt
from mightymcp.brief import brief_append_done, brief_open, brief_read
from mightymcp.debug import whats_broken_close, whats_broken_write
from mightymcp.dialectic import dialectic_record_write, dialectic_score
from mightymcp.fleet import Fleet, load_fleet, render_fleet
from mightymcp.handoff import decision_record, handoff_prompt, handoff_write
from mightymcp.report import checklist_render, report_write
from mightymcp.resources import register_resources
from mightymcp.review import (
    findings_merge,
    grade_compute,
    pr_comment_render,
    review_report_write,
    review_verdict,
)
from mightymcp.routing import blast_radius_questions, route_finding, route_ramp
from mightymcp.scripts import (
    crashout_add,
    crashout_last,
    crashout_stats,
    metrics_run,
)
from mightymcp.status import sprint_status
from mightymcp.ticket import (
    resolve_model,
    ticket_create,
    ticket_read,
    ticket_update_context,
)
from mightymcp.worker_reports import parse_report

server = MCPServer(
    name='mightymodels',
    version='0.9.0',
    instructions=(
        'The mightymodels workflow as tools. Use fleet_roster to see which agents the '
        'plugin ships, resolve_model and the route_ tools to pick a worker or a ramp, '
        'and the ticket_ and sprint_status tools to read and write the ticket state '
        'under .mightymodels/. The brief_ tools carry the two-half task brief, '
        'task_record_attempt logs an attempt and reports where it escalates, and '
        'report_write, whats_broken_, handoff_, and decision_record write the rest of '
        'the sprint artifacts. parse_report turns a worker report into a verdict, the '
        'review_ and findings_ tools apply the merge gate and the uncle-bob rubric, '
        'dialectic_ breaks a tie, and the crashout_ and metrics_ tools run the skills '
        'scripts. Every tool returns a refusals list; a non-empty one means nothing '
        'was written.'
    ),
)


@server.tool()
def fleet_roster() -> Fleet:
    """List every agent the mightymodels plugin ships, with its job and model."""
    return load_fleet()


@server.resource('mm://fleet', name='fleet', mime_type='text/plain')
def fleet_resource() -> str:
    """The agent fleet as one line per worker: name (model): job."""
    return render_fleet(load_fleet())


for tool in (
    ticket_read,
    ticket_create,
    ticket_update_context,
    resolve_model,
    route_ramp,
    route_finding,
    sprint_status,
    brief_open,
    brief_append_done,
    brief_read,
    task_record_attempt,
    report_write,
    checklist_render,
    whats_broken_write,
    whats_broken_close,
    handoff_write,
    handoff_prompt,
    decision_record,
    parse_report,
    findings_merge,
    review_verdict,
    review_report_write,
    grade_compute,
    blast_radius_questions,
    pr_comment_render,
    dialectic_score,
    dialectic_record_write,
    crashout_add,
    crashout_stats,
    crashout_last,
    metrics_run,
):
    server.add_tool(tool)

register_resources(server)


def main() -> None:
    server.run()

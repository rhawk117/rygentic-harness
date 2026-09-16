from mcp.server import MCPServer

from mightymcp.attempts import task_record_attempt
from mightymcp.brief import brief_append_done, brief_open, brief_read
from mightymcp.debug import whats_broken_close, whats_broken_write
from mightymcp.fleet import Fleet, load_fleet, render_fleet
from mightymcp.handoff import decision_record, handoff_prompt, handoff_write
from mightymcp.report import checklist_render, report_write
from mightymcp.routing import route_finding, route_ramp
from mightymcp.status import sprint_status
from mightymcp.ticket import (
    resolve_model,
    ticket_create,
    ticket_read,
    ticket_update_context,
)

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
        'the sprint artifacts. Every tool returns a refusals list; a non-empty one '
        'means nothing was written.'
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
):
    server.add_tool(tool)


def main() -> None:
    server.run()

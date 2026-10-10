"""The `mightymodels subagent-handback` command, run by the PostToolUse hook on SubagentHandback.

On Claude Code 2.1.271 or later a subagent in auto mode delivers its report through the
SubagentHandback tool, and the `last_assistant_message` of its SubagentStop is closing text. The
hook input is the PostToolUse input of that call inside the subagent: `agent_type` and `agent_id`
say who handed back and `tool_input.message` is the report. For `mightymodels:code-scout` and
`mightymodels:web-scout` the command leaves the message in the scout-report spool exactly as
`subagent_record.py` does, under `HANDBACK_PART`, so the server stores it and drops the closing text
the same agent stops with. Any other agent type, and a message that is missing, blank or not text,
leaves the spool as it is.

The command never blocks and never changes a hand-back: it exits 0 with nothing on standard output,
and says on standard error why it did nothing.
"""

from mightymodels_plugin.commands.hook_context import HookContext
from mightymodels_plugin.commands.rejection import skipped
from mightymodels_plugin.commands.subagent_record import (
    NoReportError,
    ScoutStop,
    scout_report_of,
    spool_report,
)
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.tools.similarity.spool import HANDBACK_PART

TOOL_INPUT_KEY = 'tool_input'
MESSAGE_KEY = 'message'


def scout_handback_of(fields: dict[str, object]) -> ScoutStop | NoReportError | None:
    tool_input = fields.get(TOOL_INPUT_KEY)
    message = tool_input.get(MESSAGE_KEY) if isinstance(tool_input, dict) else None
    return scout_report_of(fields, message)


def run_hook(context: HookContext) -> int:
    fields = context.fields()
    if isinstance(fields, StateError):
        return skipped(fields)
    handback = scout_handback_of(fields)
    if handback is None:
        return 0
    if isinstance(handback, NoReportError):
        return skipped(handback)
    failure = spool_report(handback, context, HANDBACK_PART)
    return 0 if failure is None else skipped(failure)

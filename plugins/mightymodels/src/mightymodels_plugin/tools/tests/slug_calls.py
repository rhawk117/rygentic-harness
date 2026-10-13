from mcp.types import CallToolResult

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.tests.support import StateServer, ToolCall

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
REVIEW = {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'}
WRITE: ToolCall = (
    'ticket',
    {
        'action': 'write',
        'fields': {
            'summary': 'Retry queue drains slowly',
            'scope': 'med',
            'compaction': False,
            'branch': 'fix/retry-queue',
            'context': ['drain loop sleeps between batches'],
        },
    },
)
VALIDATE: ToolCall = ('ticket', {'action': 'validate'})
SHOW: ToolCall = ('ticket', {'action': 'show'})
START_REVIEW: ToolCall = ('review', {'request': {'action': 'start', 'payload': REVIEW}})


def slug_results(server: StateServer, *calls: ToolCall) -> list[CallToolResult]:
    requests: list[ToolCall] = [
        (name, {'request': {'slug': SLUG, **arguments}}) for name, arguments in calls
    ]
    return server.call(*requests)

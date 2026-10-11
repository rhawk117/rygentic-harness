import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from operator import attrgetter
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

import sqlalchemy as sql
from mcp import Client
from mcp.client.context import ClientRequestContext
from mcp.types import (
    CallToolResult,
    ElicitRequestFormParams,
    ElicitRequestParams,
    ElicitResult,
    InputRequiredResult,
)

from mightymodels_plugin.core.declarative import Base
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.core.workspace import workspace_at
from mightymodels_plugin.server import build_server
from mightymodels_plugin.tools.review.tables import ReviewRunRow
from mightymodels_plugin.tools.tests.support import StateServer, workspace_database

if TYPE_CHECKING:
    from mcp.types import InputResponses

type Arguments = dict[str, object]
type Stored = Callable[[StateServer], object]

SLUG = 'retry-queue'
TICKET_INTERVIEW: Arguments = {
    'summary': 'Retry queue drains slowly',
    'context': ['drain loop sleeps between batches'],
}
HANDOFF_LINE = re.compile(r'^  (scope|plan-first|branch-name): (.*)$', re.MULTILINE)


def rows_read[Stored: Base, Value](
    server: StateServer, row_type: type[Stored], project: Callable[[Stored], Value]
) -> list[Value]:
    assert isinstance(server.data_directory, Path)
    with (
        workspace_database(workspace_at(server.root), server.data_directory) as database,
        database.transaction() as session,
    ):
        return [project(row) for row in session.scalars(sql.select(row_type)).all()]


def review_runs(server: StateServer) -> object:
    return rows_read(server, ReviewRunRow, attrgetter('scope', 'depth', 'emphasis'))


def ticket_handoff(server: StateServer) -> object:
    ticket = workspace_at(server.root).ticket_file(Slug(SLUG))
    if not ticket.is_file():
        return []
    return HANDOFF_LINE.findall(ticket.read_text(encoding='utf-8'))


async def not_asked(context: ClientRequestContext, params: ElicitRequestParams) -> ElicitResult:
    asked = f'{context.session}: {params.message}'
    raise AssertionError(asked)


@dataclass(slots=True, kw_only=True, frozen=True)
class Replies:
    fallback: ElicitResult
    by_resolver: Mapping[str, ElicitResult] = MappingProxyType({})

    def __call__(self, key: str) -> ElicitResult:
        return self.by_resolver.get(key.rsplit(':', 1)[-1], self.fallback)


@dataclass(slots=True, kw_only=True, frozen=True)
class Exchange:
    first: CallToolResult | InputRequiredResult
    before: object
    between: object
    final: CallToolResult | InputRequiredResult | None
    after: object

    def questions(self) -> list[ElicitRequestFormParams]:
        assert isinstance(self.first, InputRequiredResult)
        assert self.first.input_requests is not None
        asked = [request.params for request in self.first.input_requests.values()]
        assert all(isinstance(params, ElicitRequestFormParams) for params in asked)
        return [params for params in asked if isinstance(params, ElicitRequestFormParams)]

    def question(self) -> ElicitRequestFormParams:
        (only,) = self.questions()
        return only

    def result(self) -> CallToolResult:
        assert isinstance(self.final, CallToolResult)
        return self.final

    def refused(self) -> CallToolResult:
        refused = self.final if self.final is not None else self.first
        assert isinstance(refused, CallToolResult)
        return refused


async def exchange_with(
    server: StateServer, tool: str, arguments: Arguments, stored: Stored, replies: Replies | None
) -> Exchange:
    async with Client(
        build_server(server.root, server.data_directory), elicitation_callback=not_asked
    ) as client:
        before = stored(server)
        first = await client.session.call_tool(
            tool, {'request': arguments}, allow_input_required=True
        )
        between = stored(server)
        final = None
        if replies is not None and isinstance(first, InputRequiredResult):
            assert first.input_requests is not None
            answers: InputResponses = {key: replies(str(key)) for key in first.input_requests}
            final = await client.session.call_tool(
                tool,
                {'request': arguments},
                input_responses=answers,
                request_state=first.request_state,
                allow_input_required=True,
            )
        after = stored(server)
        return Exchange(first=first, before=before, between=between, final=final, after=after)


def said(result: CallToolResult) -> str:
    assert result.structured_content is not None
    return str(result.structured_content['text'])


def unanswered(action: Literal['cancel', 'decline']) -> Replies:
    return Replies(fallback=ElicitResult(action=action))

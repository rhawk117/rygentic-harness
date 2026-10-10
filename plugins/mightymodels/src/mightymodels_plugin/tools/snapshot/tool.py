"""The `snapshot` tool: it takes a ticket and a limit and asks the snapshot service.

The model chooses no action, so the schema shows `slug` and `limit` only. The tool still holds
its one handler under `SnapshotAction.TAKE` and dispatches through `dispatch_to_service`, so it
is an `ActionTool` like the others and its failures cross the same one translation.

`ResolvedSnapshots` is a plain assignment because the SDK does not see a `Resolve` marker behind
a PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels_plugin.tools.snapshot.schema import (
    DEFAULT_LIMIT,
    Limit,
    SnapshotAction,
    SnapshotView,
)
from mightymodels_plugin.tools.snapshot.service import SnapshotService


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotCall:
    slug: Slug
    limit: int


def take_snapshot(snapshots: SnapshotService, call: SnapshotCall) -> SnapshotView:
    return snapshots.take(call.slug, call.limit)


def lifespan_snapshots(ctx: Context[ServedState]) -> SnapshotService:
    return served_services(ctx).snapshots


ResolvedSnapshots = Annotated[SnapshotService, Resolve(lifespan_snapshots)]


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotTool:
    handlers: Mapping[SnapshotAction, ServiceHandler[SnapshotService, SnapshotCall, SnapshotView]]

    def snapshot(
        self, slug: Slug, limit: Limit = DEFAULT_LIMIT, *, snapshots: ResolvedSnapshots
    ) -> SnapshotView:
        """Return the ticket's objective state as JSON and Markdown text for baton-pass to write."""
        call = SnapshotCall(slug=slug, limit=limit)
        return dispatch_to_service(self.handlers, SnapshotAction.TAKE, call, service=snapshots)


snapshot_tool = SnapshotTool(handlers=MappingProxyType({SnapshotAction.TAKE: take_snapshot}))
snapshot_action_tool: ActionTool[SnapshotAction, SnapshotService, SnapshotCall, SnapshotView] = (
    snapshot_tool
)

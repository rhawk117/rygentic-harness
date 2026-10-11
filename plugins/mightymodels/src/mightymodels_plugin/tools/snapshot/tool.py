"""The `snapshot` tool: it takes a ticket and a limit and asks the snapshot service.

The model chooses no action, so the request shows `slug` and `limit` only. The tool still holds
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

from mightymodels_plugin.tools.protocol import (
    ActionHandler,
    ActionTool,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels_plugin.tools.snapshot.schema import (
    SnapshotAction,
    SnapshotRequest,
    SnapshotView,
)
from mightymodels_plugin.tools.snapshot.service import SnapshotService


def take_snapshot(snapshots: SnapshotService, request: SnapshotRequest) -> SnapshotView:
    return snapshots.take(request.slug, request.limit)


def lifespan_snapshots(ctx: Context[ServedState]) -> SnapshotService:
    return served_services(ctx).snapshots


ResolvedSnapshots = Annotated[SnapshotService, Resolve(lifespan_snapshots)]


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotTool:
    handlers: Mapping[
        SnapshotAction, ServiceHandler[SnapshotService, SnapshotRequest, SnapshotView]
    ]

    def snapshot(self, request: SnapshotRequest, *, snapshots: ResolvedSnapshots) -> SnapshotView:
        """Return the ticket's objective state as JSON and Markdown text for baton-pass to write."""
        return dispatch_to_service(self.handlers, SnapshotAction.TAKE, request, service=snapshots)


snapshot_tool = SnapshotTool(
    handlers=MappingProxyType(
        {SnapshotAction.TAKE: ActionHandler(variant=SnapshotRequest, handle=take_snapshot)}
    )
)
snapshot_action_tool: ActionTool[SnapshotAction, SnapshotService, SnapshotRequest, SnapshotView] = (
    snapshot_tool
)

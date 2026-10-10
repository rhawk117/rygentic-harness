"""The `state` MCP server the plugin registers in `.mcp.json`: its lifespan state and its tools.

The lifespan opens the state once when a client connects, the workspace at the git toplevel and
the database in the plugin data directory, builds each service over what it needs of the two, and
disposes the engine when the client closes.

The server needs a plugin data directory and a git work tree, and with either missing it creates
nothing and still starts: its lifespan state is then a `StartRefusal`, and every tool call is
answered with the reason, which names what is missing. A database file of another schema
version is refused the same way.

`AppState` holds one service per tool and nothing else: the workspace and the database are
reached only through the services built over them.

The SDK builds each tool's argument model open, so an argument the tool does not name would be
dropped and the call answered as if it were absent. `tool_refusing_unknown_arguments` gives the
tool that model again with extra arguments forbidden, which refuses such a call by the argument's
name before the tool runs and publishes the closed top level in the served schema.
"""

import os
from collections.abc import AsyncGenerator, Callable
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.tools import Tool
from pydantic import create_model

from mightymodels_plugin.core.data_directory import (
    PLUGIN_DATA_VARIABLE,
    DataDirectory,
    data_directory_from,
)
from mightymodels_plugin.core.edge import open_state
from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.core.process import process_runner
from mightymodels_plugin.core.workspace import find_root
from mightymodels_plugin.tools.close.service import CloseService
from mightymodels_plugin.tools.close.tool import close_tool
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.contract.tool import contract_tool
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.crashout.tool import crashout_tool
from mightymodels_plugin.tools.failed_fix.tool import failed_fix_tool
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.investigation.tool import investigation_tool
from mightymodels_plugin.tools.protocol import ServedState, StartRefusal
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.review.tool import review_tool
from mightymodels_plugin.tools.row_types import ROW_TYPES
from mightymodels_plugin.tools.similarity.service import SimilarityService
from mightymodels_plugin.tools.similarity.spool import SPOOL_DIRECTORY
from mightymodels_plugin.tools.similarity.tool import similarity_tool
from mightymodels_plugin.tools.snapshot.service import SnapshotService
from mightymodels_plugin.tools.snapshot.tool import snapshot_tool
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.task.tool import task_tool
from mightymodels_plugin.tools.ticket.service import TicketService
from mightymodels_plugin.tools.ticket.tool import ticket_tool

SERVER_NAME = 'state'
TOOLS = (
    ticket_tool.ticket,
    task_tool.task,
    contract_tool.contract,
    review_tool.review,
    snapshot_tool.snapshot,
    close_tool.close,
    investigation_tool.investigation,
    crashout_tool.crashout,
    similarity_tool.similarity,
    failed_fix_tool.failed_fix,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class AppState:
    tickets: TicketService
    tasks: TaskService
    contracts: ContractService
    reviews: ReviewService
    snapshots: SnapshotService
    closings: CloseService
    investigations: InvestigationService
    crashouts: CrashoutService
    similarity: SimilarityService


def tool_refusing_unknown_arguments(served: Callable[..., object]) -> Tool:
    tool = Tool.from_function(served)
    open_arguments = tool.fn_metadata.arg_model
    closed_arguments = create_model(
        open_arguments.__name__, __base__=open_arguments, __cls_kwargs__={'extra': 'forbid'}
    )
    return tool.model_copy(
        update={
            'parameters': closed_arguments.model_json_schema(by_alias=True),
            'fn_metadata': tool.fn_metadata.model_copy(update={'arg_model': closed_arguments}),
        }
    )


def build_server(start: Path, data_directory: DataDirectory) -> MCPServer[ServedState]:
    @asynccontextmanager
    async def lifespan(_: MCPServer[ServedState]) -> AsyncGenerator[ServedState]:
        with ExitStack() as opened:
            try:
                state = opened.enter_context(open_state(start, data_directory, ROW_TYPES))
            except StateError as error:
                yield StartRefusal(error=error)
                return
            workspace, database = state.workspace, state.database
            spool = state.data_directory.joinpath(SPOOL_DIRECTORY)
            yield AppState(
                tickets=TicketService(workspace=workspace, database=database),
                tasks=TaskService(workspace=workspace, database=database),
                contracts=ContractService(
                    workspace=workspace, database=database, processes=process_runner()
                ),
                reviews=ReviewService(workspace=workspace, database=database),
                snapshots=SnapshotService(workspace=workspace, database=database),
                closings=CloseService(workspace=workspace, database=database),
                investigations=InvestigationService(workspace=workspace, database=database),
                crashouts=CrashoutService(database=database),
                similarity=SimilarityService(database=database, spool=spool),
            )

    tools = list(map(tool_refusing_unknown_arguments, TOOLS))
    return MCPServer(SERVER_NAME, lifespan=lifespan, tools=tools)


def serve() -> None:
    start = find_root(os.environ, Path.cwd())
    build_server(start, data_directory_from(os.environ, PLUGIN_DATA_VARIABLE)).run()

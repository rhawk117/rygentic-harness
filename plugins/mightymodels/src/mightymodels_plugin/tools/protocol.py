"""What the state tools share: one interface, one dispatch and one way a failure reaches the model.

A tool is an instance holding a handler per action. The server registers the tool's bound method,
the SDK fills that method's resolved parameter from the lifespan state, and the method hands its
handlers and its arguments to a dispatch, which runs the one handler. The SDK shows the model the
text of a `ToolError` and hides everything else as a crash, so the failures the services
anticipate are translated in `state_errors_as_tool_errors` and nowhere else.

Each tool module binds its instance a second time under `ActionTool`, as `<domain>_action_tool`,
which is what makes the type checker hold the tool to the interface. Annotating the instance
itself would hide its registered method from the server.

A handler takes its domain's service and the call. Each tool resolves the service the lifespan
built and dispatches through `dispatch_to_service`, and the service opens its own transactions.

`LifespanState` is what the tools need from the server's lifespan state: one service per tool
and nothing else. The server's `AppState` satisfies it, and it is declared here because the server
imports the tools.

A server that could not open its state still starts, so that the reason reaches whoever calls a
tool. Its lifespan state is then a `StartRefusal` holding that reason. Every tool reaches its
service through `served_services`, which is the one place that tells the two apart: it hands out
the services, or raises the refusal as a `ToolError` before the tool does anything. It also takes
in the scout reports waiting in the spool before it hands the services out, so every call that
reaches a service finds the reports written since the last one.
"""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from mightymodels_plugin.core.errors import StateError
from mightymodels_plugin.tools.close.service import CloseService
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.similarity.service import SimilarityService
from mightymodels_plugin.tools.snapshot.service import SnapshotService
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.ticket.service import TicketService


@runtime_checkable
class ServiceHandler[Service, Call, View](Protocol):
    def __call__(self, service: Service, call: Call, /) -> View: ...


class MissingArgumentsError(StateError):
    def __init__(self, action: str, needs: str) -> None:
        super().__init__(f'{action} needs {needs}')
        self.action = action
        self.needs = needs


@runtime_checkable
class ActionTool[Action, Service, Call, View](Protocol):
    @property
    def handlers(self) -> Mapping[Action, ServiceHandler[Service, Call, View]]: ...


@runtime_checkable
class LifespanState(Protocol):
    @property
    def tickets(self) -> TicketService: ...

    @property
    def tasks(self) -> TaskService: ...

    @property
    def contracts(self) -> ContractService: ...

    @property
    def reviews(self) -> ReviewService: ...

    @property
    def snapshots(self) -> SnapshotService: ...

    @property
    def closings(self) -> CloseService: ...

    @property
    def investigations(self) -> InvestigationService: ...

    @property
    def crashouts(self) -> CrashoutService: ...

    @property
    def similarity(self) -> SimilarityService: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class StartRefusal:
    error: StateError


type ServedState = LifespanState | StartRefusal


def served_services(ctx: Context[ServedState]) -> LifespanState:
    served = ctx.request_context.lifespan_context
    if isinstance(served, StartRefusal):
        raise ToolError(str(served.error)) from served.error
    served.similarity.take_in_spool()
    return served


@contextmanager
def state_errors_as_tool_errors() -> Generator[None]:
    try:
        yield
    except StateError as error:
        raise ToolError(str(error)) from error


def dispatch_to_service[Action, Service, Call, View](
    handlers: Mapping[Action, ServiceHandler[Service, Call, View]],
    action: Action,
    call: Call,
    *,
    service: Service,
) -> View:
    with state_errors_as_tool_errors():
        return handlers[action](service, call)

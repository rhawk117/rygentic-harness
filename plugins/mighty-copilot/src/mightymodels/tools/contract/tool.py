"""The `contract` tool: each handler takes its action's request and asks the contract service.

`approve` takes the approver from each command. A call whose commands name none asks the user
through `AskedApproval`, and only a user who approves gets the commands recorded.

`ServedContract` holds the service and the user's answer, which a tool's argument limit leaves no
room to take as two parameters.

`ResolvedContracts` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.elicitation import ElicitationResult
from mcp.server.mcpserver import Context, Resolve

from mightymodels.tools.asking import chosen, needs_input_text
from mightymodels.tools.contract.questions import (
    ApprovalAnswer,
    AskedApproval,
    all_approved,
    approval_question,
)
from mightymodels.tools.contract.schema import (
    USER_APPROVER,
    ApprovalChoice,
    ApproveContract,
    ContractAction,
    ContractCommand,
    ContractRequest,
    ContractView,
    StatusContract,
)
from mightymodels.tools.contract.service import ContractService
from mightymodels.tools.protocol import (
    ActionHandler,
    ActionTool,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractServed:
    contracts: ContractService
    asked: ElicitationResult[ApprovalAnswer]


def approved_by_user(command: ContractCommand) -> ContractCommand:
    if command.approved_by.strip():
        return command
    return command.model_copy(update={'approved_by': USER_APPROVER})


def approve_commands(served: ContractServed, request: ApproveContract) -> ContractView:
    approval = chosen(served.asked)
    if approval in {ApprovalChoice.REMOVE, ApprovalChoice.EDIT}:
        text = f'not approved: the user chose to {approval}; revise the commands, then call again\n'
        return ContractView(text=text, passing=False)
    if approval is None and not all_approved(request.commands):
        text = needs_input_text([approval_question(request.commands)])
        return ContractView(text=text, passing=False)
    return served.contracts.approve(request.slug, list(map(approved_by_user, request.commands)))


def report_status(served: ContractServed, request: StatusContract) -> ContractView:
    return served.contracts.status(request.slug)


def lifespan_contracts(ctx: Context[ServedState]) -> ContractService:
    return served_services(ctx).contracts


ResolvedContracts = Annotated[ContractService, Resolve(lifespan_contracts)]


def serve_contracts(contracts: ResolvedContracts, asked: AskedApproval) -> ContractServed:
    return ContractServed(contracts=contracts, asked=asked)


ServedContract = Annotated[ContractServed, Resolve(serve_contracts)]


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractTool:
    handlers: Mapping[ContractAction, ServiceHandler[ContractServed, ContractRequest, ContractView]]

    def contract(self, request: ContractRequest, *, served: ServedContract) -> ContractView:
        """Approve verification commands, or report the latest result per command."""
        return dispatch_to_service(self.handlers, request.action, request, service=served)


contract_tool = ContractTool(
    handlers=MappingProxyType(
        {
            ContractAction.APPROVE: ActionHandler(variant=ApproveContract, handle=approve_commands),
            ContractAction.STATUS: ActionHandler(variant=StatusContract, handle=report_status),
        }
    )
)
contract_action_tool: ActionTool[ContractAction, ContractServed, ContractRequest, ContractView] = (
    contract_tool
)

"""The `contract` tool: each handler checks the call's arguments and asks the contract service.

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

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.asking import chosen, needs_input_text
from mightymodels_plugin.tools.contract.questions import (
    ApprovalAnswer,
    AskedApproval,
    all_approved,
    approval_question,
)
from mightymodels_plugin.tools.contract.schema import (
    USER_APPROVER,
    ApprovalChoice,
    ContractAction,
    ContractCommand,
    ContractView,
)
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractCall:
    slug: Slug
    commands: list[ContractCommand] | None
    asked: ElicitationResult[ApprovalAnswer]


def approved_by_user(command: ContractCommand) -> ContractCommand:
    if command.approved_by.strip():
        return command
    return command.model_copy(update={'approved_by': USER_APPROVER})


def approve_commands(contracts: ContractService, call: ContractCall) -> ContractView:
    if call.commands is None:
        raise MissingArgumentsError(ContractAction.APPROVE, 'the commands the user approved')
    approval = chosen(call.asked)
    if approval in {ApprovalChoice.REMOVE, ApprovalChoice.EDIT}:
        text = f'not approved: the user chose to {approval}; revise the commands, then call again\n'
        return ContractView(text=text, passing=False)
    if approval is None and not all_approved(call.commands):
        text = needs_input_text([approval_question(call.commands)])
        return ContractView(text=text, passing=False)
    return contracts.approve(call.slug, list(map(approved_by_user, call.commands)))


def report_status(contracts: ContractService, call: ContractCall) -> ContractView:
    return contracts.status(call.slug)


def lifespan_contracts(ctx: Context[ServedState]) -> ContractService:
    return served_services(ctx).contracts


ResolvedContracts = Annotated[ContractService, Resolve(lifespan_contracts)]


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractServed:
    contracts: ContractService
    asked: ElicitationResult[ApprovalAnswer]


def serve_contracts(contracts: ResolvedContracts, asked: AskedApproval) -> ContractServed:
    return ContractServed(contracts=contracts, asked=asked)


ServedContract = Annotated[ContractServed, Resolve(serve_contracts)]


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractTool:
    handlers: Mapping[ContractAction, ServiceHandler[ContractService, ContractCall, ContractView]]

    def contract(
        self,
        action: ContractAction,
        slug: Slug,
        commands: list[ContractCommand] | None = None,
        *,
        served: ServedContract,
    ) -> ContractView:
        """Approve verification commands, or report the latest result per command."""
        call = ContractCall(slug=slug, commands=commands, asked=served.asked)
        return dispatch_to_service(self.handlers, action, call, service=served.contracts)


contract_tool = ContractTool(
    handlers=MappingProxyType(
        {
            ContractAction.APPROVE: approve_commands,
            ContractAction.STATUS: report_status,
        }
    )
)
contract_action_tool: ActionTool[ContractAction, ContractService, ContractCall, ContractView] = (
    contract_tool
)

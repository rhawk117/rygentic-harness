"""The question `contract` puts to the user when a call asks to approve commands nobody approved.

A command carries its approver, so a call whose commands all name one asks nothing. Otherwise the
user is shown the commands and chooses to approve them all, to remove some or to edit. Only
approving records them, as approved by `USER_APPROVER`; the other two choices record nothing and
tell the caller to revise the list and call again. A caller that asked the user itself passes the
approver on the commands.

`AskedApproval` is a plain assignment because the SDK does not see a `Resolve` marker behind a PEP
695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Sequence
from typing import Annotated

from mcp.server.elicitation import ElicitationResult
from mcp.server.mcpserver import Elicit, Resolve

from mightymodels_plugin.tools.asking import Choice, Question, enumerated
from mightymodels_plugin.tools.contract.schema import (
    ApprovalChoice,
    ApproveContract,
    ContractCommand,
    ContractRequest,
)

type Commands = Sequence[ContractCommand]

ApprovalChoices = Annotated[ApprovalChoice, enumerated(ApprovalChoice)]
ApprovalAnswer = Choice[ApprovalChoices]


def command_lines(commands: Commands) -> str:
    return ''.join(f'\n{command.id}: {" ".join(command.argv)}' for command in commands)


def approval_question(commands: Commands) -> Question:
    return Question(
        message=f'Approve these verification commands?{command_lines(commands)}',
        answer=ApprovalAnswer,
        argument='approved_by "user" on each command, once the user approved',
    )


def all_approved(commands: Commands) -> bool:
    return all(command.approved_by.strip() for command in commands)


def ask_approval(request: ContractRequest) -> ApprovalAnswer | Elicit[ApprovalAnswer]:
    if not isinstance(request, ApproveContract) or all_approved(request.commands):
        return ApprovalAnswer(choice=None)
    return Elicit(approval_question(request.commands).message, ApprovalAnswer)


AskedApproval = Annotated[ElicitationResult[ApprovalAnswer], Resolve(ask_approval)]

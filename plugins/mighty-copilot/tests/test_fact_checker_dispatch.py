"""No dispatch row names the fact-checker and its own row is empty, so no worker dispatches it
and the main conversation's dispatch of it gets no decision."""

import json
from dataclasses import dataclass, field

import pytest
from mightymodels.commands.dispatch_hook import (
    DISPATCH_RULES,
    BranchTickets,
    BranchTicketsOrUnreadable,
    Denied,
    StartedOrUnreadable,
    agent_type,
    dispatch_ruling,
)
from mightymodels.core.routing import Worker

FACT_CHECKER = 'mightymodels:review:fact-checker'


@dataclass(slots=True, kw_only=True, frozen=True)
class NoStartedTasks:
    asked: list[Worker | None] = field(default_factory=list)

    def started_by(self, worker: Worker) -> StartedOrUnreadable:
        self.asked.append(worker)
        return ()

    def tickets_on_branch(self) -> BranchTicketsOrUnreadable:
        self.asked.append(None)
        return BranchTickets()


def hook_input(caller: str | None, target: str) -> str:
    fields: dict[str, object] = {'tool_name': 'Agent', 'tool_input': {'subagent_type': target}}
    if caller is not None:
        fields['agent_type'] = caller
    return json.dumps(fields)


def row_named(caller: Worker) -> str:
    return ', '.join(sorted(DISPATCH_RULES[caller])) or 'nothing'


class TestRows:
    def test_its_own_row_is_empty(self) -> None:
        assert DISPATCH_RULES[Worker.FACT_CHECKER] == frozenset()

    def test_no_workers_row_names_it(self) -> None:
        naming = [worker for worker, row in DISPATCH_RULES.items() if Worker.FACT_CHECKER in row]

        assert naming == []


class TestDispatchOfIt:
    @pytest.mark.parametrize('target', ['fact-checker', FACT_CHECKER])
    @pytest.mark.parametrize('caller', Worker)
    def test_every_workers_dispatch_of_it_is_denied(self, caller: Worker, target: str) -> None:
        dispatcher = agent_type(caller)

        ruling = dispatch_ruling(hook_input(dispatcher, target), NoStartedTasks())

        assert ruling == Denied(
            reason=f'{dispatcher} may not dispatch {target}; it may dispatch: {row_named(caller)}'
        )

    def test_the_main_conversations_dispatch_of_it_gets_no_decision_and_reads_no_state(
        self,
    ) -> None:
        started = NoStartedTasks()

        assert dispatch_ruling(hook_input(None, FACT_CHECKER), started) is None
        assert started.asked == []

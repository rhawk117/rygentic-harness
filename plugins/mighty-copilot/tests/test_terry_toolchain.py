"""Terry-toolchain surveys the environment for game-plan and for nobody else.

No dispatch row names it and its own row is empty, so no worker dispatches it and the main
conversation's dispatch of it gets no decision. Its contract holds the four surveys, the manifests
it falls back to and a capped report. game-plan dispatches it before the draft; one-shot does not.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

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

PLUGIN = Path(__file__).parent.parent
SKILLS = PLUGIN.joinpath('skills')
TERRY_TOOLCHAIN = 'mightymodels:triage:terry-toolchain'


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
        assert DISPATCH_RULES[Worker.TERRY_TOOLCHAIN] == frozenset()

    def test_no_workers_row_names_it(self) -> None:
        naming = [worker for worker, row in DISPATCH_RULES.items() if Worker.TERRY_TOOLCHAIN in row]

        assert naming == []


class TestDispatchOfIt:
    @pytest.mark.parametrize('target', ['terry-toolchain', TERRY_TOOLCHAIN])
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

        assert dispatch_ruling(hook_input(None, TERRY_TOOLCHAIN), started) is None
        assert started.asked == []


class TestContract:
    LINE_LIMIT = 120
    SECTIONS = (
        '## Harness tools',
        '## Skills, plugins and agents',
        '## Repository toolchain',
        '## Sandbox and permissions',
        '## Not seen',
    )

    @pytest.fixture
    def contract(self) -> str:
        return PLUGIN.joinpath('agents', 'triage', 'terry-toolchain.md').read_text(encoding='utf-8')

    def test_it_stays_under_the_line_limit(self, contract: str) -> None:
        assert len(contract.splitlines()) < self.LINE_LIMIT

    @pytest.mark.parametrize(
        'source',
        [
            pytest.param('`claude mcp list`', id='cli-servers'),
            pytest.param('`claude plugin list --json`', id='cli-plugins'),
            pytest.param('`.claude-plugin/plugin.json`', id='plugin-manifest'),
            pytest.param('`.mcp.json`', id='server-manifest'),
            pytest.param('`hooks/hooks.json`', id='hooks-manifest'),
            pytest.param('`.claude/settings.json`', id='settings'),
        ],
    )
    def test_it_names_the_cli_commands_and_the_manifests_it_falls_back_to(
        self, contract: str, source: str
    ) -> None:
        assert source in contract

    def test_the_report_has_a_section_per_survey_then_what_it_could_not_see(
        self, contract: str
    ) -> None:
        found = [contract.find(section) for section in self.SECTIONS]

        assert -1 not in found
        assert found == sorted(found)

    def test_the_report_is_capped(self, contract: str) -> None:
        assert 'The cap is 80 lines.' in contract


class TestRamps:
    @pytest.fixture
    def game_plan(self) -> str:
        return SKILLS.joinpath('game-plan', 'SKILL.md').read_text(encoding='utf-8')

    @pytest.fixture
    def one_shot(self) -> str:
        return SKILLS.joinpath('one-shot', 'SKILL.md').read_text(encoding='utf-8')

    @pytest.fixture
    def engineer_template(self) -> str:
        templates = SKILLS.joinpath('prompting-subagents', 'references', 'templates')
        return templates.joinpath('engineer.md').read_text(encoding='utf-8')

    def test_game_plan_dispatches_it_then_saves_the_report_before_the_draft(
        self, game_plan: str
    ) -> None:
        dispatched = game_plan.find(f'`{TERRY_TOOLCHAIN}`')
        saved = game_plan.find('`toolchain.md`')
        drafted = game_plan.find('**4. Draft the plan')

        assert -1 < dispatched < saved < drafted

    def test_one_shot_does_not_dispatch_it(self, one_shot: str) -> None:
        assert 'terry-toolchain' not in one_shot

    def test_the_engineer_template_has_a_slot_for_the_toolchain_lines(
        self, engineer_template: str
    ) -> None:
        assert '\ntoolchain: [' in engineer_template

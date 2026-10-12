"""A task over four acceptance criteria or ten owned files is refused at `start`.

The refusal names the skill that splits the task. The same start naming the user's approval is
taken, and a task at either bound needs no approval.
"""

from collections.abc import Sequence

import pytest
from mcp.types import CallToolResult
from mightymodels_plugin.tools.task.schema import (
    ACCEPTANCE_BOUND,
    OWNED_BOUND,
    Implementer,
    SizeBound,
    StartTaskPayload,
    TaskStart,
    TooLargeTaskStart,
)
from mightymodels_plugin.tools.task.tests.repo import (
    ADVANCED,
    ANSWERS,
    REJECTED,
    SLUG,
    TICKET,
    TaskRepo,
)
from mightymodels_plugin.tools.tests.support import StateServer, text_of
from mightymodels_plugin.tools.ticket.service import TicketService

FOUR_CRITERIA = ('AC-1', 'AC-2', 'AC-3', 'AC-4')
FIVE_CRITERIA = (*FOUR_CRITERIA, 'AC-5')
TEN_FILES = tuple(f'src/queue_{number}.py' for number in range(10))
ELEVEN_FILES = (*TEN_FILES, 'src/drain.py')
SPLIT_IT = 'split the task with break-it-down'
OVER_THE_CRITERIA = f'5 acceptance criteria is over the 4 one task may have; {SPLIT_IT}'
OVER_THE_FILES = f'11 owned files is over the 10 one task may have; {SPLIT_IT}'
TOO_LARGE: dict[str, object] = {
    'by': 'engineer',
    'owned': list(ELEVEN_FILES),
    'acceptance': list(FIVE_CRITERIA),
}
APPROVED: dict[str, object] = TOO_LARGE | {'too_large_approved_by': 'user'}
APPROVED_BY_THE_USER = 'too large, approved by user'


class TestASizeBound:
    @pytest.mark.parametrize(
        ('bound', 'listed'),
        [
            pytest.param(ACCEPTANCE_BOUND, FIVE_CRITERIA, id='criteria'),
            pytest.param(OWNED_BOUND, ELEVEN_FILES, id='files'),
        ],
    )
    def test_one_over_is_an_error_that_counts_what_was_listed(
        self, bound: SizeBound, listed: Sequence[str]
    ) -> None:
        error = bound.error(listed)

        assert error is not None
        assert (error.counted, error.count, error.limit) == (
            bound.counted,
            len(listed),
            len(listed) - 1,
        )

    @pytest.mark.parametrize(
        ('bound', 'listed'),
        [
            pytest.param(ACCEPTANCE_BOUND, FOUR_CRITERIA, id='criteria'),
            pytest.param(OWNED_BOUND, TEN_FILES, id='files'),
        ],
    )
    def test_a_task_at_the_bound_is_no_error(self, bound: SizeBound, listed: Sequence[str]) -> None:
        assert bound.error(listed) is None


class TestAStartAlreadyValidated:
    @pytest.mark.parametrize(
        'change',
        [
            pytest.param(
                TaskStart(by=Implementer.ENGINEER, owned=TEN_FILES, acceptance=FOUR_CRITERIA),
                id='bounded',
            ),
            pytest.param(
                TooLargeTaskStart(
                    by=Implementer.ENGINEER,
                    owned=ELEVEN_FILES,
                    acceptance=FIVE_CRITERIA,
                    too_large_approved_by='user',
                ),
                id='too-large',
            ),
        ],
    )
    def test_keeps_its_shape_in_a_payload(self, change: TaskStart | TooLargeTaskStart) -> None:
        assert StartTaskPayload(task_id='T1', change=change).change == change


class TestStartingATaskTooLarge:
    def reasons_of_the_start(self, task_repo: TaskRepo) -> list[str]:
        return list(task_repo.store.transitions[-1].transition.reasons)

    @pytest.mark.parametrize(
        ('owned', 'acceptance', 'over'),
        [
            pytest.param(TEN_FILES, FIVE_CRITERIA, OVER_THE_CRITERIA, id='criteria'),
            pytest.param(ELEVEN_FILES, FOUR_CRITERIA, OVER_THE_FILES, id='files'),
        ],
    )
    def test_is_refused_naming_the_skill_and_starts_nothing(
        self, task_repo: TaskRepo, owned: Sequence[str], acceptance: Sequence[str], over: str
    ) -> None:
        outcome = task_repo.run('start', 'T1', by='engineer', owned=owned, acceptance=acceptance)

        assert outcome.code == REJECTED
        assert over in outcome.err
        assert task_repo.transitions() == []

    def test_over_both_bounds_is_refused_for_each(self, task_repo: TaskRepo) -> None:
        outcome = task_repo.run('start', 'T1', **TOO_LARGE)

        assert outcome.code == REJECTED
        assert (OVER_THE_FILES in outcome.err, OVER_THE_CRITERIA in outcome.err) == (True, True)

    @pytest.mark.parametrize(
        ('owned', 'acceptance'),
        [
            pytest.param(TEN_FILES, FIVE_CRITERIA, id='criteria'),
            pytest.param(ELEVEN_FILES, FOUR_CRITERIA, id='files'),
            pytest.param(ELEVEN_FILES, FIVE_CRITERIA, id='both'),
        ],
    )
    def test_the_same_start_naming_the_users_approval_is_taken(
        self, task_repo: TaskRepo, owned: Sequence[str], acceptance: Sequence[str]
    ) -> None:
        outcome = task_repo.run(
            'start',
            'T1',
            by='engineer',
            owned=owned,
            acceptance=acceptance,
            too_large_approved_by='user',
        )

        task = task_repo.task('T1')
        assert outcome.code == ADVANCED
        assert (task.status, task.owned) == ('in-progress', tuple(sorted(owned)))

    def test_the_users_approval_is_written_into_the_reasons_of_the_start(
        self, task_repo: TaskRepo
    ) -> None:
        task_repo.run('start', 'T1', **APPROVED)

        assert self.reasons_of_the_start(task_repo) == ['by engineer', APPROVED_BY_THE_USER]

    def test_a_task_at_both_bounds_starts_with_no_approval(self, task_repo: TaskRepo) -> None:
        outcome = task_repo.run(
            'start', 'T1', by='engineer', owned=TEN_FILES, acceptance=FOUR_CRITERIA
        )

        assert outcome.code == ADVANCED
        assert task_repo.task('T1').owned == tuple(sorted(TEN_FILES))
        assert self.reasons_of_the_start(task_repo) == ['by engineer']

    def test_an_approval_by_anyone_but_the_user_is_refused(self, task_repo: TaskRepo) -> None:
        outcome = task_repo.run('start', 'T1', **TOO_LARGE, too_large_approved_by='primary')

        assert outcome.code == REJECTED
        assert "too_large_approved_by\n  Input should be 'user'" in outcome.err
        assert task_repo.transitions() == []

    @pytest.mark.parametrize(
        'acceptance',
        [pytest.param({}, id='not-given'), pytest.param({'acceptance': []}, id='empty')],
    )
    def test_a_start_that_lists_no_acceptance_criterion_is_refused(
        self, task_repo: TaskRepo, acceptance: dict[str, object]
    ) -> None:
        outcome = task_repo.run('start', 'T1', by='engineer', owned=['src/queue.py'], **acceptance)

        assert outcome.code == REJECTED
        assert 'acceptance' in outcome.err


class TestTheTaskToolOnATaskTooLarge:
    @pytest.fixture
    def staged_server(
        self, state_server: StateServer, ticket_service: TicketService
    ) -> StateServer:
        ticket_service.write(TICKET, ANSWERS)
        ticket_service.validate(TICKET)
        return state_server

    def started(self, server: StateServer, change: dict[str, object]) -> CallToolResult:
        payload = {'task_id': 'T1', 'change': change}
        (result,) = server.call(
            ('task', {'request': {'action': 'start', 'slug': SLUG, 'payload': payload}})
        )
        return result

    def test_start_refuses_it_in_the_schema_naming_the_skill(
        self, staged_server: StateServer
    ) -> None:
        refused = self.started(staged_server, TOO_LARGE)

        assert refused.is_error
        assert f'request.start.payload.change.bounded.owned\n  Value error, {OVER_THE_FILES}' in (
            text_of(refused)
        )
        assert f'change.bounded.acceptance\n  Value error, {OVER_THE_CRITERIA}' in text_of(refused)

    def test_start_takes_the_same_call_naming_the_users_approval(
        self, staged_server: StateServer
    ) -> None:
        started = self.started(staged_server, APPROVED)

        assert not started.is_error
        assert started.structured_content['tasks'][0]['owned'] == sorted(ELEVEN_FILES)

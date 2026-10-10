"""The reviewers' models follow the review's depth, and one override per run moves one to fable."""

from datetime import UTC, datetime

import pytest
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.review.errors import OverrideSpentError
from mightymodels_plugin.tools.review.schema import StartPayload
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.review.tables import ReviewRunRow
from mightymodels_plugin.tools.tests.support import StateServer, text_of
from mightymodels_plugin.tools.ticket.schema import TicketAnswers
from mightymodels_plugin.tools.ticket.service import TicketService
from mightymodels_plugin.tools.ticket.tables import TicketRow

SLUG = 'retry-queue'
STARTED = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
CODEBASE = {'scope': 'codebase', 'emphasis': 'balanced'}
START = {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'release-readiness'}
ANSWERS = TicketAnswers.model_validate(
    {
        'summary': 'Retry queue drains slowly',
        'scope': 'large',
        'compaction': False,
        'branch': 'fix/retry-queue',
        'context': ['drain loop sleeps between batches'],
    }
)


def started_run(reviews: ReviewService, **payload: object) -> RunId:
    view = reviews.start(StartPayload.model_validate({**CODEBASE, **payload}), started=STARTED)
    return RunId(view.run_id or '')


def stored_models(reviews: ReviewService, run: RunId) -> dict[str, str | None]:
    database = reviews.database
    with database.transaction() as session:
        row = session.get(ReviewRunRow, (database.repository_key.root, run.root))
        assert row is not None
        return dict(row.models)


class TestReviewerModelsByDepth:
    @pytest.mark.parametrize(
        ('payload', 'models'),
        [
            pytest.param(
                {'depth': 'quick', 'persona': 'merge-vader'},
                {'merge-vader-reviewer': 'sonnet'},
                id='quick-merge-vader',
            ),
            pytest.param(
                {'depth': 'quick', 'persona': 'uncle-bob'},
                {'uncle-bob-reviewer': 'sonnet'},
                id='quick-uncle-bob',
            ),
            pytest.param(
                {'depth': 'standard'},
                {'merge-vader-reviewer': 'opus', 'uncle-bob-reviewer': 'opus'},
                id='standard',
            ),
            pytest.param(
                {'depth': 'deep'},
                {'merge-vader-reviewer': 'opus', 'uncle-bob-reviewer': 'opus'},
                id='deep',
            ),
        ],
    )
    def test_without_an_override_the_depth_decides_both_reviewers(
        self, review_service: ReviewService, payload: dict[str, str], models: dict[str, str]
    ) -> None:
        run = started_run(review_service, **payload)

        assert stored_models(review_service, run) == models


class TestTicketReviewerEntries:
    @pytest.fixture
    def pinned_ticket(self, review_service: ReviewService, ticket_service: TicketService) -> None:
        ticket_service.write(Slug(SLUG), ANSWERS)
        ticket_service.validate(Slug(SLUG))
        database = review_service.database
        with database.transaction() as session:
            row = session.get(TicketRow, (database.repository_key.root, SLUG))
            assert row is not None
            row.models = {'merge-vader-reviewer': 'haiku', 'uncle-bob-reviewer': 'fable'}

    @pytest.mark.parametrize('depth', ['standard', 'deep'])
    @pytest.mark.usefixtures('pinned_ticket')
    def test_a_ticket_with_reviewer_entries_changes_no_review_models(
        self, review_service: ReviewService, depth: str
    ) -> None:
        run = started_run(review_service, scope='ticket', slug=SLUG, base='HEAD', depth=depth)

        assert stored_models(review_service, run) == {
            'merge-vader-reviewer': 'opus',
            'uncle-bob-reviewer': 'opus',
        }


class TestOverride:
    @pytest.mark.parametrize(
        ('payload', 'models'),
        [
            pytest.param(
                {'depth': 'deep', 'emphasis': 'release-readiness'},
                {'merge-vader-reviewer': 'fable', 'uncle-bob-reviewer': 'opus'},
                id='release-readiness-leads',
            ),
            pytest.param(
                {'depth': 'deep', 'emphasis': 'maintainability'},
                {'merge-vader-reviewer': 'opus', 'uncle-bob-reviewer': 'fable'},
                id='maintainability-leads',
            ),
            pytest.param(
                {'depth': 'deep', 'emphasis': 'balanced'},
                {'merge-vader-reviewer': 'fable', 'uncle-bob-reviewer': 'opus'},
                id='a-tie-favours-merge-vader',
            ),
            pytest.param(
                {
                    'depth': 'standard',
                    'emphasis': 'custom',
                    'weights': {'merge-vader': 0.2, 'uncle-bob': 0.8},
                },
                {'uncle-bob-reviewer': 'fable'},
                id='standard-runs-only-the-heavier',
            ),
            pytest.param(
                {'depth': 'quick', 'emphasis': 'release-readiness', 'persona': 'uncle-bob'},
                {'uncle-bob-reviewer': 'fable'},
                id='quick-runs-the-chosen-persona',
            ),
        ],
    )
    def test_puts_the_heavier_weighted_reviewer_on_fable(
        self, review_service: ReviewService, payload: dict[str, object], models: dict[str, str]
    ) -> None:
        run = started_run(review_service, **payload)

        review_service.override(run)

        assert stored_models(review_service, run) == models

    def test_the_answer_tells_the_caller_to_dispatch_with_high_effort(
        self, review_service: ReviewService
    ) -> None:
        run = started_run(review_service, depth='deep')

        view = review_service.override(run)

        assert view.text == (
            f'run {run}: merge-vader-reviewer on fable\ndispatch it with effort high\n'
        )

    def test_a_second_request_on_the_same_run_is_refused_and_changes_nothing(
        self, review_service: ReviewService
    ) -> None:
        run = started_run(review_service, depth='deep')
        review_service.override(run)
        overridden = stored_models(review_service, run)

        with pytest.raises(OverrideSpentError):
            review_service.override(run)

        assert stored_models(review_service, run) == overridden

    def test_another_run_has_its_own_override(self, review_service: ReviewService) -> None:
        first = started_run(review_service, depth='deep')
        review_service.override(first)
        later = StartPayload.model_validate({**CODEBASE, 'depth': 'deep'})
        second = RunId(review_service.start(later, started=STARTED.replace(second=1)).run_id or '')

        review_service.override(second)

        assert 'fable' in stored_models(review_service, second).values()


class TestOverrideOnTheTool:
    def test_the_review_tool_accepts_the_override_once_per_run(
        self, state_server: StateServer
    ) -> None:
        (started,) = state_server.call(('review', {'action': 'start', 'payload': START}))
        run = started.structured_content['run_id']

        first, second = state_server.call(
            ('review', {'action': 'override', 'run_id': run}),
            ('review', {'action': 'override', 'run_id': run}),
        )

        assert not first.is_error
        assert 'merge-vader-reviewer on fable' in first.structured_content['text']
        assert 'effort high' in first.structured_content['text']
        assert second.is_error
        assert 'has used its one reviewer override' in text_of(second)

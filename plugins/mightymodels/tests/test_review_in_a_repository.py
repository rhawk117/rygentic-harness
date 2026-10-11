"""The review service in a git repository on disk: where a run with no ticket keeps its files."""

from datetime import UTC, datetime

from mightymodels_plugin.core.database import Database
from mightymodels_plugin.core.run_id import RunId
from mightymodels_plugin.tools.review.schema import StartPayload
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.review.tables import ReviewRunRow

WITHOUT_A_TICKET = StartPayload.model_validate(
    {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'}
)


def run_state(database: Database, run: RunId) -> dict[str, object]:
    with database.transaction() as session:
        row = session.get(ReviewRunRow, (database.repository_key.root, run.root))
        assert row is not None
        return {'slug': row.slug}


def test_a_run_without_a_ticket_lives_under_runtime(
    review_service: ReviewService, repository_database: Database
) -> None:
    root = review_service.workspace.root
    view = review_service.start(WITHOUT_A_TICKET, started=datetime.now(tz=UTC))
    assert view.run_id is not None
    run = RunId(view.run_id)
    exclude = root.joinpath('.git', 'info', 'exclude').read_text(encoding='utf-8')
    runtime = root.joinpath('.mightymodels', '.runtime', 'reviews', run.root)
    assert runtime.is_dir()
    assert run_state(repository_database, run)['slug'] is None
    assert '.mightymodels/' in exclude.splitlines()

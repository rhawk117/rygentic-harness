"""The `review` tool through the SDK's in-memory client."""

from dataclasses import dataclass
from pathlib import Path

import pytest
from mcp.types import CallToolResult
from mightymodels_plugin.tools.tests.support import StateServer, text_of

FIXTURE = Path(__file__).parent.joinpath('fixtures', 'merge-vader-report.md')
START = {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'}
DECISIONS = {
    'by': 'user',
    'decisions': {
        'F1': {'decision': 'fix'},
        'F2': {'decision': 'accept-risk', 'reason': 'the endpoint is internal'},
    },
}
FORBIDDEN = ('report.md', 'pr-comment.md', 'review-run.json', 'findings.jsonl')


def review_results(server: StateServer, *calls: dict[str, object]) -> list[CallToolResult]:
    requests: list[dict[str, object]] = [{'request': arguments} for arguments in calls]
    return server.call(*(('review', request) for request in requests))


@dataclass(slots=True, kw_only=True, frozen=True)
class StartedRun:
    run_id: str
    directory: Path


@pytest.fixture
def started_run(state_server: StateServer) -> StartedRun:
    (started,) = review_results(state_server, {'action': 'start', 'payload': START})
    run = started.structured_content['run_id']
    directory = state_server.root.joinpath('.mightymodels', '.runtime', 'reviews', run)
    return StartedRun(run_id=run, directory=directory)


class TestReviewCalls:
    @pytest.fixture
    def run_with_a_report(self, started_run: StartedRun) -> StartedRun:
        report = started_run.directory.joinpath('MERGE-VADER-REPORT.md')
        report.write_text(FIXTURE.read_text(encoding='utf-8'), encoding='utf-8')
        return started_run

    def test_a_run_is_recorded_ingested_decided_resolved_and_reported_without_a_file(
        self, run_with_a_report: StartedRun, state_server: StateServer
    ) -> None:
        run = run_with_a_report.run_id
        directory = run_with_a_report.directory

        added, gate, disposed, resolved, full, comment, listed = review_results(
            state_server,
            {'action': 'add', 'run_id': run, 'payload': {'persona': 'merge-vader'}},
            {'action': 'gate', 'run_id': run},
            {'action': 'dispose', 'run_id': run, 'payload': DECISIONS},
            {
                'action': 'resolve',
                'run_id': run,
                'payload': {'finding': 'F1', 'result': 'fixed', 'commit': 'abc123'},
            },
            {'action': 'report', 'run_id': run},
            {'action': 'report', 'run_id': run, 'payload': {'shape': 'comment'}},
            {'action': 'list'},
        )

        assert added.structured_content['text'] == '5 findings in, 5 recorded: F1, F2, F3, F4, F5\n'
        assert gate.structured_content['text'].splitlines()[0].startswith('F1\tCritical\t[MV-1]')
        assert (
            '2 dispositions recorded; undecided: F3, F4, F5' in disposed.structured_content['text']
        )
        assert resolved.structured_content['text'] == 'F1 fixed\n'
        assert full.structured_content['verdict'] == 'MERGE WITH CONDITIONS'
        assert full.structured_content['text'].startswith('# Review report\n')
        assert comment.structured_content['text'].startswith('## Review\n')
        assert (
            listed.structured_content['text']
            == f'{run}\t-\tdeep\t5 findings\tMERGE WITH CONDITIONS\n'
        )
        assert [path.name for path in directory.iterdir()] == ['MERGE-VADER-REPORT.md']
        assert not any(directory.joinpath(name).exists() for name in FORBIDDEN)

    @pytest.mark.parametrize(
        ('arguments', 'needs'),
        [
            pytest.param(
                {'action': 'start', 'payload': {'shape': 'full'}},
                'request.start.payload.shape\n  Extra inputs are not permitted',
                id='start',
            ),
            pytest.param({'action': 'gate'}, 'request.gate.run_id\n  Field required', id='gate'),
            pytest.param({'action': 'add'}, 'request.add.run_id\n  Field required', id='add-run'),
            pytest.param(
                {'action': 'dispose'}, 'request.dispose.run_id\n  Field required', id='dispose-run'
            ),
            pytest.param(
                {'action': 'resolve'}, 'request.resolve.run_id\n  Field required', id='resolve-run'
            ),
            pytest.param(
                {'action': 'report'}, 'request.report.run_id\n  Field required', id='report-run'
            ),
            pytest.param(
                {'action': 'add', 'run_id': '20260101-000000'},
                'request.add.payload\n  Field required',
                id='add',
            ),
            pytest.param(
                {'action': 'dispose', 'run_id': '20260101-000000'},
                'request.dispose.payload\n  Field required',
                id='dispose',
            ),
            pytest.param(
                {'action': 'resolve', 'run_id': '20260101-000000'},
                'request.resolve.payload\n  Field required',
                id='resolve',
            ),
            pytest.param(
                {
                    'action': 'report',
                    'run_id': '20260101-000000',
                    'payload': {'persona': 'merge-vader'},
                },
                'request.report.payload.persona\n  Extra inputs are not permitted',
                id='report-with-a-persona',
            ),
        ],
    )
    def test_an_action_missing_its_arguments_says_what_it_needs(
        self, arguments: dict[str, object], needs: str, state_server: StateServer
    ) -> None:
        (result,) = review_results(state_server, arguments)

        assert result.is_error
        assert needs in text_of(result)

    def test_an_anticipated_failure_reaches_the_model_as_its_own_text(
        self, state_server: StateServer
    ) -> None:
        (result,) = review_results(state_server, {'action': 'gate', 'run_id': '20260101-000000'})

        assert result.is_error
        assert 'no review run 20260101-000000; start one first' in text_of(result)

    @pytest.mark.parametrize(
        'payload',
        [
            pytest.param({'persona': 'someone-else'}, id='persona'),
            pytest.param({'persona': 'merge-vader', 'findings': []}, id='finding-list'),
        ],
    )
    def test_add_takes_a_persona_and_no_finding_list(
        self, started_run: StartedRun, state_server: StateServer, payload: dict[str, object]
    ) -> None:
        (result,) = review_results(
            state_server, {'action': 'add', 'run_id': started_run.run_id, 'payload': payload}
        )

        assert result.is_error

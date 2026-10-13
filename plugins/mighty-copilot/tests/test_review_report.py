"""`review add` reads a persona's report from the run directory and records its findings."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sql
from mightymodels.core.database import Database
from mightymodels.core.errors import StateError
from mightymodels.core.run_id import RunId
from mightymodels.tools.review.schema import (
    DisposePayload,
    Persona,
    ReviewScope,
    StartPayload,
)
from mightymodels.tools.review.service import REPORT_FILES, ReviewService
from mightymodels.tools.review.tables import ReviewFindingRow

type Stored = tuple[str, str, str, str, bool, str, str, tuple[str, str | None] | None]

FIXTURES = Path(__file__).parent.joinpath('fixtures')
MERGE_VADER = Persona.MERGE_VADER
UNCLE_BOB = Persona.UNCLE_BOB
START = StartPayload(scope=ReviewScope.CODEBASE, depth='deep', emphasis='balanced')
MERGE_VADER_FINDINGS = [
    (
        'MV-1',
        'Critical',
        '.github/workflows/ci.yml:41',
        'defect',
        False,
        'Restore the `--cov-fail-under=90` step in the test job.',
        "`rg -n 'cov-fail-under' .github/workflows/ci.yml`",
        None,
    ),
    (
        'MV-2',
        'High',
        'src/auth/session.py:88',
        'defect',
        True,
        'Use `hmac.compare_digest` for the comparison.',
        '`uv run pytest -q tests/test_session.py`',
        None,
    ),
    (
        'MV-3',
        'Medium',
        'src/billing/store.py:10-140',
        'quality',
        False,
        'Extract a `PriceBook` and have the store call it.',
        "`rg -n 'class PriceBook' src/billing`",
        (
            'metric',
            'uncle-bob-metrics.json violations.functions_over_20_loc: billing/store.py:busy 38',
        ),
    ),
    (
        'MV-4',
        'Medium',
        'src/queue/retry.py:30',
        'defect',
        False,
        (
            "Stop retrying after the plan's cap of five attempts and move the message to the "
            'dead-letter list.'
        ),
        '`uv run pytest -q tests/test_retry.py -k cap`',
        None,
    ),
    (
        'MV-5',
        'Low',
        'README.md:12',
        'defect',
        False,
        'Replace `--drain-fast` with the `--batch` option.',
        "`rg -n -e '--drain-fast' README.md`",
        None,
    ),
]
UNCLE_BOB_FINDINGS = [
    (
        'UB-1',
        'High',
        'src/queue/store.py:12',
        'quality',
        False,
        'Define a `MessageStore` protocol in the queue package and make the store implement it.',
        (
            '`uv run python -c "import queue.store"` with no import cycle reported by the metrics '
            'script'
        ),
        ('metric', 'uncle-bob-metrics.json cycles: queue.store <-> queue.worker'),
    ),
    (
        'UB-2',
        'High',
        'src/queue/domain.py:30-52',
        'quality',
        False,
        'Take the session as an argument instead of importing it.',
        "`rg -n 'sqlalchemy' src/queue/domain.py`",
        (
            'convention',
            (
                'ruff.toml TID251 bans sqlalchemy in domain; src/queue/policy.py:3, '
                'src/queue/retry.py:5 take the session as an argument'
            ),
        ),
    ),
    (
        'UB-3',
        'Medium',
        'src/queue/worker.py:101',
        'quality',
        False,
        'Return the results from `drain`.',
        "`rg -n 'def drain' src/queue/worker.py`",
        ('idiom', 'https://docs.python.org/3.14/tutorial/controlflow.html#defining-functions'),
    ),
    (
        'UB-4',
        'Low',
        'src/queue/store.py:3',
        'quality',
        False,
        'Delete the import.',
        '`uv run ruff check src/queue/store.py`',
        None,
    ),
]
MERGE_VADER_BLOCK = """#### MV-2 | quality | Store mixes persistence and pricing

- Evidence: `src/billing/store.py:10-140` `class Store:`
- Why it matters: a pricing change now risks the persistence tests.
- Fix: Extract a `PriceBook`.
- Verify: `rg -n 'class PriceBook' src/billing`
"""
UNCLE_BOB_BLOCK = """#### UB-2 | [SRP] Store does two jobs \u2014 `src/billing/store.py:10-140`

- Evidence: `src/billing/store.py:10` `class Store:`
- Fix: Extract a `PriceBook`.
- Verify: `rg -n 'class PriceBook' src/billing`
"""
TYPED = '- Evidence (convention): ruff.toml PLR0913 max-args=3; src/billing/io.py:12\n'


def merge_vader(*blocks: str, severity: str = 'Medium') -> str:
    first = """#### MV-1 | docs | README names a removed flag

- Evidence: `README.md:12` `--drain-fast`
- Fix: Replace `--drain-fast` with `--batch`.
- Verify: `rg -n -e '--drain-fast' README.md`
"""
    findings = '\n'.join([first, *blocks])
    return (
        f'# MERGE-VADER REPORT: a into b\n\n## Findings\n\n### {severity}\n\n{findings}\n## Clean\n'
    )


def uncle_bob(*blocks: str, severity: str = 'Medium') -> str:
    findings = '\n'.join(blocks)
    return f'# Uncle Bob Code Quality Report\n\n## Findings\n\n### {severity}\n\n{findings}\n'


@dataclass(frozen=True, slots=True, kw_only=True)
class Ingest:
    reviews: ReviewService
    database: Database
    run: RunId

    def report(self, persona: Persona) -> Path:
        directory = self.reviews.workspace.review_directory(None, self.run)
        return directory.joinpath(REPORT_FILES[persona])

    def write(self, persona: Persona, text: str) -> Path:
        path = self.report(persona)
        path.write_text(text, encoding='utf-8')
        return path

    def add(self, persona: Persona) -> str:
        return self.reviews.add(self.run, persona).text

    def attempt(self, persona: Persona) -> str:
        with pytest.raises(StateError) as error:
            self.add(persona)
        return str(error.value)

    def stored(self) -> list[Stored]:
        query = sql.select(ReviewFindingRow).order_by(ReviewFindingRow.finding_id)
        with self.database.transaction() as session:
            return [
                (
                    row.sources[0],
                    row.severity,
                    row.location,
                    row.kind,
                    row.security,
                    row.fix,
                    row.verify,
                    (row.evidence_kind, row.evidence_cite) if row.evidence_kind else None,
                )
                for row in session.scalars(query)
            ]


@pytest.fixture
def ingest(review_service: ReviewService, repository_database: Database) -> Ingest:
    view = review_service.start(START, started=datetime.now(tz=UTC))
    return Ingest(
        reviews=review_service, database=repository_database, run=RunId(view.run_id or '')
    )


def fixture_text(name: str) -> str:
    return FIXTURES.joinpath(name).read_text(encoding='utf-8')


class TestTheTemplatedReports:
    def test_a_merge_vader_report_is_ingested_field_for_field(self, ingest: Ingest) -> None:
        ingest.write(MERGE_VADER, fixture_text('merge-vader-report.md'))

        assert ingest.add(MERGE_VADER) == '5 findings in, 5 recorded: F1, F2, F3, F4, F5\n'
        assert ingest.stored() == MERGE_VADER_FINDINGS

    def test_an_uncle_bob_report_is_ingested_field_for_field(self, ingest: Ingest) -> None:
        ingest.write(UNCLE_BOB, fixture_text('uncle-bob-report.md'))

        assert ingest.add(UNCLE_BOB) == '4 findings in, 4 recorded: F1, F2, F3, F4\n'
        assert ingest.stored() == UNCLE_BOB_FINDINGS

    def test_an_uncle_bob_blocker_is_stored_as_high(self, ingest: Ingest) -> None:
        ingest.write(UNCLE_BOB, fixture_text('uncle-bob-report.md'))
        assert 'Blocker' in fixture_text('uncle-bob-report.md')

        ingest.add(UNCLE_BOB)

        assert next(severity for _, severity, *_ in ingest.stored()) == 'High'
        assert 'Blocker' not in {severity for _, severity, *_ in ingest.stored()}


class TestTheKindRule:
    @pytest.mark.parametrize(
        ('dimension', 'kind', 'security'),
        [
            pytest.param('quality', 'quality', False, id='quality'),
            pytest.param('security', 'defect', True, id='security'),
            pytest.param('sdlc', 'defect', False, id='sdlc'),
            pytest.param('docs', 'defect', False, id='docs'),
            pytest.param('plan', 'defect', False, id='plan'),
        ],
    )
    def test_merge_vader_dimensions_decide_the_kind_and_the_security_flag(
        self, ingest: Ingest, dimension: str, kind: str, security: bool
    ) -> None:
        block = MERGE_VADER_BLOCK.replace('| quality |', f'| {dimension} |')
        ingest.write(MERGE_VADER, merge_vader(block, severity='Low'))

        ingest.add(MERGE_VADER)

        assert ingest.stored()[1][3:5] == (kind, security)

    def test_every_uncle_bob_finding_is_quality(self, ingest: Ingest) -> None:
        ingest.write(UNCLE_BOB, fixture_text('uncle-bob-report.md'))

        ingest.add(UNCLE_BOB)

        assert {kind for _, _, _, kind, *_ in ingest.stored()} == {'quality'}

    def test_a_reviewer_cannot_label_a_quality_finding_a_defect_to_skip_the_evidence(
        self, ingest: Ingest
    ) -> None:
        block = MERGE_VADER_BLOCK + '- Kind: defect\n'
        ingest.write(MERGE_VADER, merge_vader(block))

        message = ingest.attempt(MERGE_VADER)

        assert 'needs structured evidence' in message
        assert '(MV-2)' in message


class TestRejectedReports:
    def test_a_quality_finding_at_medium_without_the_typed_bullet_rejects_the_whole_report(
        self, ingest: Ingest
    ) -> None:
        ingest.write(MERGE_VADER, merge_vader(MERGE_VADER_BLOCK))

        message = ingest.attempt(MERGE_VADER)

        assert (
            'finding 1: a quality finding at Medium or above needs structured evidence' in message
        )
        assert '(MV-2)' in message
        assert ingest.stored() == []

    def test_an_uncle_bob_finding_at_high_without_the_typed_bullet_is_rejected(
        self, ingest: Ingest
    ) -> None:
        ingest.write(UNCLE_BOB, uncle_bob(UNCLE_BOB_BLOCK, severity='High'))

        message = ingest.attempt(UNCLE_BOB)

        assert 'needs structured evidence' in message
        assert '(UB-2)' in message
        assert ingest.stored() == []

    def test_the_typed_bullet_lets_the_same_finding_through(self, ingest: Ingest) -> None:
        ingest.write(MERGE_VADER, merge_vader(MERGE_VADER_BLOCK + TYPED))

        ingest.add(MERGE_VADER)

        assert [evidence for *_, evidence in ingest.stored()][1] == (
            'convention',
            'ruff.toml PLR0913 max-args=3; src/billing/io.py:12',
        )

    @pytest.mark.parametrize(
        ('removed', 'missing'),
        [
            pytest.param(
                '- Evidence: `src/billing/store.py:10-140` `class Store:`\n',
                'location',
                id='location',
            ),
            pytest.param('- Fix: Extract a `PriceBook`.\n', 'fix', id='fix'),
            pytest.param(
                "- Verify: `rg -n 'class PriceBook' src/billing`\n", 'verify', id='verify'
            ),
        ],
    )
    def test_a_merge_vader_block_missing_a_field_rejects_the_whole_report(
        self, ingest: Ingest, removed: str, missing: str
    ) -> None:
        block = (MERGE_VADER_BLOCK + TYPED).replace(removed, '')
        ingest.write(MERGE_VADER, merge_vader(block))

        assert f'finding 1: {missing} is required (MV-2)' in ingest.attempt(MERGE_VADER)
        assert ingest.stored() == []

    @pytest.mark.parametrize(
        ('removed', 'missing'),
        [
            pytest.param(' \u2014 `src/billing/store.py:10-140`', 'location', id='location'),
            pytest.param('- Fix: Extract a `PriceBook`.\n', 'fix', id='fix'),
            pytest.param(
                "- Verify: `rg -n 'class PriceBook' src/billing`\n", 'verify', id='verify'
            ),
        ],
    )
    def test_an_uncle_bob_block_missing_a_field_rejects_the_whole_report(
        self, ingest: Ingest, removed: str, missing: str
    ) -> None:
        good = (UNCLE_BOB_BLOCK + TYPED).replace('UB-2', 'UB-1')
        broken = (UNCLE_BOB_BLOCK + TYPED).replace(removed, '').replace('UB-2', 'UB-3')
        ingest.write(UNCLE_BOB, uncle_bob(good, broken))

        assert f'finding 1: {missing} is required (UB-3)' in ingest.attempt(UNCLE_BOB)
        assert ingest.stored() == []

    @pytest.mark.parametrize(
        ('text', 'problem'),
        [
            pytest.param(
                '# Report\n\n## Summary\n\nnothing\n', 'no "## Findings" section', id='no-section'
            ),
            pytest.param(
                '## Findings\n\n### Serious\n\n' + MERGE_VADER_BLOCK,
                "'### Serious' is not a severity heading",
                id='severity',
            ),
            pytest.param(
                '## Findings\n\n' + MERGE_VADER_BLOCK,
                'comes before any severity heading',
                id='unplaced',
            ),
            pytest.param(
                '## Findings\n\n### Low\n\n#### MV-1 title only\n',
                'is not a finding heading',
                id='heading',
            ),
            pytest.param(
                merge_vader(MERGE_VADER_BLOCK.replace('| quality |', '| style |')),
                "dimension 'style' is not security, sdlc, quality, docs or plan",
                id='dimension',
            ),
            pytest.param(
                merge_vader(MERGE_VADER_BLOCK.replace('MV-2', 'UB-2')),
                'a merge-vader report holds only its own finding ids',
                id='foreign',
            ),
            pytest.param(
                merge_vader(MERGE_VADER_BLOCK + '- Evidence (vibes): trust me\n'),
                "evidence kind 'vibes' is not metric, idiom or convention",
                id='evidence-kind',
            ),
            pytest.param(
                merge_vader(
                    MERGE_VADER_BLOCK.replace('src/billing/store.py:10-140', 'nowhere') + TYPED
                ),
                'location must be path:line or path:start-end',
                id='location-shape',
            ),
        ],
    )
    def test_a_report_that_does_not_fit_the_template_stores_nothing(
        self, ingest: Ingest, text: str, problem: str
    ) -> None:
        ingest.write(MERGE_VADER, text)

        assert problem in ingest.attempt(MERGE_VADER)
        assert ingest.stored() == []


class TestWhereTheReportComesFrom:
    def test_add_reads_the_named_personas_report_from_the_run_directory(
        self, ingest: Ingest
    ) -> None:
        ingest.write(UNCLE_BOB, fixture_text('uncle-bob-report.md'))

        message = ingest.attempt(MERGE_VADER)

        assert message == (
            f'no merge-vader report at .mightymodels/.runtime/reviews/{ingest.run}/'
            'MERGE-VADER-REPORT.md; the reviewer writes it there first'
        )

    def test_a_report_that_is_a_symlink_is_not_read(self, ingest: Ingest, tmp_path: Path) -> None:
        outside = tmp_path.joinpath('elsewhere.md')
        outside.write_text(fixture_text('merge-vader-report.md'), encoding='utf-8')
        ingest.report(MERGE_VADER).symlink_to(outside)

        assert 'no merge-vader report at' in ingest.attempt(MERGE_VADER)
        assert ingest.stored() == []

    def test_secrets_in_a_report_are_redacted_before_they_are_stored(self, ingest: Ingest) -> None:
        block = MERGE_VADER_BLOCK.replace('| quality |', '| security |').replace(
            'Store mixes persistence and pricing', 'Hardcoded password=hunter22 in the store'
        )
        ingest.write(MERGE_VADER, merge_vader(block, severity='High'))

        ingest.add(MERGE_VADER)

        with ingest.database.transaction() as session:
            titles = [row.title for row in session.scalars(sql.select(ReviewFindingRow))]
        assert 'hunter22' not in ' '.join(titles)
        assert 'Hardcoded [REDACTED:assignment] in the store' in titles

    def test_a_second_personas_report_adds_to_the_findings_already_recorded(
        self, ingest: Ingest
    ) -> None:
        ingest.write(MERGE_VADER, merge_vader(severity='Low'))
        ingest.write(UNCLE_BOB, fixture_text('uncle-bob-report.md'))

        ingest.add(MERGE_VADER)

        assert ingest.add(UNCLE_BOB).startswith('4 findings in')
        assert len(ingest.stored()) == 5


class TestAReportThatMergesIntoADecidedFinding:
    DEFERRED = DisposePayload.model_validate(
        {'by': 'user', 'decisions': {'F2': {'decision': 'defer', 'reason': 'ticketed as PLAT-9'}}}
    )

    @pytest.fixture
    def deferred(self, ingest: Ingest) -> None:
        ingest.write(MERGE_VADER, merge_vader(MERGE_VADER_BLOCK + TYPED))
        ingest.write(UNCLE_BOB, uncle_bob(UNCLE_BOB_BLOCK + TYPED, severity='High'))
        ingest.add(MERGE_VADER)
        ingest.reviews.dispose(ingest.run, self.DEFERRED)

    @pytest.mark.usefixtures('deferred')
    def test_a_second_personas_report_that_raises_a_decided_finding_puts_it_back_to_undecided(
        self, ingest: Ingest
    ) -> None:
        assert ingest.add(UNCLE_BOB) == '1 findings in, 1 recorded: F2; back to undecided: F2\n'
        assert ingest.reviews.gate(ingest.run).text.splitlines()[0].endswith('\tundecided')

    @pytest.mark.usefixtures('deferred')
    def test_the_same_report_added_again_keeps_the_decision(self, ingest: Ingest) -> None:
        assert ingest.add(MERGE_VADER) == '2 findings in, 2 recorded: F1, F2\n'
        assert ingest.reviews.gate(ingest.run).text.splitlines()[1].endswith('\tdefer')

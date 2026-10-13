"""The writes that store a text for similarity, one for each domain that stores one.

A similarity test writes through the four services, on SQLite or on the stores kept in memory, so
the services are bundled as `Services` and each write takes the bundle. A write answers the text
its service answered, which names a near-duplicate when the text resembles an earlier one.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from mightymodels.core.run_id import RunId
from mightymodels.core.slug import Slug
from mightymodels.tools.crashout.schema import CrashoutEntry, Severity, Verdict
from mightymodels.tools.crashout.service import CrashoutService
from mightymodels.tools.investigation.schema import (
    EntryKind,
    InvestigationStart,
    LedgerEntry,
    Source,
    TargetKind,
)
from mightymodels.tools.investigation.service import InvestigationService
from mightymodels.tools.review.schema import FindingInput, ReportedSeverity
from mightymodels.tools.review.service import ReviewService
from mightymodels.tools.similarity.schema import Scout, SimilarityKind, SpooledReport
from mightymodels.tools.similarity.service import SimilarityService

type Write = Callable[['Services', str, int], str]

STARTED = datetime(2026, 9, 28, 12, tzinfo=UTC)
RUN = RunId('20260928-120000')
THE_DRAIN_LOOP = 'the drain loop sleeps between every retry batch'
THE_DRAIN_LOOP_REWORDED = 'drain loop sleeps between every retry batches'
SHARES_ONE_WORD = 'drain the queue before shutdown completes'
ONLY_COMMON_WORDS = 'it was the and that they would have about this'


@dataclass(slots=True, kw_only=True, frozen=True)
class Services:
    investigations: InvestigationService
    reviews: ReviewService
    crashouts: CrashoutService
    similarity: SimilarityService


def started_investigation(services: Services) -> Slug:
    target = InvestigationStart(target='cache invalidation', kind=TargetKind.BEHAVIOR)
    started = services.investigations.start(target, started=STARTED)
    assert started.investigation_id is not None
    return Slug(started.investigation_id)


def ledger_entry(text: str) -> LedgerEntry:
    return LedgerEntry(kind=EntryKind.OPEN, text=text, source=Source.USER)


def write_ledger_entry(services: Services, text: str, _number: int) -> str:
    investigation = started_investigation(services)
    return services.investigations.add(investigation, 1, [ledger_entry(text)]).text


def write_review_finding(services: Services, text: str, number: int) -> str:
    finding = FindingInput(
        sources=('MV-1',),
        severity=ReportedSeverity.HIGH,
        title=text,
        location=f'src/file{number}.py:1',
        fix='fix it',
        verify='run the tests',
    )
    return services.reviews.add_findings(RUN, [finding]).text


def write_crashout(services: Services, text: str, _number: int) -> str:
    entry = CrashoutEntry(
        severity=Severity.HEATED,
        verdict=Verdict.DESERVED,
        rant='why did you do that',
        failures=('did it',),
        root_cause=text,
        corrective_action='stop doing that',
        barked_back=False,
    )
    return services.crashouts.add(entry).text


WRITES = (
    pytest.param(write_ledger_entry, SimilarityKind.LEDGER_ENTRY, id='ledger-entry'),
    pytest.param(write_review_finding, SimilarityKind.REVIEW_FINDING, id='review-finding'),
    pytest.param(write_crashout, SimilarityKind.CRASHOUT, id='crashout'),
)


EACH_WRITE = (
    pytest.param(write_ledger_entry, id='ledger-entry'),
    pytest.param(write_review_finding, id='review-finding'),
    pytest.param(write_crashout, id='crashout'),
)


def store_scout_report(similarity: SimilarityService, text: str) -> list[str]:
    report = SpooledReport(
        repository_key=similarity.repository_key,
        scout=Scout.CODE_SCOUT,
        target='the drain loop',
        report=text,
    )
    with similarity.store.transaction() as repository:
        return [duplicate.earlier.reference for duplicate in repository.add_scout_report(report)]


def references_found(similarity: SimilarityService, query: str) -> list[str]:
    return [match.reference for match in similarity.search(query, None).matches]

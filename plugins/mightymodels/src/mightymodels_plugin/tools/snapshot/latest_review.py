"""The latest review run of a ticket: its findings and where each one stands.

A snapshot shows it and a closing is blocked by it, so both read it here. Findings are held in
number order and every list below keeps that order.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from mightymodels_plugin.core.slug import Slug
from mightymodels_plugin.tools.review.rendering import Standing
from mightymodels_plugin.tools.review.repository import ReviewRepository
from mightymodels_plugin.tools.review.schema import Decision, Disposition, Finding, Result
from mightymodels_plugin.tools.review.service import findings_of, run_of, standing_of


@dataclass(slots=True, kw_only=True, frozen=True)
class LatestReview:
    findings: Mapping[str, Finding]
    standing: Standing

    def decided(self) -> dict[str, Disposition]:
        dispositions = self.standing.dispositions
        return {
            finding_id: dispositions[finding_id]
            for finding_id in self.findings
            if finding_id in dispositions
        }

    def undecided(self) -> list[str]:
        dispositions = self.standing.dispositions
        return [finding_id for finding_id in self.findings if finding_id not in dispositions]

    def is_fixed(self, finding_id: str) -> bool:
        return self.standing.results.get(finding_id) is Result.FIXED

    def open_remediation(self) -> list[str]:
        return [
            finding_id
            for finding_id, disposition in self.decided().items()
            if disposition.decision is Decision.FIX and not self.is_fixed(finding_id)
        ]


def latest_review_of(reviews: ReviewRepository, slug: Slug) -> LatestReview | None:
    row = reviews.latest_run_row(slug)
    if row is None:
        return None
    run = run_of(row)
    return LatestReview(
        findings=findings_of(reviews, run.run_id), standing=standing_of(reviews, run)
    )

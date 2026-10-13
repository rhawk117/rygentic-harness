"""The texts of the similarity tool: what a write says about a near-duplicate, and a search result.

A match is shown with the start of the earlier row's text, on one line, so the caller can judge
it without reading the row.
"""

from collections.abc import Sequence

from mightymodels_plugin.tools.similarity.schema import Duplicate, Match

EXCERPT_LENGTH = 120
NO_MATCHES = 'no similar rows\n'


def excerpt(text: str) -> str:
    one_line = ' '.join(text.split())
    return one_line if len(one_line) <= EXCERPT_LENGTH else f'{one_line[:EXCERPT_LENGTH]}...'


def match_line(match: Match) -> str:
    return f'{match.kind} {match.reference} (overlap {match.overlap:.2f}): {excerpt(match.text)}\n'


def duplicates_text(duplicates: Sequence[Duplicate]) -> str:
    return ''.join(
        f'near-duplicate: {duplicate.written} resembles {match_line(duplicate.earlier)}'
        for duplicate in duplicates
    )


def matches_text(matches: Sequence[Match]) -> str:
    return ''.join(map(match_line, matches)) or NO_MATCHES

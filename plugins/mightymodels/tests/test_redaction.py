"""Redaction of free text: the `assignment` pattern keeps its meaning and long tokens stay cheap."""

import re
import time

import pytest
from hypothesis import given
from hypothesis import strategies as st
from mightymodels_plugin.redaction import SECRET_PATTERNS, redact

LONG_TEXT = 60_000
SECONDS_FOR_LONG_TEXT = 5.0
PATTERN_AT_THE_FIRST_RELEASE = re.compile(
    r'(?i)[A-Z0-9_]*(?:password|passwd|secret|token|api[_-]?key)[A-Z0-9_]*'
    r'["\']?\s*[:=]\s*["\']?[^\s,;"\']+'
)
FRAGMENTS = (
    'password',
    'passwd',
    'secret',
    'token',
    'api',
    'key',
    'apikey',
    'api_key',
    'api-key',
    '-',
    '_',
    '=',
    ':',
    ' ',
    '\n',
    ',',
    '"',
    "'",
    'x',
    '7',
    'ſ',
    'K',
)
TEXTS = st.lists(st.sampled_from(FRAGMENTS), max_size=14).map(''.join)


def long_tokens() -> list[str]:
    return [
        'x' * LONG_TEXT,
        '7_' * (LONG_TEXT // 2),
        'token' * (LONG_TEXT // 5),
        'tokenapi-key' * (LONG_TEXT // 12),
        'token=' * (LONG_TEXT // 6),
        'token' + ' ' * LONG_TEXT,
    ]


class TestTheAssignmentPattern:
    @given(text=TEXTS)
    def test_redacts_generated_text_exactly_as_the_pattern_at_the_first_release_did(
        self, text: str
    ) -> None:
        current = SECRET_PATTERNS['assignment']

        assert current.sub('[R]', text) == PATTERN_AT_THE_FIRST_RELEASE.sub('[R]', text)
        assert [m.span() for m in current.finditer(text)] == [
            m.span() for m in PATTERN_AT_THE_FIRST_RELEASE.finditer(text)
        ]

    @pytest.mark.parametrize('token', long_tokens(), ids=lambda token: token[:12].strip())
    def test_redacts_sixty_thousand_characters_of_one_token_within_seconds(
        self, token: str
    ) -> None:
        started = time.perf_counter()
        redact(token)

        assert time.perf_counter() - started < SECONDS_FOR_LONG_TEXT

    def test_still_redacts_a_prefixed_assignment(self) -> None:
        assert redact('export MY_DB_PASSWORD="hunter2" now') == (
            'export [REDACTED:assignment]" now'
        )

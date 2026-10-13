"""Secret redaction applied to every free-text field before it is stored.

A marker can be longer than the secret it replaces, so text a request accepted at the length of
its column can leave redaction over it. `redact_within` and `redaction_within` redact text on its
way to a column and refuse it when the redacted text is over the limit the caller names. The text
is never cut to fit and the secret is never kept.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mightymodels.core.errors import StateError

SECRET_PATTERNS: Mapping[str, re.Pattern[str]] = MappingProxyType(
    {
        'private-key': re.compile(
            r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
            re.DOTALL,
        ),
        'aws-key': re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'),
        'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_\w{20,})'),
        'slack-token': re.compile(r'\bxox[abposr]-[A-Za-z0-9-]{10,}'),
        'stripe-key': re.compile(r'\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b'),
        'api-key': re.compile(r'\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}'),
        'jwt': re.compile(r'\beyJ[\w-]+\.[\w-]+\.[\w-]+'),
        'bearer': re.compile(r'\bBearer [A-Za-z0-9._~+/-]{12,}=*'),
        'url-credentials': re.compile(r'(?<=://)[^/\s:@]+:[^@\s]+(?=@)'),
        'assignment': re.compile(
            r'(?i)(?<![A-Z0-9_])'
            r'(?:(?>[A-Z0-9_]*?(?:password|passwd|secret|token|api_?key))[A-Z0-9_]*+'
            r'|[A-Z0-9_]*+(?<=api)-key[A-Z0-9_]*+)'
            r'["\']?\s*[:=]\s*["\']?[^\s,;"\']+'
        ),
    }
)


class RedactedTextTooLongError(StateError):
    def __init__(self, field: str, *, limit: int, length: int) -> None:
        super().__init__(
            f'{field}: {length} characters once its secrets are redacted, and at most {limit} '
            'are stored; shorten the text; nothing was written'
        )
        self.field = field
        self.limit = limit
        self.length = length


@dataclass(slots=True, kw_only=True, frozen=True)
class Redaction:
    text: str
    hits: int

    def length_error(self, field: str, limit: int) -> RedactedTextTooLongError | None:
        if len(self.text) <= limit:
            return None
        return RedactedTextTooLongError(field, limit=limit, length=len(self.text))


def redaction_of(text: str) -> Redaction:
    hits = 0
    for name, pattern in SECRET_PATTERNS.items():
        text, replaced = pattern.subn(f'[REDACTED:{name}]', text)
        hits += replaced
    return Redaction(text=text, hits=hits)


def redact(text: str) -> str:
    return redaction_of(text).text


def redaction_within(text: str, field: str, limit: int) -> Redaction:
    redaction = redaction_of(text)
    if (error := redaction.length_error(field, limit)) is not None:
        raise error
    return redaction


def redact_within(text: str, field: str, limit: int) -> str:
    return redaction_within(text, field, limit).text

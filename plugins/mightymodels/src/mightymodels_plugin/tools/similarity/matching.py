"""What makes a text a near-duplicate of another: the words it is reduced to and how far they meet.

A text is reduced to its content words: the lowercased runs of letters and digits in it, less the
`COMMON_WORDS` and the markers redaction leaves. FTS5's `unicode61` tokenizer splits text at the
same boundaries, so a content word is a term of the index.

The match is two steps. BM25 ranks the stored rows that share a content word with the text, and
the best `CANDIDATE_CAP` of them are read. BM25 scores are relative to the rows an index holds, so
no score can say that two texts are alike. `overlap` does: the share of the words of both texts
that are in each. A candidate whose overlap reaches `MATCH_OVERLAP` is a match, and a text with no
content word has no candidate at all.

A query is built from content words alone, each in double quotes and joined by `OR`. A content
word holds no character FTS5 gives a meaning to, so what a caller wrote cannot add an operator,
name a column or break the query's syntax.
"""

import re
from collections.abc import Iterable

CANDIDATE_CAP = 20
MATCH_OVERLAP = 0.6
WORDS = re.compile(r'[^\W_]+')
REDACTION_MARKER = re.compile(r'\[REDACTED:[\w-]+\]')
COMMON_TEXT = """
a about after all also am an and any are as at be because been before but by can could did do does
for from had has have he her his how i if in into is it its just me more my no not of on or our out
over she so some such than that the their them then there these they this those to too up us was we
were what when where which while who why will with would you your
"""
COMMON_WORDS = frozenset(COMMON_TEXT.split())


def content_words(text: str) -> frozenset[str]:
    words = WORDS.finditer(REDACTION_MARKER.sub(' ', text).lower())
    return frozenset(word[0] for word in words if word[0] not in COMMON_WORDS)


def overlap(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def index_query(words: Iterable[str]) -> str:
    return ' OR '.join(f'"{word}"' for word in sorted(words))

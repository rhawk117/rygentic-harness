import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from operator import attrgetter
from typing import Protocol, runtime_checkable

DEFAULT_THRESHOLD = 0.25
PAIR = 2
TOKEN_PATTERN = re.compile(r'(?u)\b\w\w+\b')
STOPWORDS = frozenset({
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'by', 'for', 'if', 'in', 'into', 'is', 'it',
    'no', 'not', 'of', 'on', 'or', 'such', 'that', 'the', 'their', 'then', 'there', 'these',
    'they', 'this', 'to', 'was', 'will', 'with',
})  # fmt: skip


def tokenize(text: str) -> tuple[str, ...]:
    words = [match.group() for match in TOKEN_PATTERN.finditer(text.lower())]
    return tuple(word for word in words if word not in STOPWORDS)


@dataclass(slots=True, kw_only=True, frozen=True)
class Collision:
    first: str
    second: str
    overlap: float
    shared_terms: tuple[str, ...]

    def describe(self) -> str:
        terms = ', '.join(self.shared_terms)
        return f'{self.first} <-> {self.second}: overlap {self.overlap:.2f} ({terms})'

    def involves(self, skill: str) -> bool:
        return skill in {self.first, self.second}


@runtime_checkable
class CollisionDetector(Protocol):
    def find(self, descriptions: Mapping[str, str]) -> list[Collision]: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class Bm25Options:
    k1: float = 1.5
    b: float = 0.75


@dataclass(slots=True, kw_only=True, frozen=True)
class Bm25Index:
    documents: tuple[Counter[str], ...]
    options: Bm25Options = field(default_factory=Bm25Options)

    @property
    def average_length(self) -> float:
        total = sum(document.total() for document in self.documents)
        return total / len(self.documents)

    def document_frequency(self, term: str) -> int:
        return sum(1 for document in self.documents if term in document)

    def idf(self, term: str) -> float:
        count = len(self.documents)
        frequency = self.document_frequency(term)
        return math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))

    def term_score(self, term: str, document: Counter[str]) -> float:
        frequency = document[term]
        if not frequency:
            return 0.0
        relative_length = document.total() / self.average_length
        damping = self.options.k1 * (1 - self.options.b + self.options.b * relative_length)
        return self.idf(term) * frequency * (self.options.k1 + 1) / (frequency + damping)

    def score(self, query: Sequence[str], position: int) -> float:
        document = self.documents[position]
        return sum(self.term_score(term, document) for term in query)


def build_index(texts: Sequence[tuple[str, ...]]) -> Bm25Index:
    return Bm25Index(documents=tuple(Counter(tokens) for tokens in texts))


@dataclass(slots=True, kw_only=True, frozen=True)
class OverlapMatrix:
    names: tuple[str, ...]
    tokens: tuple[tuple[str, ...], ...]
    index: Bm25Index

    def normalized(self, row: int, column: int) -> float:
        query = self.tokens[row]
        self_score = self.index.score(query, row)
        if not self_score:
            return 0.0
        return self.index.score(query, column) / self_score

    def collision(self, row: int, column: int) -> Collision:
        overlap = max(self.normalized(row, column), self.normalized(column, row))
        shared = sorted(set(self.tokens[row]) & set(self.tokens[column]))
        return Collision(
            first=self.names[row],
            second=self.names[column],
            overlap=overlap,
            shared_terms=tuple(shared),
        )


def build_overlap_matrix(descriptions: Mapping[str, str]) -> OverlapMatrix:
    names = tuple(sorted(descriptions))
    tokens = tuple(tokenize(descriptions[name]) for name in names)
    return OverlapMatrix(names=names, tokens=tokens, index=build_index(tokens))


@dataclass(slots=True, kw_only=True, frozen=True)
class Bm25CollisionDetector:
    threshold: float = DEFAULT_THRESHOLD

    def find(self, descriptions: Mapping[str, str]) -> list[Collision]:
        if len(descriptions) < PAIR:
            return []
        matrix = build_overlap_matrix(descriptions)
        pairs = combinations(range(len(matrix.names)), PAIR)
        found = [matrix.collision(row, column) for row, column in pairs]
        ranked = sorted(found, key=attrgetter('overlap'), reverse=True)
        return [collision for collision in ranked if collision.overlap >= self.threshold]

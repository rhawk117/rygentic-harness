import math
from collections.abc import Mapping

import pytest
from hypothesis import given
from hypothesis import strategies as st
from vibe_code_cli.tune.collisions import Bm25CollisionDetector, build_overlap_matrix, tokenize


class TestTokenize:
    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            pytest.param('Alpha BETA', ('alpha', 'beta'), id='lowercases'),
            pytest.param(
                'the quick fox and a lazy dog',
                ('quick', 'fox', 'lazy', 'dog'),
                id='drops_stopwords',
            ),
            pytest.param('x y ab cd', ('ab', 'cd'), id='drops_single_character_tokens'),
        ],
    )
    def test_tokenize_normalizes_text(self, text: str, expected: tuple[str, ...]) -> None:
        assert tokenize(text) == expected


class TestHandComputedOverlap:
    document_count = 2
    k1 = 1.5
    b = 0.75
    descriptions: Mapping[str, str] = {'a': 'foo bar', 'b': 'foo baz'}

    def idf(self, document_frequency: int) -> float:
        count = self.document_count
        return math.log(1 + (count - document_frequency + 0.5) / (document_frequency + 0.5))

    def term_score(
        self, term_frequency: int, document_frequency: int, relative_length: float
    ) -> float:
        damping = self.k1 * (1 - self.b + self.b * relative_length)
        numerator = self.idf(document_frequency) * term_frequency * (self.k1 + 1)
        return numerator / (term_frequency + damping)

    def test_overlap_matches_a_hand_computed_bm25_score(self) -> None:
        matrix = build_overlap_matrix(self.descriptions)
        score_a_on_a = self.term_score(1, 2, 1.0) + self.term_score(1, 1, 1.0)
        score_a_on_b = self.term_score(1, 2, 1.0)
        expected_overlap = score_a_on_b / score_a_on_a

        collision = matrix.collision(0, 1)

        assert collision.first == 'a'
        assert collision.second == 'b'
        assert collision.shared_terms == ('foo',)
        assert collision.overlap == pytest.approx(expected_overlap)


class TestThresholdFiltering:
    descriptions: Mapping[str, str] = {'a': 'foo bar', 'b': 'foo baz', 'c': 'qux quux'}

    @pytest.mark.parametrize(
        ('threshold', 'expected_count'),
        [
            pytest.param(0.4, 0, id='above_every_overlap'),
            pytest.param(0.3, 1, id='keeps_only_the_shared_pair'),
            pytest.param(0.0, 3, id='keeps_every_pair'),
        ],
    )
    def test_threshold_filters_the_found_collisions(
        self, threshold: float, expected_count: int
    ) -> None:
        collisions = Bm25CollisionDetector(threshold=threshold).find(self.descriptions)
        assert len(collisions) == expected_count


class TestCollisionLaws:
    words = ('alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta')
    names = st.from_regex(r'[a-z]{2,6}', fullmatch=True)
    phrases = st.lists(st.sampled_from(words), min_size=1, max_size=4, unique=True).map(' '.join)
    libraries = st.dictionaries(names, phrases, max_size=5)
    distinct_name_pairs = st.lists(names, min_size=2, max_size=2, unique=True)

    @given(descriptions=libraries)
    def test_overlap_is_never_negative(self, descriptions: dict[str, str]) -> None:
        collisions = Bm25CollisionDetector(threshold=0.0).find(descriptions)
        assert all(collision.overlap >= 0.0 for collision in collisions)

    @given(descriptions=libraries)
    def test_collisions_are_sorted_by_overlap_descending(
        self, descriptions: dict[str, str]
    ) -> None:
        collisions = Bm25CollisionDetector(threshold=0.0).find(descriptions)
        overlaps = [collision.overlap for collision in collisions]
        assert overlaps == sorted(overlaps, reverse=True)

    @given(descriptions=st.dictionaries(names, phrases, max_size=1))
    def test_fewer_than_two_skills_has_no_collisions(self, descriptions: dict[str, str]) -> None:
        assert Bm25CollisionDetector().find(descriptions) == []

    @given(pair=distinct_name_pairs, phrase=phrases)
    def test_identical_descriptions_have_overlap_one(self, pair: list[str], phrase: str) -> None:
        first, second = pair
        collisions = Bm25CollisionDetector(threshold=0.0).find({first: phrase, second: phrase})
        assert [collision.overlap for collision in collisions] == [1.0]

    def test_disjoint_vocabularies_have_overlap_zero(self) -> None:
        descriptions = {'a': 'alpha beta', 'b': 'gamma delta'}
        collisions = Bm25CollisionDetector(threshold=0.0).find(descriptions)
        assert [collision.overlap for collision in collisions] == [0.0]

    def test_stopword_only_description_overlaps_nothing_without_dividing_by_zero(self) -> None:
        descriptions = {'empty': 'the a an', 'other': 'alpha beta'}
        collisions = Bm25CollisionDetector(threshold=0.0).find(descriptions)
        assert [collision.overlap for collision in collisions] == [0.0]

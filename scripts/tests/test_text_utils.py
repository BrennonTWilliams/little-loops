"""Tests for text_utils module."""

from __future__ import annotations

from little_loops.text_utils import calculate_word_overlap, extract_words


class TestExtractWords:
    """Tests for extract_words function."""

    def test_basic_extraction(self) -> None:
        """Extracts 3+ char lowercase words."""
        words = extract_words("The quick brown fox jumps over the lazy dog")
        assert "quick" in words
        assert "brown" in words
        assert "jumps" in words
        assert "lazy" in words
        # 2-char words excluded
        assert "the" not in words

    def test_filters_common_words(self) -> None:
        """Common stop words are excluded."""
        words = extract_words("This is a test file with code and issues")
        assert "test" in words
        # Common words filtered
        assert "this" not in words
        assert "file" not in words
        assert "code" not in words
        assert "issue" not in words

    def test_empty_input(self) -> None:
        """Empty string returns empty set."""
        assert extract_words("") == set()

    def test_case_insensitive(self) -> None:
        """Words are lowercased."""
        words = extract_words("Python JAVASCRIPT TypeScript")
        assert "python" in words
        assert "javascript" in words
        assert "typescript" in words


class TestCalculateWordOverlap:
    """Tests for calculate_word_overlap function."""

    def test_identical_sets(self) -> None:
        """Identical sets have overlap of 1.0."""
        words = {"python", "javascript", "typescript"}
        assert calculate_word_overlap(words, words) == 1.0

    def test_disjoint_sets(self) -> None:
        """Disjoint sets have overlap of 0.0."""
        words1 = {"python", "javascript"}
        words2 = {"rust", "golang"}
        assert calculate_word_overlap(words1, words2) == 0.0

    def test_partial_overlap(self) -> None:
        """Partial overlap gives correct Jaccard score."""
        words1 = {"aaa", "bbb"}
        words2 = {"bbb", "ccc"}
        # intersection: {bbb}, union: {aaa, bbb, ccc}
        assert calculate_word_overlap(words1, words2) == 1.0 / 3.0

    def test_empty_sets(self) -> None:
        """Empty sets return 0.0."""
        assert calculate_word_overlap(set(), {"word"}) == 0.0
        assert calculate_word_overlap({"word"}, set()) == 0.0
        assert calculate_word_overlap(set(), set()) == 0.0

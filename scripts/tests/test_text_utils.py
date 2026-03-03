"""Tests for text_utils module."""

from __future__ import annotations

from little_loops.text_utils import calculate_word_overlap, extract_words, score_bm25


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


class TestScoreBM25:
    """Tests for score_bm25 function."""

    def _make_corpus(self, docs: list[set[str]]) -> dict:
        """Build corpus stats from a list of word sets."""
        doc_freq: dict[str, int] = {}
        for words in docs:
            for word in words:
                doc_freq[word] = doc_freq.get(word, 0) + 1
        total_len = sum(len(d) for d in docs)
        return {
            "doc_freq": doc_freq,
            "avg_doc_len": total_len / len(docs) if docs else 0.0,
            "total_docs": len(docs),
        }

    def test_matching_terms_produce_positive_score(self) -> None:
        """Document containing query terms scores above zero."""
        docs = [{"python", "testing"}, {"java", "testing"}, {"rust", "bench"}]
        corpus = self._make_corpus(docs)
        score = score_bm25({"python"}, {"python", "testing"}, **corpus)
        assert score > 0.0

    def test_no_matching_terms_returns_zero(self) -> None:
        """Document without query terms scores 0."""
        docs = [{"python"}, {"java"}]
        corpus = self._make_corpus(docs)
        score = score_bm25({"rust"}, {"python", "java"}, **corpus)
        assert score == 0.0

    def test_empty_query_returns_zero(self) -> None:
        """Empty query returns 0."""
        docs = [{"python"}]
        corpus = self._make_corpus(docs)
        assert score_bm25(set(), {"python"}, **corpus) == 0.0

    def test_empty_doc_returns_zero(self) -> None:
        """Empty document returns 0."""
        docs = [{"python"}]
        corpus = self._make_corpus(docs)
        assert score_bm25({"python"}, set(), **corpus) == 0.0

    def test_zero_total_docs_returns_zero(self) -> None:
        """Zero total_docs returns 0."""
        assert score_bm25({"python"}, {"python"}, doc_freq={}, avg_doc_len=0.0, total_docs=0) == 0.0

    def test_rare_term_scores_higher_than_common_term(self) -> None:
        """Rare terms (low doc frequency) yield higher IDF and thus higher BM25."""
        # 10 docs total; "rare" appears in 1, "common" appears in 9
        docs = [{"rare"}] + [{"common"}] * 9
        corpus = self._make_corpus(docs)
        score_rare = score_bm25({"rare"}, {"rare"}, **corpus)
        score_common = score_bm25({"common"}, {"common"}, **corpus)
        assert score_rare > score_common

    def test_shorter_doc_scores_higher_for_same_match(self) -> None:
        """Shorter documents rank higher than longer ones for the same match (b>0)."""
        # Two docs both contain "python"; one is shorter
        docs = [{"python"}, {"python", "aaa", "bbb", "ccc", "ddd", "eee"}]
        corpus = self._make_corpus(docs)
        score_short = score_bm25({"python"}, {"python"}, **corpus)
        score_long = score_bm25({"python"}, {"python", "aaa", "bbb", "ccc", "ddd", "eee"}, **corpus)
        assert score_short > score_long

"""Tests for text_utils module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from little_loops.text_utils import (
    RefIndex,
    build_ref_index,
    calculate_word_overlap,
    classify_file_ref,
    classify_issue_refs,
    extract_words,
    score_bm25,
)


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


# =============================================================================
# File Reference Classification (ENH-2983)
# =============================================================================


class TestClassifyFileRef:
    """Tests for classify_file_ref() against a pre-built RefIndex."""

    def test_resolved_for_unrooted_partial_path(self) -> None:
        """A partial path uniquely suffix-matching a tracked file resolves."""
        index = RefIndex(
            by_basename={"executor.py": ["scripts/little_loops/fsm/executor.py"]}
        )
        assert classify_file_ref("fsm/executor.py", index) == "resolved"

    def test_unresolvable_form_bare_basename(self) -> None:
        """A bare basename with no `/` is a prose mention, not a location."""
        index = RefIndex(by_basename={"config-schema.json": ["scripts/config-schema.json"]})
        assert classify_file_ref("config-schema.json", index) == "unresolvable_form"

    def test_unresolvable_form_glob(self) -> None:
        """A glob pattern is unresolvable_form."""
        index = RefIndex(by_basename={})
        assert classify_file_ref("skills/*/SKILL.md", index) == "unresolvable_form"

    def test_unresolvable_form_placeholder(self) -> None:
        """A path containing a <placeholder> segment is unresolvable_form."""
        index = RefIndex(by_basename={})
        assert (
            classify_file_ref("~/.codex/skills/<name>/SKILL.md", index)
            == "unresolvable_form"
        )

    def test_stale_for_qualified_path_no_suffix_match(self) -> None:
        """A /-qualified path with no suffix match is genuine drift: stale."""
        index = RefIndex(by_basename={})
        assert (
            classify_file_ref("scripts/little_loops/session_store.py", index) == "stale"
        )

    def test_planned_new_from_line_context(self) -> None:
        """A path on a line marked (new) is planned_new, even if unresolved."""
        index = RefIndex(by_basename={})
        line = "- `scripts/little_loops/new_thing.py` (new)"
        assert (
            classify_file_ref("scripts/little_loops/new_thing.py", index, line=line)
            == "planned_new"
        )

    def test_ambiguous_suffix_match_does_not_resolve(self) -> None:
        """Two tracked files ending in /utils.py must not silently resolve."""
        index = RefIndex(
            by_basename={
                "utils.py": [
                    "scripts/little_loops/pkg1/dir/utils.py",
                    "scripts/little_loops/pkg2/dir/utils.py",
                ]
            }
        )
        result = classify_file_ref("dir/utils.py", index)
        assert result != "resolved"

    def test_bare_skill_md_is_not_suffix_matched(self) -> None:
        """Ordering guard: a bare SKILL.md must not suffix-match tracked SKILL.md files."""
        index = RefIndex(
            by_basename={
                "SKILL.md": [
                    "skills/commit/SKILL.md",
                    "skills/init/SKILL.md",
                    "skills/configure/SKILL.md",
                ]
            }
        )
        assert classify_file_ref("SKILL.md", index) == "unresolvable_form"

    def test_direct_exact_match_resolves(self) -> None:
        """A reference that is itself an exact tracked path resolves."""
        index = RefIndex(
            by_basename={"executor.py": ["scripts/little_loops/fsm/executor.py"]}
        )
        assert (
            classify_file_ref("scripts/little_loops/fsm/executor.py", index) == "resolved"
        )


class TestClassifyIssueRefs:
    """Tests for classify_issue_refs() over a whole issue body."""

    def test_classifies_every_extracted_reference(self) -> None:
        index = RefIndex(
            by_basename={"executor.py": ["scripts/little_loops/fsm/executor.py"]}
        )
        content = (
            "See fsm/executor.py for the runner and "
            "scripts/little_loops/session_store.py for storage."
        )
        result = classify_issue_refs(content, index)
        assert result["fsm/executor.py"] == "resolved"
        assert result["scripts/little_loops/session_store.py"] == "stale"

    def test_empty_content_returns_empty_dict(self) -> None:
        index = RefIndex(by_basename={})
        assert classify_issue_refs("", index) == {}

    def test_planned_new_detected_from_containing_line(self) -> None:
        index = RefIndex(by_basename={})
        content = "### Files to Modify\n- `scripts/little_loops/new_thing.py` (new)\n"
        result = classify_issue_refs(content, index)
        assert result["scripts/little_loops/new_thing.py"] == "planned_new"


class TestBuildRefIndex:
    """Tests for build_ref_index() over a real git repo."""

    def test_indexes_tracked_files_by_basename(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "utils.py").write_text("# stub\n")
        subprocess.run(["git", "add", "pkg/utils.py"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

        index = build_ref_index(tmp_path)

        assert index.by_basename.get("utils.py") == ["pkg/utils.py"]

    def test_calls_git_ls_files_exactly_once(self, tmp_path: Path) -> None:
        completed = subprocess.CompletedProcess(
            args=["git", "ls-files", "-z"], returncode=0, stdout=b"a/b.py\0", stderr=b""
        )
        with patch("little_loops.text_utils.subprocess.run", return_value=completed) as mock_run:
            build_ref_index(tmp_path)
        assert mock_run.call_count == 1

    def test_git_unavailable_returns_empty_index(self, tmp_path: Path) -> None:
        with patch(
            "little_loops.text_utils.subprocess.run", side_effect=OSError("no git")
        ):
            index = build_ref_index(tmp_path)
        assert index.by_basename == {}

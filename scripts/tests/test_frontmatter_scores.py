"""Tests for little_loops.fsm.frontmatter_scores (FEAT-3474).

Covers the pure encoder (encode_frontmatter_scores) directly against the
issue's Encoding Rules, and the main() entry point (resolve -> clean slate ->
parse -> encode -> write) with no subprocess involved — there is no
fragment-heredoc-execution test precedent in this repo, so the scorer body
lives in this importable module and is exercised directly.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from little_loops.fsm.frontmatter_scores import encode_frontmatter_scores, main

# ---------------------------------------------------------------------------
# encode_frontmatter_scores — pure encoder
# ---------------------------------------------------------------------------


class TestEncodeBoolean:
    """boolean -> 100/0 by string-truthiness on true/yes/on/1 (case-insensitive);
    always written, including absent/null."""

    @pytest.mark.parametrize(
        "raw_value,expected",
        [
            ("true", "100"),
            ("True", "100"),
            ("TRUE", "100"),
            ("yes", "100"),
            ("Yes", "100"),
            ("on", "100"),
            ("On", "100"),
            ("1", "100"),
            ("false", "0"),
            ("no", "0"),
            ("off", "0"),
            ("0", "0"),
            ("garbage", "0"),
        ],
    )
    def test_string_truthiness(self, raw_value: str, expected: str) -> None:
        fm = {"decision_needed": raw_value}
        result = encode_frontmatter_scores(fm, [("decision_needed", "boolean")])
        assert result == {"decision_needed": expected}

    def test_absent_writes_zero(self) -> None:
        result = encode_frontmatter_scores({}, [("spike_needed", "boolean")])
        assert result == {"spike_needed": "0"}

    def test_null_writes_zero(self) -> None:
        result = encode_frontmatter_scores({"spike_needed": None}, [("spike_needed", "boolean")])
        assert result == {"spike_needed": "0"}

    def test_always_written_even_when_falsy(self) -> None:
        """Unlike numeric/string, boolean is never omitted."""
        result = encode_frontmatter_scores({}, [("decision_needed", "boolean")])
        assert "decision_needed" in result


class TestEncodeNumeric:
    """numeric -> scalar verbatim (even non-numeric); list -> len(list);
    absent/null -> no file."""

    def test_scalar_written_verbatim(self) -> None:
        result = encode_frontmatter_scores(
            {"confidence_score": "85"}, [("confidence_score", "numeric")]
        )
        assert result == {"confidence_score": "85"}

    def test_non_numeric_scalar_written_verbatim(self) -> None:
        """confidence_score: high is written as-is; engine's string fallback applies."""
        result = encode_frontmatter_scores(
            {"confidence_score": "high"}, [("confidence_score", "numeric")]
        )
        assert result == {"confidence_score": "high"}

    def test_leading_zeros_preserved(self) -> None:
        """coerce_types=False means '007' stays '007', not 7."""
        result = encode_frontmatter_scores(
            {"confidence_score": "007"}, [("confidence_score", "numeric")]
        )
        assert result == {"confidence_score": "007"}

    def test_list_value_under_numeric_is_count(self) -> None:
        result = encode_frontmatter_scores(
            {"blocked_by": ["BUG-1", "BUG-2"]}, [("blocked_by", "numeric")]
        )
        assert result == {"blocked_by": "2"}

    def test_absent_omitted(self) -> None:
        result = encode_frontmatter_scores({}, [("confidence_score", "numeric")])
        assert result == {}

    def test_null_omitted(self) -> None:
        result = encode_frontmatter_scores(
            {"confidence_score": None}, [("confidence_score", "numeric")]
        )
        assert result == {}


class TestEncodeList:
    """list -> count semantics; list -> len; non-empty non-list scalar -> 1;
    absent/null/empty list -> 0. Always written."""

    def test_list_value_is_len(self) -> None:
        result = encode_frontmatter_scores(
            {"blocked_by": ["BUG-1", "BUG-2", "BUG-3"]}, [("blocked_by", "list")]
        )
        assert result == {"blocked_by": "3"}

    def test_scalar_value_is_one(self) -> None:
        result = encode_frontmatter_scores({"blocked_by": "BUG-1"}, [("blocked_by", "list")])
        assert result == {"blocked_by": "1"}

    def test_absent_is_zero(self) -> None:
        result = encode_frontmatter_scores({}, [("blocked_by", "list")])
        assert result == {"blocked_by": "0"}

    def test_null_is_zero(self) -> None:
        result = encode_frontmatter_scores({"blocked_by": None}, [("blocked_by", "list")])
        assert result == {"blocked_by": "0"}

    def test_empty_list_is_zero(self) -> None:
        result = encode_frontmatter_scores({"blocked_by": []}, [("blocked_by", "list")])
        assert result == {"blocked_by": "0"}

    def test_always_written(self) -> None:
        result = encode_frontmatter_scores({}, [("blocked_by", "list")])
        assert "blocked_by" in result


class TestEncodeString:
    """string -> str(value).strip() verbatim; absent/null/empty -> no file."""

    def test_verbatim(self) -> None:
        result = encode_frontmatter_scores({"status": "open"}, [("status", "string")])
        assert result == {"status": "open"}

    def test_stripped(self) -> None:
        result = encode_frontmatter_scores(
            {"deferred_reason": "  waiting on design  "}, [("deferred_reason", "string")]
        )
        assert result == {"deferred_reason": "waiting on design"}

    def test_absent_omitted(self) -> None:
        result = encode_frontmatter_scores({}, [("deferred_reason", "string")])
        assert result == {}

    def test_null_omitted(self) -> None:
        result = encode_frontmatter_scores(
            {"deferred_reason": None}, [("deferred_reason", "string")]
        )
        assert result == {}

    def test_custom_field(self) -> None:
        """Arbitrary custom frontmatter keys work with no prior little-loops knowledge."""
        result = encode_frontmatter_scores({"severity": "critical"}, [("severity", "string")])
        assert result == {"severity": "critical"}


class TestPriorityRankDerivation:
    """priority_rank is synthesized from priority (^P(\\d)$ after strip); the only
    derived dimension — custom fields are never transformed."""

    def test_p2_derives_rank_2(self) -> None:
        result = encode_frontmatter_scores({"priority": "P2"}, [("priority_rank", "numeric")])
        assert result == {"priority_rank": "2"}

    def test_p0_derives_rank_0(self) -> None:
        result = encode_frontmatter_scores({"priority": "P0"}, [("priority_rank", "numeric")])
        assert result == {"priority_rank": "0"}

    def test_non_p_digit_value_no_file(self) -> None:
        result = encode_frontmatter_scores({"priority": "high"}, [("priority_rank", "numeric")])
        assert result == {}

    def test_absent_priority_no_file(self) -> None:
        result = encode_frontmatter_scores({}, [("priority_rank", "numeric")])
        assert result == {}

    def test_null_priority_no_file(self) -> None:
        result = encode_frontmatter_scores({"priority": None}, [("priority_rank", "numeric")])
        assert result == {}

    def test_priority_itself_still_verbatim_string(self) -> None:
        """priority is a separate declared dim from priority_rank; both may be present."""
        result = encode_frontmatter_scores(
            {"priority": "P2"},
            [("priority", "string"), ("priority_rank", "numeric")],
        )
        assert result == {"priority": "P2", "priority_rank": "2"}


class TestNameNormalization:
    """Output keys are normalized dim names (lowercase, spaces->hyphens,
    underscores untouched)."""

    def test_spaces_to_hyphens(self) -> None:
        result = encode_frontmatter_scores(
            {"Has Citations": "true"}, [("Has Citations", "boolean")]
        )
        assert result == {"has-citations": "100"}

    def test_underscores_untouched(self) -> None:
        result = encode_frontmatter_scores(
            {"confidence_score": "85"}, [("confidence_score", "numeric")]
        )
        assert "confidence_score" in result


class TestEncodeMissingFields:
    def test_dim_key_entirely_absent_from_fm(self) -> None:
        """A dim declared but not present anywhere in fm behaves like None."""
        result = encode_frontmatter_scores({"other": "value"}, [("severity", "string")])
        assert result == {}

    def test_multiple_dims_mixed_present_absent(self) -> None:
        fm = {"status": "open", "confidence_score": "40"}
        dims = [
            ("status", "string"),
            ("confidence_score", "numeric"),
            ("outcome_confidence", "numeric"),
            ("deferred_reason", "string"),
        ]
        result = encode_frontmatter_scores(fm, dims)
        assert result == {"status": "open", "confidence_score": "40"}


# ---------------------------------------------------------------------------
# main() — resolve -> clean slate -> parse -> encode -> write
# ---------------------------------------------------------------------------


def _write_issue(
    issues_base: Path,
    *,
    category: str = "features",
    filename: str = "P3-FEAT-001-test-issue.md",
    frontmatter: str,
) -> Path:
    cat_dir = issues_base / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    path = cat_dir / filename
    path.write_text(f"---\n{frontmatter}\n---\n\n# Test Issue\n")
    return path


class TestMainHappyPath:
    def test_writes_expected_dim_files(
        self,
        make_project: Callable[..., tuple[Path, Path]],
        sample_config: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        project_root, issues_base = make_project(sample_config)
        _write_issue(
            issues_base,
            frontmatter=(
                "id: FEAT-001\n"
                "status: open\n"
                "priority: P2\n"
                "confidence_score: '85'\n"
                "decision_needed: true\n"
                "blocked_by:\n"
                "  - BUG-1\n"
                "  - BUG-2\n"
                "severity: critical\n"
            ),
        )
        monkeypatch.chdir(project_root)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        dims_text = (
            "status:string|priority:string|priority_rank:numeric|"
            "confidence_score:numeric|decision_needed:boolean|"
            "blocked_by:list|severity:string"
        )
        rc = main("FEAT-001", dims_text, str(run_dir))
        assert rc == 0

        assert (run_dir / "rubric-dim-status.txt").read_text() == "open"
        assert (run_dir / "rubric-dim-priority.txt").read_text() == "P2"
        assert (run_dir / "rubric-dim-priority_rank.txt").read_text() == "2"
        assert (run_dir / "rubric-dim-confidence_score.txt").read_text() == "85"
        assert (run_dir / "rubric-dim-decision_needed.txt").read_text() == "100"
        assert (run_dir / "rubric-dim-blocked_by.txt").read_text() == "2"
        assert (run_dir / "rubric-dim-severity.txt").read_text() == "critical"

    def test_unresolved_issue_id_returns_nonzero(
        self,
        make_project: Callable[..., tuple[Path, Path]],
        sample_config: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        project_root, issues_base = make_project(sample_config)
        monkeypatch.chdir(project_root)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        rc = main("FEAT-99999", "status:string", str(run_dir))
        assert rc != 0
        # No score files were written for an unresolved issue.
        assert list(run_dir.glob("rubric-dim-*.txt")) == []

    def test_two_pass_clean_slate(
        self,
        make_project: Callable[..., tuple[Path, Path]],
        sample_config: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """A field present on pass 1 and cleared by pass 2 must not leave a stale file."""
        project_root, issues_base = make_project(sample_config)
        issue_path = _write_issue(
            issues_base,
            frontmatter=("id: FEAT-002\ndeferred_reason: waiting on design\n"),
            filename="P3-FEAT-002-test-issue.md",
        )
        monkeypatch.chdir(project_root)
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        dims_text = "deferred_reason:string"
        rc = main("FEAT-002", dims_text, str(run_dir))
        assert rc == 0
        dim_file = run_dir / "rubric-dim-deferred_reason.txt"
        assert dim_file.exists()
        assert dim_file.read_text() == "waiting on design"

        # Clear the field (refine-issue would do this) and re-run.
        issue_path.write_text("---\nid: FEAT-002\ndeferred_reason:\n---\n\n# Test Issue\n")
        rc = main("FEAT-002", dims_text, str(run_dir))
        assert rc == 0
        assert not dim_file.exists()

    def test_clean_slate_clears_aggregate_file_too(
        self,
        make_project: Callable[..., tuple[Path, Path]],
        sample_config: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        project_root, issues_base = make_project(sample_config)
        _write_issue(
            issues_base,
            frontmatter="id: FEAT-003\nstatus: open\n",
            filename="P3-FEAT-003-test-issue.md",
        )
        monkeypatch.chdir(project_root)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "rubric-aggregate.txt").write_text("77")
        (run_dir / "rubric-dim-stale.txt").write_text("stale-value")

        rc = main("FEAT-003", "status:string", str(run_dir))
        assert rc == 0
        assert not (run_dir / "rubric-aggregate.txt").exists()
        assert not (run_dir / "rubric-dim-stale.txt").exists()
        assert (run_dir / "rubric-dim-status.txt").read_text() == "open"

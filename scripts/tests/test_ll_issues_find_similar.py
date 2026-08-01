"""Tests for ll-issues find-similar sub-command (ENH-2941)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch


def _write_issue(
    path: Path, issue_id: str, title: str, status: str = "open", body: str = ""
) -> None:
    path.write_text(f"---\nid: {issue_id}\nstatus: {status}\n---\n# {issue_id}: {title}\n\n{body}")


def _run(argv: list[str], temp_project_dir: Path, sample_config: dict[str, Any]) -> tuple[int, str]:
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))

    with patch.object(sys, "argv", ["ll-issues", *argv, "--config", str(temp_project_dir)]):
        import contextlib
        import io

        from little_loops.cli import main_issues

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = main_issues()
        return result, buf.getvalue()


class TestIssuesCLIFindSimilar:
    """Tests for ll-issues find-similar sub-command."""

    def test_find_similar_output_is_ranked_json(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """find-similar returns a JSON array of {id, title, path, score}."""
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-100-auth.md",
            "BUG-100",
            "authentication token refresh failure",
        )
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-101-unrelated.md",
            "BUG-101",
            "database migration rollback",
        )

        result, out = _run(
            ["find-similar", "authentication token refresh"], temp_project_dir, sample_config
        )

        assert result == 0
        data = json.loads(out)
        assert isinstance(data, list)
        ids = [m["id"] for m in data]
        assert "BUG-100" in ids
        assert "BUG-101" not in ids
        match = next(m for m in data if m["id"] == "BUG-100")
        assert set(match) == {"id", "title", "path", "score"}
        assert 0.0 < match["score"] <= 1.0

    def test_find_similar_deterministic(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """Repeated invocations with the same input produce identical output."""
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-100-auth.md",
            "BUG-100",
            "authentication token refresh failure",
        )

        _, out1 = _run(
            ["find-similar", "authentication token refresh"], temp_project_dir, sample_config
        )
        _, out2 = _run(
            ["find-similar", "authentication token refresh"], temp_project_dir, sample_config
        )
        assert out1 == out2

    def test_find_similar_title_only_guard(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """A body-similar but title-dissimilar issue scores below threshold."""
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-200-widget.md",
            "BUG-200",
            "widget rendering glitch",
            body=(
                "## Summary\n\nauthentication token refresh authentication token refresh "
                "authentication token refresh authentication token refresh\n"
            ),
        )

        result, out = _run(
            ["find-similar", "authentication token refresh", "--threshold", "0.5"],
            temp_project_dir,
            sample_config,
        )

        assert result == 0
        data = json.loads(out)
        assert all(m["id"] != "BUG-200" for m in data)

    def test_find_similar_threshold_override(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """--threshold overrides the config default and filters out weak matches."""
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-300-partial.md",
            "BUG-300",
            "token refresh logic",
        )

        result, out = _run(
            ["find-similar", "authentication token refresh failure", "--threshold", "0.99"],
            temp_project_dir,
            sample_config,
        )

        assert result == 0
        data = json.loads(out)
        assert data == []

    def test_find_similar_threshold_defaults_from_config(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """No --threshold: default tracks config.issues.duplicate_detection.similar_threshold."""
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-400-partial.md",
            "BUG-400",
            "token refresh logic",
        )
        sample_config.setdefault("issues", {})["duplicate_detection"] = {"similar_threshold": 0.99}

        result, out = _run(
            ["find-similar", "authentication token refresh failure"],
            temp_project_dir,
            sample_config,
        )

        assert result == 0
        data = json.loads(out)
        assert data == []

    def test_find_similar_limit(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """--limit caps the number of returned matches."""
        for i in range(5):
            _write_issue(
                issues_dir / "bugs" / f"P1-BUG-{500 + i}-auth.md",
                f"BUG-{500 + i}",
                "authentication token refresh failure",
            )

        result, out = _run(
            ["find-similar", "authentication token refresh failure", "--limit", "2"],
            temp_project_dir,
            sample_config,
        )

        assert result == 0
        data = json.loads(out)
        assert len(data) == 2

    def test_find_similar_against_all_includes_done(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """--against all includes done/cancelled issues; default open excludes them."""
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-600-auth.md",
            "BUG-600",
            "authentication token refresh failure",
            status="done",
        )

        result_open, out_open = _run(
            ["find-similar", "authentication token refresh failure"],
            temp_project_dir,
            sample_config,
        )
        result_all, out_all = _run(
            ["find-similar", "authentication token refresh failure", "--against", "all"],
            temp_project_dir,
            sample_config,
        )

        assert result_open == 0
        assert result_all == 0
        assert all(m["id"] != "BUG-600" for m in json.loads(out_open))
        assert any(m["id"] == "BUG-600" for m in json.loads(out_all))

    def test_find_similar_missing_text_returns_error(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """find-similar without TEXT and without --batch returns exit code 1."""
        result, _ = _run(["find-similar"], temp_project_dir, sample_config)
        assert result == 1

    def test_find_similar_fs_alias(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """find-similar is accessible via the 'fs' alias."""
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-700-auth.md",
            "BUG-700",
            "authentication token refresh failure",
        )

        result, out = _run(["fs", "authentication token refresh"], temp_project_dir, sample_config)

        assert result == 0
        data = json.loads(out)
        assert any(m["id"] == "BUG-700" for m in data)


class TestBatchSimilarity:
    """Tests for ll-issues find-similar --batch pairwise mode."""

    def test_batch_returns_pairs_above_threshold(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """--batch returns {a, b, score} pairs for similar-titled issues."""
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-800-a.md",
            "BUG-800",
            "authentication token refresh failure",
        )
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-801-b.md",
            "BUG-801",
            "authentication token refresh error",
        )
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-802-c.md",
            "BUG-802",
            "database migration rollback",
        )

        result, out = _run(["find-similar", "--batch"], temp_project_dir, sample_config)

        assert result == 0
        data = json.loads(out)
        assert isinstance(data, list)
        pair_ids = {frozenset((p["a"], p["b"])) for p in data}
        assert frozenset({"BUG-800", "BUG-801"}) in pair_ids
        assert frozenset({"BUG-800", "BUG-802"}) not in pair_ids
        for pair in data:
            assert set(pair) == {"a", "b", "score"}

    def test_batch_against_defaults_to_open(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """--batch with no --against excludes done/cancelled issues by default."""
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-900-a.md",
            "BUG-900",
            "authentication token refresh failure",
        )
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-901-b.md",
            "BUG-901",
            "authentication token refresh error",
            status="done",
        )

        result, out = _run(["find-similar", "--batch"], temp_project_dir, sample_config)

        assert result == 0
        data = json.loads(out)
        assert not any("BUG-901" in (p["a"], p["b"]) for p in data)

    def test_batch_against_all_includes_done(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """--batch --against all includes done/cancelled issues."""
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-910-a.md",
            "BUG-910",
            "authentication token refresh failure",
        )
        _write_issue(
            issues_dir / "bugs" / "P1-BUG-911-b.md",
            "BUG-911",
            "authentication token refresh error",
            status="done",
        )

        result, out = _run(
            ["find-similar", "--batch", "--against", "all"], temp_project_dir, sample_config
        )

        assert result == 0
        data = json.loads(out)
        assert any("BUG-911" in (p["a"], p["b"]) for p in data)


class TestSimilarityMatchToDict:
    """Tests for SimilarityMatch/SimilarityPair to_dict() rounding."""

    def test_similarity_match_to_dict_rounds_score(self) -> None:
        from little_loops.cli.issues.find_similar import SimilarityMatch

        match = SimilarityMatch(id="BUG-1", title="t", path="p", score=1 / 3)
        assert match.to_dict()["score"] == 0.333

    def test_similarity_pair_to_dict_rounds_score(self) -> None:
        from little_loops.cli.issues.find_similar import SimilarityPair

        pair = SimilarityPair(a="BUG-1", b="BUG-2", score=2 / 3)
        assert pair.to_dict()["score"] == 0.667

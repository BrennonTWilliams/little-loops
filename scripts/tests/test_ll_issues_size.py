"""Tests for ll-issues size sub-command (ENH-2945)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch


def _write_issue(path: Path, issue_id: str, body: str) -> None:
    prefix = issue_id.split("-", 1)[0]
    path.write_text(
        f"---\nid: {issue_id}\ntype: {prefix}\nstatus: open\n---\n# {issue_id}: Example\n\n{body}\n"
    )


def _run(argv: list[str], temp_project_dir: Path, sample_config: dict[str, Any]) -> tuple[int, str]:
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))

    with patch.object(sys, "argv", ["ll-issues", *argv, "--config", str(temp_project_dir)]):
        from little_loops.cli.issues import main_issues

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = main_issues()
        return result, buf.getvalue()


def _fake_issue(issue_id: str):
    from little_loops.issue_parser import IssueInfo

    return IssueInfo(
        path=Path(f"{issue_id}.md"),
        issue_type="enhancements",
        priority="P2",
        issue_id=issue_id,
        title="Example",
    )


class TestComputeSize:
    def test_score_two_is_small(self) -> None:
        from little_loops.cli.issues.size import compute_size

        body = (
            "## Summary\nA small change.\n\n"
            "## Proposed Solution\n"
            "Touch `scripts/a.py`, `scripts/b.py`, and `scripts/c.py`.\n"
        )
        score = compute_size(_fake_issue("ENH-001"), body)

        assert score.score == 2
        assert score.label == "Small"
        assert score.signals["file_count"] == 2
        assert score.signals["multiple_concerns"] == 0

    def test_score_three_is_medium(self) -> None:
        from little_loops.cli.issues.size import compute_size

        body = (
            "## Summary\nA change.\n\n"
            "## Proposed Solution\n"
            "Do the thing. Additionally, handle the edge case separately.\n"
        )
        score = compute_size(_fake_issue("ENH-002"), body)

        assert score.score == 3
        assert score.label == "Medium"
        assert score.signals["multiple_concerns"] == 3
        assert score.signals["file_count"] == 0

    def test_score_seven_is_large(self) -> None:
        from little_loops.cli.issues.size import compute_size

        long_para = ("word " * 320).strip() + "."
        body = (
            "## Summary\nA change.\n\n"
            "## Proposed Solution\n"
            f"Touch `scripts/a.py`, `scripts/b.py`, and `scripts/c.py`. Additionally, {long_para}\n"
        )
        score = compute_size(_fake_issue("ENH-003"), body)

        assert score.score == 7
        assert score.label == "Large"
        assert score.signals["file_count"] == 2
        assert score.signals["section_complexity"] == 2
        assert score.signals["multiple_concerns"] == 3
        assert score.signals["dependency_mentions"] == 0
        assert score.signals["word_count"] == 0

    def test_score_eight_is_very_large(self) -> None:
        from little_loops.cli.issues.size import compute_size

        long_para = ("word " * 850).strip() + "."
        body = (
            "## Summary\nRelated to ENH-500.\n\n"
            "## Proposed Solution\n"
            f"Touch `scripts/a.py`, `scripts/b.py`, and `scripts/c.py`. {long_para}\n"
        )
        score = compute_size(_fake_issue("ENH-004"), body)

        assert score.score == 8
        assert score.label == "Very Large"
        assert score.signals["file_count"] == 2
        assert score.signals["section_complexity"] == 2
        assert score.signals["multiple_concerns"] == 0
        assert score.signals["dependency_mentions"] == 2
        assert score.signals["word_count"] == 2

    def test_self_id_reference_excluded_from_dependency_signal(self) -> None:
        from little_loops.cli.issues.size import compute_size

        body = "## Summary\nENH-005 fixes its own thing, no other refs.\n"
        score = compute_size(_fake_issue("ENH-005"), body)

        assert score.signals["dependency_mentions"] == 0


class TestWriteSize:
    def test_write_size_stamps_frontmatter(self, temp_project_dir: Path) -> None:
        from little_loops.cli.issues.size import SizeScore, write_size

        path = temp_project_dir / "issue.md"
        _write_issue(path, "ENH-006", "## Summary\nShort.\n")
        write_size(path, SizeScore(id="ENH-006", score=2, label="Small", signals={}))

        content = path.read_text()
        assert "size: Small" in content
        assert "id: ENH-006" in content  # other fields preserved

    def test_write_size_idempotent(self, temp_project_dir: Path) -> None:
        from little_loops.cli.issues.size import SizeScore, write_size

        path = temp_project_dir / "issue.md"
        _write_issue(path, "ENH-007", "## Summary\nShort.\n")
        score = SizeScore(id="ENH-007", score=5, label="Large", signals={})
        write_size(path, score)
        first = path.read_text()
        write_size(path, score)
        second = path.read_text()

        assert first == second
        assert first.count("size: Large") == 1


class TestCliSize:
    def test_size_single_issue_json(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        enh_dir = temp_project_dir / ".issues" / "enhancements"
        enh_dir.mkdir(parents=True, exist_ok=True)
        _write_issue(enh_dir / "P2-ENH-008-example.md", "ENH-008", "## Summary\nShort change.\n")

        exit_code, output = _run(["size", "ENH-008", "--json"], temp_project_dir, sample_config)
        assert exit_code == 0
        data = json.loads(output)
        assert data[0]["id"] == "ENH-008"
        assert data[0]["label"] == "Small"

    def test_size_requires_exactly_one_target_mode(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        exit_code, _ = _run(["size"], temp_project_dir, sample_config)
        assert exit_code == 1

    def test_size_write_flag_persists_label(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        enh_dir = temp_project_dir / ".issues" / "enhancements"
        enh_dir.mkdir(parents=True, exist_ok=True)
        issue_path = enh_dir / "P2-ENH-009-example.md"
        _write_issue(issue_path, "ENH-009", "## Summary\nShort change.\n")

        exit_code, _ = _run(["size", "ENH-009", "--write"], temp_project_dir, sample_config)
        assert exit_code == 0
        assert "size: Small" in issue_path.read_text()

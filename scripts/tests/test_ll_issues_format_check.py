"""Tests for ll-issues format-check subcommand (ENH-2426)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CLEAN_BUG_BODY = "\n".join(
    [
        "---",
        "id: BUG-9101",
        "status: open",
        "---",
        "",
        "# BUG-9101: Test bug",
        "",
        "## Summary",
        "A real problem happens under specific conditions.",
        "",
        "## Current Behavior",
        "It breaks in a specific way.",
        "",
        "## Expected Behavior",
        "It should not break.",
        "",
        "## Steps to Reproduce",
        "1. Do the thing.",
        "2. Observe failure.",
        "",
        "## Impact",
        "- **Priority**: P3 - Low",
        "- **Effort**: Small",
        "- **Risk**: Low",
        "- **Breaking Change**: No",
        "",
        "## Status",
        "open",
    ]
)


@pytest.fixture
def format_check_dir(temp_project_dir: Path, sample_config: dict[str, Any]) -> Path:
    """Base fixture: temp project with config and empty .issues dirs."""
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))
    issues_base = temp_project_dir / ".issues"
    (issues_base / "bugs").mkdir(parents=True, exist_ok=True)
    (issues_base / "features").mkdir(parents=True, exist_ok=True)
    (issues_base / "enhancements").mkdir(parents=True, exist_ok=True)
    return issues_base


def _write_issue(issues_dir: Path, filename: str, body: str) -> Path:
    path = issues_dir / "bugs" / filename
    path.write_text(body)
    return path


def _invoke(argv: list[str]) -> int:
    """Invoke main_issues() with given argv."""
    with patch.object(sys, "argv", argv):
        from little_loops.cli import main_issues

        return main_issues()


# ---------------------------------------------------------------------------
# TestFormatCheckClean
# ---------------------------------------------------------------------------


class TestFormatCheckClean:
    """A fully-populated, non-boilerplate issue exits 0."""

    def test_clean_issue_exits_zero(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_issue(format_check_dir, "P3-BUG-9101-test-bug.md", _CLEAN_BUG_BODY)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9101", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "BUG-9101" in out


# ---------------------------------------------------------------------------
# TestFormatCheckMissing
# ---------------------------------------------------------------------------


class TestFormatCheckMissing:
    """A required section absent entirely exits 1 and is reported as missing."""

    def test_missing_section_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace("## Expected Behavior\nIt should not break.\n\n", "")
        _write_issue(format_check_dir, "P3-BUG-9102-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9102", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "missing: Expected Behavior" in out


# ---------------------------------------------------------------------------
# TestFormatCheckRenamed
# ---------------------------------------------------------------------------


class TestFormatCheckRenamed:
    """A present deprecated section with a canonical replacement exits 1."""

    def test_renamed_section_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY + "\n\n## Proposed Fix\nOld-style content.\n"
        _write_issue(format_check_dir, "P3-BUG-9103-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9103", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "renamed: Proposed Fix → Proposed Solution" in out


# ---------------------------------------------------------------------------
# TestFormatCheckEmpty
# ---------------------------------------------------------------------------


class TestFormatCheckEmpty:
    """A required header present with a whitespace-only body exits 1."""

    def test_empty_section_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace(
            "## Summary\nA real problem happens under specific conditions.\n",
            "## Summary\n\n",
        )
        _write_issue(format_check_dir, "P3-BUG-9104-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9104", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "empty: Summary" in out


# ---------------------------------------------------------------------------
# TestFormatCheckBoilerplate
# ---------------------------------------------------------------------------


class TestFormatCheckBoilerplate:
    """A required header whose body equals its creation_template exits 1."""

    def test_boilerplate_section_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace(
            "## Summary\nA real problem happens under specific conditions.\n",
            "## Summary\n[Description extracted from input]\n",
        )
        _write_issue(format_check_dir, "P3-BUG-9105-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9105", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "boilerplate: Summary" in out


# ---------------------------------------------------------------------------
# TestFormatCheckJsonOutput
# ---------------------------------------------------------------------------


class TestFormatCheckJsonOutput:
    """--format json prints the structured gap report."""

    def test_clean_issue_json_output(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_issue(format_check_dir, "P3-BUG-9106-test-bug.md", _CLEAN_BUG_BODY)

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9106",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        data = json.loads(out)
        assert data == {"missing": [], "renamed": [], "empty": [], "boilerplate": []}

    def test_gapped_issue_json_output(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace("## Expected Behavior\nIt should not break.\n\n", "")
        _write_issue(format_check_dir, "P3-BUG-9107-test-bug.md", body)

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9107",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        data = json.loads(out)
        assert data["missing"] == ["Expected Behavior"]


# ---------------------------------------------------------------------------
# TestFormatCheckIssueNotFound
# ---------------------------------------------------------------------------


class TestFormatCheckIssueNotFound:
    """An unresolvable issue ID exits 1 with an error on stderr."""

    def test_not_found_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = _invoke(
            ["ll-issues", "format-check", "BUG-9999", "--config", str(temp_project_dir)]
        )
        _, err = capsys.readouterr()

        assert result == 1
        assert "not found" in err.lower()


# ---------------------------------------------------------------------------
# TestFormatCheckFailOpen
# ---------------------------------------------------------------------------


class TestFormatCheckFailOpen:
    """An unresolved template (fail-open) exits 0 even though sections are missing."""

    def test_unresolved_template_exits_zero(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        empty_templates = tmp_path / "empty-templates"
        empty_templates.mkdir()

        config_override = {**sample_config}
        config_override["issues"] = {
            **sample_config.get("issues", {}),
            "templates_dir": str(empty_templates),
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(config_override))

        _write_issue(format_check_dir, "P3-BUG-9108-test-bug.md", "## Summary\nOnly Summary.")

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9108", "--config", str(temp_project_dir)]
        )

        assert result == 0

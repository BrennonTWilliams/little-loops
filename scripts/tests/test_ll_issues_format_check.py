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
# TestFormatCheckMalformedId
# ---------------------------------------------------------------------------


class TestFormatCheckMalformedId:
    """A frontmatter id disagreeing with the filename's TYPE-NNN exits 1 (BUG-2769)."""

    def test_malformed_id_section_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: 9108")
        _write_issue(format_check_dir, "P3-BUG-9108-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9108", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "malformed_id: id: 9108 (expected BUG-9108)" in out


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
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9106")
        _write_issue(format_check_dir, "P3-BUG-9106-test-bug.md", body)

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
        assert data == {
            "missing": [],
            "renamed": [],
            "empty": [],
            "boilerplate": [],
            "malformed_id": [],
            "prose_dep_drift": [],
            "stale_prose_dep": [],
            "program_design_nonspecific": [],
        }

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


# ---------------------------------------------------------------------------
# TestFormatCheckProseDeps (FEAT-2849)
# ---------------------------------------------------------------------------


def _write_feature(issues_dir: Path, filename: str, body: str) -> Path:
    path = issues_dir / "features" / filename
    path.write_text(body)
    return path


class TestFormatCheckProseDeps:
    """prose_dep_drift / stale_prose_dep gap kinds (FEAT-2849)."""

    def test_prose_dep_on_active_issue_reports_drift(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_feature(
            format_check_dir,
            "P2-FEAT-9200-blocker.md",
            "---\nid: FEAT-9200\nstatus: open\n---\n\n# FEAT-9200: Blocker\n",
        )
        body = _CLEAN_BUG_BODY.replace(
            "id: BUG-9101",
            "id: BUG-9109",
        ).replace(
            "## Summary\nA real problem happens under specific conditions.",
            "## Summary\nDepends on FEAT-9200 for the underlying fix.",
        )
        _write_issue(format_check_dir, "P3-BUG-9109-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9109", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "prose_dep_drift: FEAT-9200" in out

    def test_prose_dep_on_done_issue_reports_stale(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_feature(
            format_check_dir,
            "P2-FEAT-9201-blocker.md",
            "---\nid: FEAT-9201\nstatus: done\n---\n\n# FEAT-9201: Blocker\n",
        )
        body = _CLEAN_BUG_BODY.replace(
            "id: BUG-9101",
            "id: BUG-9110",
        ).replace(
            "## Summary\nA real problem happens under specific conditions.",
            "## Summary\nBlocked by FEAT-9201 until it ships.",
        )
        _write_issue(format_check_dir, "P3-BUG-9110-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9110", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "stale_prose_dep: FEAT-9201" in out
        assert "prose_dep_drift" not in out

    def test_prose_dep_already_in_blocked_by_is_clean(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_feature(
            format_check_dir,
            "P2-FEAT-9202-blocker.md",
            "---\nid: FEAT-9202\nstatus: open\n---\n\n# FEAT-9202: Blocker\n",
        )
        body = _CLEAN_BUG_BODY.replace(
            "id: BUG-9101",
            "id: BUG-9111\nblocked_by:\n- FEAT-9202",
        ).replace(
            "## Summary\nA real problem happens under specific conditions.",
            "## Summary\nDepends on FEAT-9202 for the underlying fix.",
        )
        _write_issue(format_check_dir, "P3-BUG-9111-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9111", "--config", str(temp_project_dir)]
        )

        assert result == 0


# ---------------------------------------------------------------------------
# TestFormatCheckAll (FEAT-2850)
# ---------------------------------------------------------------------------


class TestFormatCheckAll:
    """Repo-wide sweep mode via ``--all`` (FEAT-2850)."""

    def test_no_issue_id_and_no_all_errors(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = _invoke(["ll-issues", "format-check", "--config", str(temp_project_dir)])
        _, err = capsys.readouterr()

        assert result == 1
        assert "--all" in err

    def test_all_clean_exits_zero(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_issue(
            format_check_dir,
            "P3-BUG-9301-test-bug.md",
            _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9301"),
        )

        result = _invoke(["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 0
        assert "structurally compliant" in out

    def test_all_reports_gapped_issue_only(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_issue(
            format_check_dir,
            "P3-BUG-9302-test-bug.md",
            _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9302"),
        )
        gapped = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9303").replace(
            "## Expected Behavior\nIt should not break.\n\n", ""
        )
        _write_issue(format_check_dir, "P3-BUG-9303-test-bug.md", gapped)

        result = _invoke(["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 1
        assert "BUG-9303" in out
        assert "missing: Expected Behavior" in out
        assert "BUG-9302" not in out

    def test_all_json_output(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        gapped = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9304").replace(
            "## Expected Behavior\nIt should not break.\n\n", ""
        )
        _write_issue(format_check_dir, "P3-BUG-9304-test-bug.md", gapped)

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "--all",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        data = json.loads(out)
        assert data["BUG-9304"]["missing"] == ["Expected Behavior"]


# ---------------------------------------------------------------------------
# TestFormatCheckFix (FEAT-2851)
# ---------------------------------------------------------------------------


class TestFormatCheckFix:
    """``--fix``/``--apply`` backfills blocked_by from prose_dep_drift via link.py."""

    def _write_drifting_bug(self, format_check_dir: Path, bug_id: str, filename: str) -> Path:
        _write_feature(
            format_check_dir,
            "P2-FEAT-9500-blocker.md",
            "---\nid: FEAT-9500\nstatus: open\n---\n\n# FEAT-9500: Blocker\n",
        )
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", f"id: {bug_id}").replace(
            "## Summary\nA real problem happens under specific conditions.",
            "## Summary\nDepends on FEAT-9500 for the underlying fix.",
        )
        return _write_issue(format_check_dir, filename, body)

    def test_fix_without_apply_previews_and_does_not_write(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_drifting_bug(format_check_dir, "BUG-9401", "P3-BUG-9401-test-bug.md")
        before = path.read_text()

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9401", "--fix", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "would link (dry-run)" in out
        assert "prose_dep_drift: FEAT-9500" in out
        assert path.read_text() == before

    def test_fix_apply_writes_blocked_by_and_clears_drift(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_drifting_bug(format_check_dir, "BUG-9402", "P3-BUG-9402-test-bug.md")

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9402",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert "linked" in out
        assert "blocked_by" in path.read_text()
        assert "FEAT-9500" in path.read_text()
        assert result == 0
        assert "prose_dep_drift" not in out

    def test_fix_apply_is_idempotent(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_drifting_bug(format_check_dir, "BUG-9403", "P3-BUG-9403-test-bug.md")

        _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9403",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()
        after_first = path.read_text()

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9403",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "prose_dep_drift" not in out
        assert path.read_text() == after_first

    def test_fix_all_mode_applies_across_sweep(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_drifting_bug(format_check_dir, "BUG-9404", "P3-BUG-9404-test-bug.md")

        _invoke(
            [
                "ll-issues",
                "format-check",
                "--all",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert "BUG-9404" not in out or "prose_dep_drift" not in out.split("BUG-9404:")[-1]
        assert "blocked_by" in path.read_text()
        assert "FEAT-9500" in path.read_text()


# ---------------------------------------------------------------------------
# TestFormatCheckProgramDesign (ENH-2852)
# ---------------------------------------------------------------------------


class TestFormatCheckProgramDesign:
    """The Program Design gate reaches the CLI, and is off in unstamped projects."""

    @staticmethod
    def _arm(temp_project_dir: Path, stamp_date: str) -> None:
        (temp_project_dir / ".ll" / "program-design-cutover.json").write_text(
            json.dumps({"sha": "0" * 40, "date": stamp_date})
        )

    def test_unstamped_project_reports_no_program_design_gap(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Fail open: the clean-bug fixture has no `## Program Design` and still passes."""
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9601")
        _write_issue(format_check_dir, "P3-BUG-9601-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9601", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0, out
        assert "Program Design" not in out

    def test_nonspecific_section_surfaces_in_text_output(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._arm(temp_project_dir, "2020-01-01")
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9602").replace(
            "## Status\nopen",
            "## Program Design\n\n### Types\n\nSome prose about the shape.\n\n"
            "### Signatures\n\nA function will be added.\n\n"
            "### Call Path\n\nThe CLI reaches the parser somehow.\n\n## Status\nopen",
        )
        _write_issue(format_check_dir, "P3-BUG-9602-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9602", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "program_design_nonspecific: Program Design:" in out

    def test_missing_section_surfaces_after_cutover(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._arm(temp_project_dir, "2020-01-01")
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9603")
        _write_issue(format_check_dir, "P3-BUG-9603-test-bug.md", body)

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9603",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "Program Design" in json.loads(out)["missing"]

    def test_escape_hatch_passes_after_cutover(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._arm(temp_project_dir, "2020-01-01")
        body = _CLEAN_BUG_BODY.replace(
            "id: BUG-9101", "id: BUG-9604\nprogram_design_not_applicable: true"
        )
        _write_issue(format_check_dir, "P3-BUG-9604-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9604", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0, out

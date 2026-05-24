"""Tests for BUG-1649: create-sprint Step 1.5.1 must use ll-issues list --json.

Verifies that commands/create-sprint.md Step 1.5.1 delegates to
`ll-issues list --json` (the canonical active-issue source) and no longer
contains the raw type-dir Glob patterns that caused done/cancelled issues
to be counted as active after the ENH-1390 layout migration.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CREATE_SPRINT = PROJECT_ROOT / "commands" / "create-sprint.md"


def _step_151_region(content: str) -> str:
    """Extract the Step 1.5.1 region up to (not including) Step 1.5.2."""
    start = content.find("#### Step 1.5.1:")
    end = content.find("#### Step 1.5.2:", start)
    assert start != -1, "Step 1.5.1 header not found in create-sprint.md"
    assert end != -1, "Step 1.5.2 header not found in create-sprint.md"
    return content[start:end]


class TestCreateSprintActiveIssueScan:
    """commands/create-sprint.md Step 1.5.1 must use the canonical active-issue CLI."""

    def test_ll_issues_list_json_present_in_step_151(self) -> None:
        content = CREATE_SPRINT.read_text()
        region = _step_151_region(content)
        assert "ll-issues list --json" in region, (
            "Step 1.5.1 must call `ll-issues list --json` to get the canonical "
            "active-issue set (status: open/in_progress/blocked)"
        )

    def test_raw_bugs_glob_absent_from_step_151(self) -> None:
        content = CREATE_SPRINT.read_text()
        region = _step_151_region(content)
        # The primary scan path must not use a bare Glob over the bugs dir
        assert "bugs/*.md" not in region or "fallback" in region.lower(), (
            "Step 1.5.1 must not use raw `bugs/*.md` Glob as the primary scan path; "
            "it causes done/cancelled issues to be counted as active (BUG-1649)"
        )

    def test_raw_features_glob_absent_from_step_151(self) -> None:
        content = CREATE_SPRINT.read_text()
        region = _step_151_region(content)
        assert "features/*.md" not in region or "fallback" in region.lower(), (
            "Step 1.5.1 must not use raw `features/*.md` Glob as the primary scan path; "
            "it causes done/cancelled issues to be counted as active (BUG-1649)"
        )

    def test_raw_enhancements_glob_absent_from_step_151(self) -> None:
        content = CREATE_SPRINT.read_text()
        region = _step_151_region(content)
        assert "enhancements/*.md" not in region or "fallback" in region.lower(), (
            "Step 1.5.1 must not use raw `enhancements/*.md` Glob as the primary scan path; "
            "it causes done/cancelled issues to be counted as active (BUG-1649)"
        )

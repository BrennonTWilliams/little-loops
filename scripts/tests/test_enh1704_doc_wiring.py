"""Tests for ENH-1704: foreground log capture documentation accuracy.

Verifies that stale text claiming foreground runs never create a log file is absent
from docs/reference/CLI.md and docs/guides/LOOPS_GUIDE.md, and that accurate
replacement text reflecting ENH-1703 (always-on _TeeWriter) is present.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CLI_MD = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
LOOPS_GUIDE = PROJECT_ROOT / "docs" / "guides" / "LOOPS_GUIDE.md"


class TestCliMdForegroundLogCapture:
    """docs/reference/CLI.md must reflect always-on foreground log capture."""

    def test_stale_null_for_foreground_absent(self) -> None:
        content = CLI_MD.read_text()
        assert "log_file` is `null` for foreground runs" not in content, (
            "docs/reference/CLI.md must not claim log_file is null for foreground runs"
        )

    def test_accurate_log_file_description_present(self) -> None:
        content = CLI_MD.read_text()
        assert "foreground and background runs" in content, (
            "docs/reference/CLI.md must state that log_file is a path for both foreground and background runs"
        )


class TestLoopsGuideForegroundLogCapture:
    """docs/guides/LOOPS_GUIDE.md must reflect always-on foreground log capture."""

    def test_stale_never_create_log_absent(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "never create a `.log` file" not in content, (
            "docs/guides/LOOPS_GUIDE.md must not claim foreground runs never create a .log file"
        )

    def test_stale_null_for_foreground_absent(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "log_file is null for foreground runs" not in content, (
            "docs/guides/LOOPS_GUIDE.md must not claim log_file is null for foreground runs"
        )

    def test_accurate_both_run_modes_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "foreground and background runs" in content, (
            "docs/guides/LOOPS_GUIDE.md must state that both foreground and background runs write a log file"
        )

    def test_tips_foreground_log_bullet_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "Foreground runs always write a log file" in content, (
            "docs/guides/LOOPS_GUIDE.md Tips section must have a bullet for always-on foreground log capture"
        )

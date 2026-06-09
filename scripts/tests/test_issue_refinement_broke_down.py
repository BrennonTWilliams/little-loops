"""Regression tests for BUG-2034: issue-refinement check_broke_down gate.

Verifies that after run_refine_to_ready completes, the check_broke_down state
routes to handle_failure (skip-list) when the child wrote refine-broke-down=1,
and routes to check_commit when the signal is absent or zero.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


def _check_broke_down_script(run_dir: str) -> str:
    """Shell body of check_broke_down with context.run_dir substituted."""
    return f"""
    BROKE="{run_dir}/refine-broke-down"
    if [ -f "$BROKE" ] && grep -q '1' "$BROKE" 2>/dev/null; then exit 0; fi
    exit 1
    """


class TestCheckBrokeDown:
    """check_broke_down gate routes correctly based on refine-broke-down signal."""

    def test_broke_down_signal_exits_zero(self, tmp_path: Path) -> None:
        """exit 0 (→ handle_failure) when refine-broke-down contains 1."""
        run_dir = tmp_path / ".loops" / "runs" / "issue-refinement-20260608T000000"
        run_dir.mkdir(parents=True)
        (run_dir / "refine-broke-down").write_text("1")

        result = _bash(_check_broke_down_script(str(run_dir)), tmp_path)

        assert result.returncode == 0, "broke-down=1 should exit 0 → route to handle_failure"

    def test_no_signal_file_exits_nonzero(self, tmp_path: Path) -> None:
        """exit 1 (→ check_commit) when refine-broke-down is absent."""
        run_dir = tmp_path / ".loops" / "runs" / "issue-refinement-20260608T000000"
        run_dir.mkdir(parents=True)
        # no refine-broke-down file written

        result = _bash(_check_broke_down_script(str(run_dir)), tmp_path)

        assert result.returncode != 0, "absent signal should exit 1 → route to check_commit"

    def test_zero_signal_exits_nonzero(self, tmp_path: Path) -> None:
        """exit 1 (→ check_commit) when refine-broke-down contains 0 (genuine success)."""
        run_dir = tmp_path / ".loops" / "runs" / "issue-refinement-20260608T000000"
        run_dir.mkdir(parents=True)
        (run_dir / "refine-broke-down").write_text("0")

        result = _bash(_check_broke_down_script(str(run_dir)), tmp_path)

        assert result.returncode != 0, "broke-down=0 should exit 1 → route to check_commit"

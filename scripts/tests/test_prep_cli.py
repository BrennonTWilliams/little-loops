"""ENH-3630: ``ll-issues prep`` registration, help surface and failure paths.

Covers the CLI wiring (add_prep_parser/cmd_prep registered in main_issues, the
epilog line, --help listing all four subcommands) and in-process failure paths for
the writers -- complementing the decide()/writer tests in test_preparation_policy*.py.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent


def _cli() -> list[str]:
    if shutil.which("ll-issues") is not None:
        return ["ll-issues"]
    return [sys.executable, "-m", "little_loops.cli"]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for kind in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / kind).mkdir(parents=True, exist_ok=True)
    return tmp_path


class TestPrepHelpSurface:
    def test_subcommand_in_help(self, project: Path) -> None:
        result = subprocess.run(
            [*_cli(), "--help"], cwd=str(project), capture_output=True, text=True, timeout=30
        )
        assert "prep" in result.stdout
        assert "Sub-commands:" in result.stdout

    def test_prep_help_lists_all_four_subcommands(self, project: Path) -> None:
        result = subprocess.run(
            [*_cli(), "prep", "--help"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        for name in ("step", "record", "apply", "explain"):
            assert name in result.stdout

    def test_prep_apply_help_lists_rate_limited_flag(self, project: Path) -> None:
        result = subprocess.run(
            [*_cli(), "prep", "apply", "--help"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "--rate-limited" in result.stdout

    def test_prep_step_help_lists_advise_go_no_go_flag(self, project: Path) -> None:
        """ENH-3590: opt-in veto consult flag, threaded into decide()."""
        result = subprocess.run(
            [*_cli(), "prep", "step", "--help"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "--advise-go-no-go" in result.stdout


class TestPrepCliSurfaceIndex:
    def test_cli_surface_recognizes_prep(self) -> None:
        """``cli_surface_accepts`` scrapes one level (top-level --help); ``prep``'s
        own sub-subcommand flags (e.g. ``apply --rate-limited``) aren't in its model.
        """
        from little_loops.issues.cli_surface import build_cli_surface_index, cli_surface_accepts

        idx = build_cli_surface_index()
        assert cli_surface_accepts(idx, "ll-issues", "prep") is True


class TestPrepFailurePaths:
    def test_unresolvable_issue_precondition_raises(self, tmp_path: Path) -> None:
        from little_loops.config import BRConfig
        from little_loops.preparation_policy import _run_preconditions

        (tmp_path / ".issues" / "enhancements").mkdir(parents=True, exist_ok=True)
        config = BRConfig(tmp_path)
        with pytest.raises(RuntimeError, match="not found"):
            _run_preconditions(config, "ENH-99999", tmp_path / "run", ["clear_scores"])

    def test_invalid_reason_status_pair_raises_before_writing(self, tmp_path: Path) -> None:
        from little_loops.config import BRConfig
        from little_loops.preparation_policy import _set_status_checked

        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True, exist_ok=True)
        path = issues_dir / "P3-ENH-1-test.md"
        path.write_text("---\nid: ENH-1\nstatus: open\npriority: P3\n---\n# T\n")
        config = BRConfig(tmp_path)
        with pytest.raises(RuntimeError, match="reason"):
            # "already_fixed" is a closure code, invalid on a "deferred" transition.
            _set_status_checked(config, path, "ENH-1", "deferred", reason="already_fixed")
        assert "status: deferred" not in path.read_text()

    def test_cmd_prep_returns_2_for_unknown_subcommand(self, project: Path) -> None:
        import argparse

        from little_loops.config import BRConfig
        from little_loops.preparation_policy import cmd_prep

        args = argparse.Namespace(prep_command="bogus", issue_id="ENH-1", run_dir=str(project))
        assert cmd_prep(BRConfig(project), args) == 2

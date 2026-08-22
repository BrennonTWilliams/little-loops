"""Family-wide guard test (BUG-3294): every `ll-issues check-*` probe must exit 2 —
not 1 — when the issue ID cannot be resolved, so a newly added probe cannot
reintroduce the not-found/genuine-negative conflation this issue fixes.

The family is glob-derived from `cli/issues/check_*.py`, not hand-maintained, so
an eighth probe is automatically covered (or automatically fails this test until
its exit code is added to the code and it is exempted here for a stated reason).
Only per-probe extra argv is hand-maintained: `check-flag` requires a trailing
field name; the rest take a bare issue ID.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_CHECK_MODULES_DIR = Path(__file__).parent.parent / "little_loops" / "cli" / "issues"

# Hand-maintained: extra positional argv each subcommand needs beyond the
# unresolvable issue ID itself. Everything else in the family takes a bare ID.
_EXTRA_ARGV: dict[str, list[str]] = {
    "check-flag": ["decision_needed"],
}


def _family_subcommands() -> list[str]:
    return sorted(
        p.stem.replace("_", "-")
        for p in _CHECK_MODULES_DIR.glob("check_*.py")
        if p.stem != "check_unresolved_decisions"  # BUG-3278: not yet landed
    )


def _cli() -> list[str]:
    if shutil.which("ll-issues") is not None:
        return ["ll-issues"]
    import sys

    return [sys.executable, "-m", "little_loops.cli"]


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    issues = tmp_path / ".issues"
    for kind in ("bugs", "features", "enhancements", "epics"):
        (issues / kind).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _invoke(project_root: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    return subprocess.run(
        [*_cli(), *args],
        cwd=str(project_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestCheckFamilyNotFoundExitsTwo:
    """Every check-* probe exits 2 (not 1) for an unresolvable issue ID."""

    @pytest.mark.parametrize("subcommand", _family_subcommands())
    def test_unresolvable_issue_exits_two(self, temp_project_dir: Path, subcommand: str) -> None:
        extra = _EXTRA_ARGV.get(subcommand, [])
        result = _invoke(temp_project_dir, subcommand, "FEAT-9999", *extra)
        assert result.returncode == 2, (
            f"{subcommand} must exit 2 for an unresolvable issue ID (BUG-3294), "
            f"got {result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_family_has_seven_members(self) -> None:
        """Guards against silent family shrinkage (a probe renamed/removed
        without updating this test's assumptions)."""
        assert len(_family_subcommands()) == 7, _family_subcommands()

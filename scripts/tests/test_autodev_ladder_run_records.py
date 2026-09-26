"""Tests for ENH-3615: autodev ladder stop rows also write a ``prepare-issue`` run record.

Each stop state's real shell action runs under bash against a throwaway project and
the real ``ll-issues`` CLI, so the assertions cover the record token the state
writes, that the ``autodev-skipped.txt`` ledger rows are unchanged, and the
``refine-broke-down`` reset that keeps the records from reading as ``DECOMPOSED``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

AUTODEV_LOOP_PATH = Path(__file__).parent.parent / "little_loops" / "loops" / "autodev.yaml"
ISSUE_ID = "ENH-9001"


@pytest.fixture(scope="module")
def states() -> dict[str, Any]:
    return yaml.safe_load(AUTODEV_LOOP_PATH.read_text())["states"]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".ll").mkdir(parents=True)
    (root / ".ll" / "ll-config.json").write_text("{}")
    (root / ".issues" / "enhancements").mkdir(parents=True)
    (root / "run").mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def _write_issue(project: Path, *, status: str = "open", **fm: Any) -> None:
    fields = {"confidence_score": 10, "outcome_confidence": 10, **fm}
    front = "\n".join(f"{k}: {v}" for k, v in fields.items())
    (project / ".issues" / "enhancements" / f"P3-{ISSUE_ID}-demo.md").write_text(
        f"---\nid: {ISSUE_ID}\ntype: ENH\ntitle: demo\npriority: P3\nstatus: {status}\n"
        f"{front}\n---\n\n# {ISSUE_ID}: demo\n\n## Summary\n\nx\n"
    )


def _run(states: dict[str, Any], name: str, project: Path) -> subprocess.CompletedProcess[str]:
    subs = {
        "context.run_dir": str(project / "run"),
        "captured.input.output:shell": ISSUE_ID,
        "captured.input.output": ISSUE_ID,
        "context.readiness_threshold:shell": "85",
        "context.outcome_threshold:shell": "65",
    }
    action = re.sub(r"\$\{([^}]+)\}", lambda m: subs[m.group(1)], states[name]["action"])
    return subprocess.run(
        ["bash", "-c", action], capture_output=True, text=True, check=False, cwd=project
    )


def _token(project: Path) -> str:
    result = subprocess.run(
        [
            "ll-issues",
            "run-record",
            "read",
            ISSUE_ID,
            "--run-dir",
            str(project / "run"),
            "--writer",
            "prepare-issue",
            "--format",
            "token",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=project,
    )
    return result.stdout.strip()


def _ledger(project: Path) -> str:
    path = project / "run" / "autodev-skipped.txt"
    return path.read_text() if path.exists() else ""


def _touch(project: Path, name: str) -> None:
    (project / "run" / name).write_text("")


def _arm_low_readiness(project: Path) -> None:
    _touch(project, "autodev-pre-deferral-remedy-fired")


def _arm_stagnation(project: Path) -> None:
    (project / "run" / "autodev-repair-cycle-count.txt").write_text("2")
    (project / "run" / "autodev-pre-readiness.txt").write_text("50")


def _arm_design_gate(project: Path) -> None:
    _touch(project, f"autodev-design-gate-failed-{ISSUE_ID}")
    _touch(project, f"autodev-design-remedy-attempted-{ISSUE_ID}")


# (state, issue frontmatter, arm, ledger reason, token)
STOP_ROWS = {
    "recheck-low_readiness": (
        "recheck_after_size_review",
        {},
        _arm_low_readiness,
        "low_readiness",
        "DEFERRED:gate_unmet",
    ),
    "recheck-readiness_stagnated": (
        "recheck_after_size_review",
        {},
        _arm_stagnation,
        "readiness_stagnated",
        "DEFERRED:gate_unmet",
    ),
    "recheck-design_gate_failed": (
        "recheck_after_size_review",
        {},
        _arm_design_gate,
        "design_gate_failed",
        "DEFERRED:gate_unmet",
    ),
    "recheck-decision_unresolved": (
        "recheck_after_size_review",
        {"decision_needed": "true"},
        _arm_low_readiness,
        "decision_unresolved",
        "BLOCKED:decision_unresolved",
    ),
    "regate-oversized_atomic": (
        "regate_after_atomic_remediation",
        {"confidence_score": 90, "outcome_confidence": 10},
        lambda project: None,
        "oversized_atomic",
        "DEFERRED:gate_unmet",
    ),
    "regate-design_gate_failed": (
        "regate_after_atomic_remediation",
        {"confidence_score": 90, "outcome_confidence": 10},
        _arm_design_gate,
        "design_gate_failed",
        "DEFERRED:gate_unmet",
    ),
    "reentry-decision_unresolved": (
        "record_reentry_exhausted",
        {},
        lambda project: None,
        "decision_unresolved",
        "BLOCKED:decision_unresolved",
    ),
}


class TestStopRowRunRecords:
    @pytest.mark.parametrize("row", STOP_ROWS)
    def test_stop_row_writes_matching_record_and_unchanged_ledger(
        self, states: dict[str, Any], project: Path, row: str
    ) -> None:
        state, fm, arm, reason, token = STOP_ROWS[row]
        _write_issue(project, **fm)
        arm(project)
        _run(states, state, project)
        assert _ledger(project) == f"{ISSUE_ID}  {reason}\n"
        assert _token(project) == token

    @pytest.mark.parametrize("status", ["done", "cancelled"])
    def test_reentry_exhausted_on_resolved_issue_writes_ledger_row_and_no_record(
        self, states: dict[str, Any], project: Path, status: str
    ) -> None:
        _write_issue(project, status=status)
        _run(states, "record_reentry_exhausted", project)
        assert _ledger(project) == f"{ISSUE_ID}  decision_unresolved\n"
        assert _token(project) in ("", "MISSING")

    @pytest.mark.parametrize(
        "state", ["recheck_after_size_review", "regate_after_atomic_remediation"]
    )
    def test_resolved_issue_leaves_ladder_without_record(
        self, states: dict[str, Any], project: Path, state: str
    ) -> None:
        _write_issue(project, status="done")
        _run(states, state, project)
        assert _ledger(project) == f"{ISSUE_ID}  resolved_by_subloop\n"
        assert _token(project) in ("", "MISSING")


class TestBrokeDownTrap:
    """A stale ``refine-broke-down`` flag must not turn ladder stops into DECOMPOSED."""

    def test_copy_broke_down_resets_flag_after_copying(
        self, states: dict[str, Any], project: Path
    ) -> None:
        run = project / "run"
        (run / "refine-broke-down").write_text("1")
        _run(states, "copy_broke_down", project)
        assert (run / "autodev-broke-down").read_text() == "1"
        assert (run / "refine-broke-down").read_text() == "0"

    def test_stop_after_breakdown_flag_records_deferred_not_decomposed(
        self, states: dict[str, Any], project: Path
    ) -> None:
        """Flag at 1 with no usable record (an inner breakdown with no children and an
        unresolved parent, or route_refine_success failing open on MISSING): the pass
        still passes copy_broke_down, so the later stop records DEFERRED."""
        _write_issue(project)
        (project / "run" / "refine-broke-down").write_text("1")
        _run(states, "copy_broke_down", project)
        _arm_design_gate(project)
        _run(states, "recheck_after_size_review", project)
        assert _token(project) == "DEFERRED:gate_unmet"

    def test_unreset_flag_would_decompose(self, states: dict[str, Any], project: Path) -> None:
        """Control: without copy_broke_down's reset the same stop reads DECOMPOSED."""
        _write_issue(project)
        (project / "run" / "refine-broke-down").write_text("1")
        _arm_design_gate(project)
        _run(states, "recheck_after_size_review", project)
        assert _token(project) == "DECOMPOSED"


class TestReopenWaived:
    def test_removes_oversized_atomic_row_and_clears_record(
        self, states: dict[str, Any], project: Path
    ) -> None:
        _write_issue(project, confidence_score=90, outcome_confidence=10)
        _run(states, "regate_after_atomic_remediation", project)
        assert _ledger(project) == f"{ISSUE_ID}  oversized_atomic\n"
        assert _token(project) == "DEFERRED:gate_unmet"
        result = _run(states, "reopen_waived", project)
        assert result.returncode == 0, result.stderr
        assert ISSUE_ID not in _ledger(project)
        assert _token(project) in ("", "MISSING")

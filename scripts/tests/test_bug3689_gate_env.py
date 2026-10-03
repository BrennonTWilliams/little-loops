"""BUG-3689: the suite is hermetic against inherited LL_PYTHON / COLUMNS / LINES.

An FSM-driven quality gate exports ``LL_PYTHON`` and may inherit a wide terminal; tests
must not depend on either. ``conftest.py`` scrubs ``LL_PYTHON`` and pins the terminal
to 80x24 per test (a test overrides by ``monkeypatch.setenv`` in its body).
"""

from __future__ import annotations

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from little_loops.worktree_utils import HERMETIC_ENV_VARS

TESTS = "scripts/tests"

# The 11 tests that failed under the gate's inherited env (BUG-3689 Current Behavior).
ENV_SENSITIVE_NODE_IDS = (
    f"{TESTS}/test_builtin_loops.py::TestAutoRefineAndImplementLoop"
    "::test_recheck_set_folds_back_abandoned_residual",
    f"{TESTS}/test_ll_loop_display.py::TestPrintExecutionPlan::test_long_action_truncated",
    f"{TESTS}/test_ll_loop_display.py::TestAdaptiveLayoutTopologies"
    "::test_terminal_width_no_overflow",
    f"{TESTS}/test_ll_loop_display.py::TestAdaptiveLayoutTopologies"
    "::test_fanout_merged_label_truncated_with_ellipsis",
    f"{TESTS}/test_snapshot_loop_layout.py::TestFSMDiagramSnapshot::test_linear_two_state_fsm",
    f"{TESTS}/test_snapshot_loop_layout.py::TestFSMDiagramSnapshot::test_branching_three_state_fsm",
    f"{TESTS}/test_snapshot_loop_layout.py::TestFSMDiagramSnapshot::test_linear_fsm_with_highlight",
    f"{TESTS}/test_snapshot_loop_layout.py::TestFSMDiagramSnapshot::test_suppress_labels_mode",
    f"{TESTS}/test_show.py::TestRenderCard::test_long_unbreakable_word_truncated_not_extended",
    f"{TESTS}/test_cli.py::TestSprintShowDependencyVisualization"
    "::test_render_execution_plan_title_truncation",
    f"{TESTS}/test_issues_cli.py::TestIssuesCLIShow::test_show_with_long_summary",
)


def test_hermetic_vars_are_the_bounded_set() -> None:
    assert HERMETIC_ENV_VARS == ("LL_PYTHON", "COLUMNS", "LINES")


class TestFixtureDefaults:
    def test_terminal_pinned_and_ll_python_absent(self) -> None:
        assert os.environ.get("COLUMNS") == "80"
        assert os.environ.get("LINES") == "24"
        assert "LL_PYTHON" not in os.environ

    def test_in_body_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLUMNS", "150")
        monkeypatch.setenv("LL_PYTHON", "/x/python")
        assert os.environ["COLUMNS"] == "150"
        assert os.environ["LL_PYTHON"] == "/x/python"

    def test_raw_write_is_restored_for_next_test(self) -> None:
        os.environ["LL_PYTHON"] = "/leaky"
        os.environ["COLUMNS"] = "200"

    def test_raw_write_did_not_leak(self) -> None:
        # Runs after the previous test in file order; both are serial within a module.
        assert "LL_PYTHON" not in os.environ
        assert os.environ.get("COLUMNS") == "80"


def test_suite_passes_with_ambient_gate_env(tmp_path: Path) -> None:
    """The 11 originally failing tests pass with polluted interpreter/width/height."""
    repo_root = Path(__file__).resolve().parents[2]
    junit = tmp_path / "junit.xml"
    env = {
        k: v
        for k, v in os.environ.items()
        if k != "PYTEST_ADDOPTS" and not k.startswith("PYTEST_XDIST")
    }
    env.update({"LL_PYTHON": sys.executable, "COLUMNS": "150", "LINES": "60"})
    # Pass the ambient values as the *inherited* env: conftest must neutralise them.
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-n",
            "0",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
            *ENV_SENSITIVE_NODE_IDS,
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-3000:]
    suite = ET.parse(junit).getroot()
    cases = list(suite.iter("testcase"))
    assert len(cases) == len(ENV_SENSITIVE_NODE_IDS)
    assert not [c for c in cases if c.find("skipped") is not None]
    assert not [c for c in cases if c.find("failure") is not None or c.find("error") is not None]

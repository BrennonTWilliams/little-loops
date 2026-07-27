"""Tests for little_loops.learning_tests.gate module (ENH-2405)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from little_loops.fsm.persistence import LoopState
from little_loops.learning_tests.gate import run_learning_gate_for_issue


class TestRunLearningGateForIssueTargetsThreading:
    """ENH-2405: the gate must thread registered targets through as targets_csv
    instead of discarding them, so proof-first-task can prove the registered
    list directly rather than re-extracting via assumption-firewall."""

    def _ok_result(self) -> MagicMock:
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        mock.stderr = ""
        return mock

    def test_targets_none_omits_targets_csv_context(self, tmp_path: Path) -> None:
        """Default (targets=None) must not append targets_csv (JIT fallback unchanged)."""
        issue_path = tmp_path / "ENH-1.md"
        issue_path.write_text("---\nid: ENH-1\n---\n")

        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=self._ok_result()
        ) as mock_sub:
            run_learning_gate_for_issue(issue_path, cwd=tmp_path)

        cmd = mock_sub.call_args[0][0]
        assert not any("targets_csv" in part for part in cmd)

    def test_targets_provided_invokes_ready_to_implement_gate_directly(
        self, tmp_path: Path
    ) -> None:
        """ENH-2834: a populated targets list must invoke ready-to-implement-gate
        directly (not proof-first-task) with --context targets=<csv>."""
        issue_path = tmp_path / "ENH-2.md"
        issue_path.write_text("---\nid: ENH-2\n---\n")

        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=self._ok_result()
        ) as mock_sub:
            run_learning_gate_for_issue(issue_path, cwd=tmp_path, targets=["stripe"])

        cmd = mock_sub.call_args[0][0]
        assert cmd[2] == "ready-to-implement-gate"
        assert "targets=stripe" in " ".join(cmd)

    def test_multiple_targets_joined_by_comma(self, tmp_path: Path) -> None:
        issue_path = tmp_path / "ENH-3.md"
        issue_path.write_text("---\nid: ENH-3\n---\n")

        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=self._ok_result()
        ) as mock_sub:
            run_learning_gate_for_issue(issue_path, cwd=tmp_path, targets=["stripe", "anthropic"])

        cmd = mock_sub.call_args[0][0]
        assert "targets=stripe,anthropic" in " ".join(cmd)

    def test_empty_targets_list_omits_targets_csv_context(self, tmp_path: Path) -> None:
        """An empty (but non-None) list must behave like None — no targets_csv forwarded."""
        issue_path = tmp_path / "ENH-4.md"
        issue_path.write_text("---\nid: ENH-4\n---\n")

        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=self._ok_result()
        ) as mock_sub:
            run_learning_gate_for_issue(issue_path, cwd=tmp_path, targets=[])

        cmd = mock_sub.call_args[0][0]
        assert not any("targets_csv" in part for part in cmd)

    def test_skip_short_circuits_before_targets_are_consulted(self, tmp_path: Path) -> None:
        """skip=True must still short-circuit regardless of targets."""
        issue_path = tmp_path / "ENH-5.md"
        issue_path.write_text("---\nid: ENH-5\n---\n")

        with patch("little_loops.learning_tests.gate.subprocess.run") as mock_sub:
            verdict = run_learning_gate_for_issue(
                issue_path, cwd=tmp_path, skip=True, targets=["stripe"]
            )

        assert verdict == "skipped"
        mock_sub.assert_not_called()


def _make_loop_state(current_state: str) -> LoopState:
    return LoopState(
        loop_name="proof-first-task",
        current_state=current_state,
        iteration=1,
        captured={},
        prev_result=None,
        last_result=None,
        started_at="2026-07-26T12:00:00+00:00",
        updated_at="",
        status="completed",
    )


class TestRunLearningGateForIssueTerminalDiscrimination:
    """BUG-2833: the exit code alone cannot distinguish proof-first-task's two
    failure terminals (blocked vs impl_failed), so the gate must consult the
    archived LoopState to discriminate."""

    def _failed_result(self) -> MagicMock:
        from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE

        mock = MagicMock()
        mock.returncode = FAILURE_TERMINAL_EXIT_CODE
        mock.stdout = ""
        mock.stderr = ""
        return mock

    def test_blocked_terminal_yields_blocked_verdict(self, tmp_path: Path) -> None:
        issue_path = tmp_path / "ENH-6.md"
        issue_path.write_text("---\nid: ENH-6\n---\n")

        with (
            patch(
                "little_loops.learning_tests.gate.subprocess.run",
                return_value=self._failed_result(),
            ),
            patch(
                "little_loops.fsm.persistence.list_run_history",
                return_value=[_make_loop_state("blocked")],
            ),
        ):
            verdict = run_learning_gate_for_issue(issue_path, cwd=tmp_path)

        assert verdict == "blocked"

    def test_impl_failed_terminal_yields_distinct_verdict(self, tmp_path: Path) -> None:
        issue_path = tmp_path / "ENH-7.md"
        issue_path.write_text("---\nid: ENH-7\n---\n")

        with (
            patch(
                "little_loops.learning_tests.gate.subprocess.run",
                return_value=self._failed_result(),
            ),
            patch(
                "little_loops.fsm.persistence.list_run_history",
                return_value=[_make_loop_state("impl_failed")],
            ),
        ):
            verdict = run_learning_gate_for_issue(issue_path, cwd=tmp_path)

        assert verdict == "impl_failed"
        assert verdict != "blocked"

    def test_missing_history_defaults_to_impl_failed(self, tmp_path: Path) -> None:
        """No archived history to discriminate from — fail safe to the
        generic-failure path rather than mislabeling as a gate block."""
        issue_path = tmp_path / "ENH-8.md"
        issue_path.write_text("---\nid: ENH-8\n---\n")

        with (
            patch(
                "little_loops.learning_tests.gate.subprocess.run",
                return_value=self._failed_result(),
            ),
            patch("little_loops.fsm.persistence.list_run_history", return_value=[]),
        ):
            verdict = run_learning_gate_for_issue(issue_path, cwd=tmp_path)

        assert verdict == "impl_failed"


class TestRunLearningGateForIssueDirectInvocation:
    """ENH-2834: with resolved targets, the gate proves via ready-to-implement-gate
    directly and never spawns proof-first-task's impl loop — a proven-registry
    issue whose impl chain is broken must still pass (BUG-2831 regression)."""

    def _ok_result(self) -> MagicMock:
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        mock.stderr = ""
        return mock

    def _failed_result(self) -> MagicMock:
        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = ""
        mock.stderr = ""
        return mock

    def _blocked_result(self) -> MagicMock:
        from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE

        mock = MagicMock()
        mock.returncode = FAILURE_TERMINAL_EXIT_CODE
        mock.stdout = ""
        mock.stderr = ""
        return mock

    def test_proven_target_with_broken_impl_chain_still_passes(self, tmp_path: Path) -> None:
        """BUG-2831 scenario: registry target is proven (exit 0), but the
        general-task impl loop the old proof-first-task path would have
        chained into is broken/unreachable. The gate must still pass, and
        must never consult list_run_history — there is no impl_failed
        terminal on this path to discriminate against."""
        issue_path = tmp_path / "ENH-9.md"
        issue_path.write_text("---\nid: ENH-9\n---\n")

        with (
            patch(
                "little_loops.learning_tests.gate.subprocess.run",
                return_value=self._ok_result(),
            ),
            patch("little_loops.fsm.persistence.list_run_history") as mock_history,
        ):
            verdict = run_learning_gate_for_issue(issue_path, cwd=tmp_path, targets=["stripe"])

        assert verdict == "passed"
        mock_history.assert_not_called()

    def test_infra_failure_yields_impl_failed_not_blocked(self, tmp_path: Path) -> None:
        """BUG-2864: a non-FAILURE_TERMINAL_EXIT_CODE exit (e.g. a scope-lock
        conflict) means the loop never reached a terminal at all, so it must
        not be misdiagnosed as a genuine refuted-target "blocked" verdict."""
        issue_path = tmp_path / "ENH-10.md"
        issue_path.write_text("---\nid: ENH-10\n---\n")

        with (
            patch(
                "little_loops.learning_tests.gate.subprocess.run",
                return_value=self._failed_result(),
            ),
            patch("little_loops.fsm.persistence.list_run_history") as mock_history,
        ):
            verdict = run_learning_gate_for_issue(issue_path, cwd=tmp_path, targets=["stripe"])

        assert verdict == "impl_failed"
        assert verdict != "blocked"
        mock_history.assert_not_called()

    def test_refuted_target_terminal_yields_blocked_without_history_lookup(
        self, tmp_path: Path
    ) -> None:
        issue_path = tmp_path / "ENH-11.md"
        issue_path.write_text("---\nid: ENH-11\n---\n")

        with (
            patch(
                "little_loops.learning_tests.gate.subprocess.run",
                return_value=self._blocked_result(),
            ),
            patch("little_loops.fsm.persistence.list_run_history") as mock_history,
        ):
            verdict = run_learning_gate_for_issue(issue_path, cwd=tmp_path, targets=["stripe"])

        assert verdict == "blocked"
        mock_history.assert_not_called()

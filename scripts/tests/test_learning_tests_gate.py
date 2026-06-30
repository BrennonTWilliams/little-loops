"""Tests for little_loops.learning_tests.gate module (ENH-2405)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_targets_provided_forwards_targets_csv_context(self, tmp_path: Path) -> None:
        """A populated targets list must be forwarded as --context targets_csv=<csv>."""
        issue_path = tmp_path / "ENH-2.md"
        issue_path.write_text("---\nid: ENH-2\n---\n")

        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=self._ok_result()
        ) as mock_sub:
            run_learning_gate_for_issue(issue_path, cwd=tmp_path, targets=["stripe"])

        cmd = mock_sub.call_args[0][0]
        assert "targets_csv=stripe" in " ".join(cmd)

    def test_multiple_targets_joined_by_comma(self, tmp_path: Path) -> None:
        issue_path = tmp_path / "ENH-3.md"
        issue_path.write_text("---\nid: ENH-3\n---\n")

        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=self._ok_result()
        ) as mock_sub:
            run_learning_gate_for_issue(issue_path, cwd=tmp_path, targets=["stripe", "anthropic"])

        cmd = mock_sub.call_args[0][0]
        assert "targets_csv=stripe,anthropic" in " ".join(cmd)

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

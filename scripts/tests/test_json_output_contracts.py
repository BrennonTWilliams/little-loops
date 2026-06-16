"""Snapshot / contract tests for --json CLI output surfaces consumed by Hermes.

These tests assert that the required fields exist and have the expected types in
the JSON output of:
  - ll-loop list --json
  - ll-loop status --json
  - ll-issues list --json

Removing or renaming a field in these outputs is a breaking change that would
silently break the Hermes integration. These tests fail immediately on such changes.

New optional fields may be added without modifying these tests (additive changes
are non-breaking per the stability policy in docs/reference/json-output-contracts.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _runnable(spec: str) -> str:
    """Wrap a partial YAML spec in a minimal runnable FSM skeleton."""
    return (
        spec
        + "\ninitial: done\nstates:\n  done:\n    terminal: true\n"
    )


# ---------------------------------------------------------------------------
# ll-loop list --json contract
# ---------------------------------------------------------------------------


class TestLoopListJsonContract:
    """Contract: ll-loop list --json must include required fields per docs/reference/json-output-contracts.md."""

    REQUIRED_FIELDS = {"name", "path", "category", "labels", "visibility", "description"}

    def _cmd_list_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            _runnable("name: my-loop\ndescription: Test loop\nvisibility: public\n")
        )

        args = argparse.Namespace(
            running=False, status=None, json=True,
            category=None, label=None, all=True,
            internal=False, examples=False,
        )
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)
        assert result == 0
        return json.loads(capsys.readouterr().out)

    def test_required_fields_present(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Every loop object must include all required fields."""
        items = self._cmd_list_json(tmp_path, capsys)
        assert items, "expected at least one loop in output"
        for item in items:
            for field in self.REQUIRED_FIELDS:
                assert field in item, f"required field '{field}' missing from ll-loop list --json output"

    def test_name_is_string(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """'name' field must be a string."""
        items = self._cmd_list_json(tmp_path, capsys)
        for item in items:
            assert isinstance(item["name"], str)

    def test_labels_is_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """'labels' field must be a list."""
        items = self._cmd_list_json(tmp_path, capsys)
        for item in items:
            assert isinstance(item["labels"], list)

    def test_visibility_is_known_tier(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """'visibility' must be one of the documented tiers."""
        items = self._cmd_list_json(tmp_path, capsys)
        for item in items:
            assert item["visibility"] in ("public", "internal", "example"), (
                f"unexpected visibility value: {item['visibility']!r}"
            )

    def test_built_in_flag_only_for_builtin_loops(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """'built_in' key appears only for built-in loops and has value True."""
        items = self._cmd_list_json(tmp_path, capsys)
        for item in items:
            if "built_in" in item:
                assert item["built_in"] is True

    def test_full_shape_with_builtin_loop(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A built-in loop result includes built_in=True and all required fields."""
        from little_loops.cli.loop.info import cmd_list
        from little_loops.cli.loop._helpers import get_builtin_loops_dir

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        args = argparse.Namespace(
            running=False, status=None, json=True,
            category=None, label=None, all=True,
            internal=False, examples=False,
        )
        result = cmd_list(args, loops_dir)
        assert result == 0
        items = json.loads(capsys.readouterr().out)
        builtin_items = [i for i in items if i.get("built_in")]
        if builtin_items:
            for item in builtin_items:
                for field in self.REQUIRED_FIELDS:
                    assert field in item


# ---------------------------------------------------------------------------
# ll-loop status --json contract
# ---------------------------------------------------------------------------


class TestLoopStatusJsonContract:
    """Contract: ll-loop status --json must include required fields per docs/reference/json-output-contracts.md."""

    REQUIRED_FIELDS = {
        "loop_name",
        "current_state",
        "iteration",
        "captured",
        "prev_result",
        "last_result",
        "started_at",
        "updated_at",
        "status",
        "accumulated_ms",
    }

    def _make_loop_state(self, **overrides: Any) -> Any:
        from little_loops.fsm.persistence import LoopState

        defaults: dict[str, Any] = {
            "loop_name": "test-loop",
            "current_state": "check",
            "iteration": 2,
            "captured": {},
            "prev_result": None,
            "last_result": None,
            "started_at": "2026-06-16T12:00:00+00:00",
            "updated_at": "2026-06-16T12:05:00+00:00",
            "status": "running",
            "accumulated_ms": 300_000,
        }
        defaults.update(overrides)
        return LoopState(**defaults)

    def test_required_fields_present(self) -> None:
        """LoopState.to_dict() must include all required fields."""
        state = self._make_loop_state()
        d = state.to_dict()
        for field in self.REQUIRED_FIELDS:
            assert field in d, f"required field '{field}' missing from ll-loop status --json output"

    def test_status_is_known_value(self) -> None:
        """'status' must be one of the documented values."""
        known = {"running", "completed", "failed", "interrupted", "awaiting_continuation", "timed_out"}
        for status_val in known:
            state = self._make_loop_state(status=status_val)
            assert state.to_dict()["status"] == status_val

    def test_loop_name_is_string(self) -> None:
        """'loop_name' must be a string."""
        state = self._make_loop_state()
        assert isinstance(state.to_dict()["loop_name"], str)

    def test_iteration_is_int(self) -> None:
        """'iteration' must be an integer."""
        state = self._make_loop_state()
        assert isinstance(state.to_dict()["iteration"], int)

    def test_accumulated_ms_is_int(self) -> None:
        """'accumulated_ms' must be an integer."""
        state = self._make_loop_state()
        assert isinstance(state.to_dict()["accumulated_ms"], int)

    def test_continuation_prompt_present_when_awaiting(self) -> None:
        """'continuation_prompt' key is present in to_dict() when status is awaiting_continuation."""
        state = self._make_loop_state(
            status="awaiting_continuation",
            continuation_prompt="Resume from step 3",
        )
        d = state.to_dict()
        assert "continuation_prompt" in d
        assert d["continuation_prompt"] == "Resume from step 3"

    def test_json_output_via_cmd_list_running(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ll-loop list --running --json emits LoopState JSON with required fields."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        state = self._make_loop_state()

        args = argparse.Namespace(running=True, status=None, json=True)
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=[state]):
            result = cmd_list(args, loops_dir)

        assert result == 0
        items = json.loads(capsys.readouterr().out)
        assert len(items) == 1
        for field in self.REQUIRED_FIELDS:
            assert field in items[0], f"required field '{field}' missing from running-loop JSON output"


# ---------------------------------------------------------------------------
# ll-issues list --json contract
# ---------------------------------------------------------------------------


class TestIssuesListJsonContract:
    """Contract: ll-issues list --json must include required fields per docs/reference/json-output-contracts.md."""

    REQUIRED_FIELDS = {
        "id",
        "priority",
        "type",
        "title",
        "path",
        "status",
        "discovered_date",
        "parent",
        "labels",
        "milestone",
    }

    def _write_issue(self, issues_dir: Path, filename: str, content: str) -> None:
        issues_dir.mkdir(parents=True, exist_ok=True)
        (issues_dir / filename).write_text(content)

    def test_required_fields_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Every issue object in ll-issues list --json must have all required fields."""
        issues_dir = tmp_path / ".issues" / "enhancements"
        self._write_issue(
            issues_dir,
            "P2-ENH-0001-test-issue.md",
            "---\nid: ENH-0001\ntype: ENH\npriority: P2\nstatus: open\n---\n\n# Test Issue\n",
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-issues", "list", "--json"]):
            from little_loops.cli.issues import main_issues

            result = main_issues()

        assert result == 0
        items = json.loads(capsys.readouterr().out)
        assert items, "expected at least one issue in output"
        for item in items:
            for field in self.REQUIRED_FIELDS:
                assert field in item, f"required field '{field}' missing from ll-issues list --json output"

    def test_id_is_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """'id' field must be a string."""
        issues_dir = tmp_path / ".issues" / "enhancements"
        self._write_issue(
            issues_dir,
            "P2-ENH-0001-test.md",
            "---\nid: ENH-0001\ntype: ENH\npriority: P2\nstatus: open\n---\n\n# T\n",
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-issues", "list", "--json"]):
            from little_loops.cli.issues import main_issues

            main_issues()
        items = json.loads(capsys.readouterr().out)
        for item in items:
            assert isinstance(item["id"], str)

    def test_labels_is_list(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """'labels' field must be a list (empty list when no labels set)."""
        issues_dir = tmp_path / ".issues" / "enhancements"
        self._write_issue(
            issues_dir,
            "P2-ENH-0001-test.md",
            "---\nid: ENH-0001\ntype: ENH\npriority: P2\nstatus: open\n---\n\n# T\n",
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-issues", "list", "--json"]):
            from little_loops.cli.issues import main_issues

            main_issues()
        items = json.loads(capsys.readouterr().out)
        for item in items:
            assert isinstance(item["labels"], list)

    def test_status_is_known_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """'status' must be a canonical issue status value."""
        known = {"open", "in_progress", "blocked", "deferred", "done", "cancelled"}
        issues_dir = tmp_path / ".issues" / "enhancements"
        self._write_issue(
            issues_dir,
            "P2-ENH-0001-test.md",
            "---\nid: ENH-0001\ntype: ENH\npriority: P2\nstatus: open\n---\n\n# T\n",
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-issues", "list", "--json"]):
            from little_loops.cli.issues import main_issues

            main_issues()
        items = json.loads(capsys.readouterr().out)
        for item in items:
            assert item["status"] in known, f"unexpected status: {item['status']!r}"

    def test_type_is_known_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """'type' must be a known issue type."""
        known = {"BUG", "ENH", "FEAT", "EPIC"}
        issues_dir = tmp_path / ".issues" / "enhancements"
        self._write_issue(
            issues_dir,
            "P2-ENH-0001-test.md",
            "---\nid: ENH-0001\ntype: ENH\npriority: P2\nstatus: open\n---\n\n# T\n",
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-issues", "list", "--json"]):
            from little_loops.cli.issues import main_issues

            main_issues()
        items = json.loads(capsys.readouterr().out)
        for item in items:
            assert item["type"] in known, f"unexpected type: {item['type']!r}"

"""Tests for next_loop.py pure functions and cmd_install.

Covers LoopCandidate, scoring helpers, command building, rationale formatting,
and the install command (which has zero existing test coverage).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.cli.loop.config_cmds import cmd_install
from little_loops.cli.loop.next_loop import (
    LoopCandidate,
    _build_command,
    _build_rationale,
    _recency_score,
    _resolve_params,
    _score_loop,
)
from little_loops.logger import Logger

# ---------------------------------------------------------------------------
# LoopCandidate
# ---------------------------------------------------------------------------


class TestLoopCandidate:
    """Tests for LoopCandidate dataclass."""

    def test_defaults(self) -> None:
        """LoopCandidate has sensible defaults."""
        c = LoopCandidate(
            loop="test-loop",
            score=0.85,
            input=None,
            context={},
            rationale="3 runs; last run today; 100% success",
            command="ll-loop run test-loop",
        )
        assert c.run_count == 0
        assert c.last_run is None
        assert c.success_rate == 1.0

    def test_to_dict_includes_core_fields(self) -> None:
        """to_dict includes loop, input, context, score, rationale, command."""
        c = LoopCandidate(
            loop="my-loop",
            score=0.75,
            input="some input",
            context={"theme": "dark"},
            rationale="5 runs; 80% success",
            command="ll-loop run my-loop",
        )
        d = c.to_dict()
        assert d["loop"] == "my-loop"
        assert d["input"] == "some input"
        assert d["context"] == {"theme": "dark"}
        assert d["score"] == 0.75
        assert d["rationale"] == "5 runs; 80% success"
        assert d["command"] == "ll-loop run my-loop"

    def test_to_dict_rounds_score_to_4_decimal_places(self) -> None:
        """to_dict rounds score to 4 decimal places."""
        c = LoopCandidate(
            loop="lp",
            score=0.123456789,
            input=None,
            context={},
            rationale="",
            command="",
        )
        assert c.to_dict()["score"] == 0.1235

    def test_to_dict_excludes_internal_fields(self) -> None:
        """to_dict excludes run_count, last_run, success_rate."""
        c = LoopCandidate(
            loop="lp",
            score=0.5,
            input=None,
            context={},
            rationale="",
            command="",
            run_count=10,
            last_run="yesterday",
            success_rate=0.9,
        )
        d = c.to_dict()
        assert "run_count" not in d
        assert "last_run" not in d
        assert "success_rate" not in d


# ---------------------------------------------------------------------------
# _recency_score
# ---------------------------------------------------------------------------


class TestRecencyScore:
    """Tests for _recency_score exponential decay function."""

    def test_none_returns_zero(self) -> None:
        """None input returns 0.0."""
        assert _recency_score(None) == 0.0

    def test_empty_string_returns_zero(self) -> None:
        """Empty string returns 0.0 (ValueError caught)."""
        assert _recency_score("") == 0.0

    def test_invalid_format_returns_zero(self) -> None:
        """Invalid date string returns 0.0 (ValueError caught)."""
        assert _recency_score("not-a-date") == 0.0

    def test_now_returns_near_one(self) -> None:
        """A timestamp just seconds ago returns a value close to 1.0."""
        from datetime import UTC, datetime, timedelta

        recent = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
        score = _recency_score(recent)
        assert 0.99 < score <= 1.0

    def test_halflife_decay(self) -> None:
        """After exactly 7 days, score should be ~0.5."""
        from datetime import UTC, datetime, timedelta

        seven_days_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        score = _recency_score(seven_days_ago)
        assert 0.45 < score < 0.55  # allow floating-point tolerance

    def test_very_old_returns_near_zero(self) -> None:
        """A very old timestamp returns a score near 0."""
        from datetime import UTC, datetime, timedelta

        long_ago = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        score = _recency_score(long_ago)
        assert 0.0 <= score < 0.01

    def test_handles_z_suffix(self) -> None:
        """ISO timestamps with 'Z' suffix are handled correctly."""
        from datetime import UTC, datetime, timedelta

        recent = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        score = _recency_score(recent)
        assert 0.9 < score <= 1.0


# ---------------------------------------------------------------------------
# _score_loop
# ---------------------------------------------------------------------------


class TestScoreLoop:
    """Tests for _score_loop composite scoring function."""

    def test_empty_runs_returns_zero_score(self) -> None:
        """Empty run list returns 0.0 score, 1.0 success rate, None last_run."""
        score, success_rate, last_run = _score_loop([])
        assert score == 0.0
        assert success_rate == 1.0
        assert last_run is None

    def test_single_successful_run(self) -> None:
        """A single completed run gets a positive score."""
        from datetime import UTC, datetime, timedelta

        recent = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        runs = [{"status": "completed", "started_at": recent}]
        score, success_rate, last_run = _score_loop(runs)
        assert score > 0.0
        assert success_rate == 1.0
        assert last_run == recent

    def test_mixed_success_and_failure(self) -> None:
        """Success rate is calculated from completed status."""
        from datetime import UTC, datetime, timedelta

        recent = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        runs = [
            {"status": "completed", "started_at": recent},
            {"status": "failed", "started_at": recent},
            {"status": "interrupted", "started_at": recent},
            {"status": "completed", "started_at": recent},
        ]
        score, success_rate, _ = _score_loop(runs)
        assert success_rate == 0.5

    def test_uses_most_recent_started_at(self) -> None:
        """Last_run is the most recent started_at across all runs."""
        older = "2025-01-01T00:00:00+00:00"
        newer = "2025-06-01T00:00:00+00:00"
        runs = [
            {"status": "completed", "started_at": older},
            {"status": "completed", "started_at": newer},
        ]
        _, _, last_run = _score_loop(runs)
        assert last_run == newer

    def test_runs_without_started_at_ignored_for_recency(self) -> None:
        """Runs without started_at don't affect last_run."""
        runs = [
            {"status": "completed"},
            {"status": "completed"},
        ]
        _, _, last_run = _score_loop(runs)
        assert last_run is None


# ---------------------------------------------------------------------------
# _build_command
# ---------------------------------------------------------------------------


class TestBuildCommand:
    """Tests for _build_command shell command construction."""

    def test_basic_command(self) -> None:
        """Basic loop name gives minimal command."""
        cmd = _build_command("fix-types", {})
        assert cmd == "ll-loop run fix-types"

    def test_with_input(self) -> None:
        """Input param is appended as a JSON-encoded positional argument."""
        cmd = _build_command("autodev", {"input": "BUG-001 FEAT-002"})
        assert cmd.startswith("ll-loop run autodev")
        assert '"BUG-001 FEAT-002"' in cmd

    def test_with_context_params(self) -> None:
        """Non-input params become --context flags."""
        cmd = _build_command("my-loop", {"input": "data", "theme": "dark", "verbose": "true"})
        assert "--context theme=dark" in cmd
        assert "--context verbose=true" in cmd

    def test_none_values_skipped(self) -> None:
        """Params with None values are not included."""
        cmd = _build_command("lp", {"input": None, "theme": None})
        assert "None" not in cmd
        assert cmd == "ll-loop run lp"

    def test_empty_params(self) -> None:
        """Empty dict produces minimal command."""
        cmd = _build_command("test", {})
        assert cmd == "ll-loop run test"


# ---------------------------------------------------------------------------
# _build_rationale
# ---------------------------------------------------------------------------


class TestBuildRationale:
    """Tests for _build_rationale human-readable summary."""

    def test_basic_rationale(self) -> None:
        """Rationale includes run count and success rate."""
        r = _build_rationale(run_count=5, success_rate=0.8, last_started_at=None, param_note="")
        assert "5 runs" in r
        assert "80% success" in r

    def test_single_run_singular(self) -> None:
        """Single run uses singular 'run'."""
        r = _build_rationale(run_count=1, success_rate=1.0, last_started_at=None, param_note="")
        assert "1 run" in r
        assert "runs" not in r

    def test_today(self) -> None:
        """Run from today includes 'last run today'."""
        from datetime import UTC, datetime

        today = datetime.now(UTC).isoformat()
        r = _build_rationale(run_count=3, success_rate=1.0, last_started_at=today, param_note="")
        assert "last run today" in r

    def test_yesterday(self) -> None:
        """Run from yesterday includes 'last run yesterday'."""
        from datetime import UTC, datetime, timedelta

        yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        r = _build_rationale(
            run_count=3, success_rate=1.0, last_started_at=yesterday, param_note=""
        )
        assert "last run yesterday" in r

    def test_days_ago(self) -> None:
        """Older runs include 'last run Nd ago'."""
        from datetime import UTC, datetime, timedelta

        five_days = (datetime.now(UTC) - timedelta(days=5)).isoformat()
        r = _build_rationale(
            run_count=3, success_rate=1.0, last_started_at=five_days, param_note=""
        )
        assert "last run 5d ago" in r

    def test_no_last_started_at(self) -> None:
        """Missing last_started_at omits recency info."""
        r = _build_rationale(run_count=3, success_rate=0.9, last_started_at=None, param_note="")
        assert "last run" not in r

    def test_param_note_appended(self) -> None:
        """param_note is appended to the rationale string."""
        r = _build_rationale(
            run_count=2,
            success_rate=1.0,
            last_started_at=None,
            param_note="input resolved (5 items)",
        )
        assert "input resolved (5 items)" in r

    def test_full_rationale_format(self) -> None:
        """Smoke test for full rationale output."""
        from datetime import UTC, datetime, timedelta

        yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        r = _build_rationale(
            run_count=10,
            success_rate=0.9,
            last_started_at=yesterday,
            param_note="input resolved (3 items)",
        )
        parts = r.split("; ")
        assert len(parts) == 4
        assert parts[0] == "10 runs"
        assert parts[1] == "last run yesterday"
        assert parts[2] == "90% success"
        assert parts[3] == "input resolved (3 items)"


# ---------------------------------------------------------------------------
# _resolve_params
# ---------------------------------------------------------------------------


class TestResolveParams:
    """Tests for _resolve_params registry lookup."""

    def test_unknown_loop_returns_empty_dict(self, tmp_path: Path) -> None:
        """Loops without a resolver return empty dict."""
        result = _resolve_params("nonexistent-loop", tmp_path)
        assert result == {}

    def test_registered_loop_calls_resolver(self, tmp_path: Path) -> None:
        """Registered loop name triggers resolver function."""
        # 'autodev' is in the registry
        result = _resolve_params("autodev", tmp_path)
        # Returns empty or dict depending on whether there are active issues
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# cmd_install
# ---------------------------------------------------------------------------


class TestCmdInstall:
    """Tests for cmd_install function."""

    def test_installs_builtin_loop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """cmd_install copies a built-in loop to the project .loops dir."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        # Create a mock built-in loops dir with a test loop
        builtin_dir = tmp_path / "builtins"
        builtin_dir.mkdir()
        (builtin_dir / "test-loop.yaml").write_text("name: test-loop")

        monkeypatch.setattr(
            "little_loops.cli.loop.config_cmds.get_builtin_loops_dir",
            lambda: builtin_dir,
        )

        logger = Logger()
        result = cmd_install("test-loop", loops_dir, logger)

        assert result == 0
        dest = loops_dir / "test-loop.yaml"
        assert dest.exists()
        assert dest.read_text() == "name: test-loop"

    def test_missing_builtin_loop_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-existent built-in loop returns exit code 1."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        builtin_dir = tmp_path / "builtins"
        builtin_dir.mkdir()
        # No test-loop.yaml in builtins

        monkeypatch.setattr(
            "little_loops.cli.loop.config_cmds.get_builtin_loops_dir",
            lambda: builtin_dir,
        )

        logger = Logger()
        result = cmd_install("nonexistent", loops_dir, logger)
        assert result == 1

    def test_already_exists_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Installing a loop that already exists returns exit code 1."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Pre-create the destination
        (loops_dir / "test-loop.yaml").write_text("existing content")

        builtin_dir = tmp_path / "builtins"
        builtin_dir.mkdir()
        (builtin_dir / "test-loop.yaml").write_text("name: test-loop")

        monkeypatch.setattr(
            "little_loops.cli.loop.config_cmds.get_builtin_loops_dir",
            lambda: builtin_dir,
        )

        logger = Logger()
        result = cmd_install("test-loop", loops_dir, logger)
        assert result == 1
        # Existing file should not be overwritten
        assert (loops_dir / "test-loop.yaml").read_text() == "existing content"

    def test_empty_builtins_dir_shows_no_available(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When builtins dir is empty, available list is not printed."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        builtin_dir = tmp_path / "empty_builtins"
        builtin_dir.mkdir()
        # Empty dir — no .yaml files

        monkeypatch.setattr(
            "little_loops.cli.loop.config_cmds.get_builtin_loops_dir",
            lambda: builtin_dir,
        )

        logger = Logger()
        result = cmd_install("missing", loops_dir, logger)
        assert result == 1
        # Should not print "Available built-in loops:" since there are none
        captured = capsys.readouterr()
        assert "Available built-in loops:" not in captured.out

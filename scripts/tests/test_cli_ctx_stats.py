"""Tests for cli/ctx_stats.py - ll-ctx-stats CLI entry point."""

from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.ctx_stats import (
    _aggregate_tool_events,
    _build_parser,
    _compute_cache_rate_from_jsonl,
    _parse_args,
    _progress_bar,
    _time_gained,
    main_ctx_stats,
)
from little_loops.learning_tests import LearnTestRecord, write_record
from little_loops.session_store import connect, ensure_db


def _populate_skill_events(
    db_path: Path,
    rows: list[tuple[str, str, str, str]],
) -> None:
    """Insert (ts, session_id, skill_name, args) rows into skill_events."""
    ensure_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        for ts, session_id, skill_name, args in rows:
            conn.execute(
                "INSERT INTO skill_events(ts, session_id, skill_name, args) VALUES(?, ?, ?, ?)",
                (ts, session_id, skill_name, args),
            )
        conn.commit()
    finally:
        conn.close()


def _insert_correction(db_path: Path, ts: str, session_id: str, content: str) -> None:
    """Insert a user_corrections row directly."""
    ensure_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, 'test')",
            (ts, session_id, content),
        )
        conn.commit()
    finally:
        conn.close()


def _capture_print() -> tuple[list[str], object]:
    """Return (lines, side_effect) for capturing print() calls including no-arg ones."""
    lines: list[str] = []
    return lines, lambda *a, **_kw: lines.append(str(a[0]) if a else "")


def _populate_tool_events(
    db_path: Path,
    rows: list[tuple[str, int | None, int | None, int | None]],
) -> None:
    """Insert ``(tool, bytes_in, bytes_out, cache_hit)`` rows into tool_events."""
    ensure_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        for tool, b_in, b_out, hit in rows:
            conn.execute(
                "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, "
                "result_size, bytes_in, bytes_out, cache_hit) "
                "VALUES('2026-05-22T00:00:00Z', 's1', ?, 'h', ?, ?, ?, ?)",
                (tool, b_out, b_in, b_out, hit),
            )
        conn.commit()
    finally:
        conn.close()


class TestParser:
    """Argument parser shape."""

    def test_build_parser_returns_argument_parser(self) -> None:
        parser = _build_parser()
        assert parser.prog == "ll-ctx-stats"

    def test_default_args(self) -> None:
        args = _parse_args([])
        assert args.db is None
        assert args.json_mode is False

    def test_db_flag(self) -> None:
        args = _parse_args(["--db", "/tmp/x.db"])
        assert args.db == Path("/tmp/x.db")

    def test_json_short_flag(self) -> None:
        args = _parse_args(["-j"])
        assert args.json_mode is True


class TestProgressBar:
    """Inline progress-bar formatter."""

    def test_full_bar(self) -> None:
        bar = _progress_bar(100, 100, 12)
        assert bar.startswith("|") and bar.endswith("|")
        assert "#" * 10 in bar

    def test_half_bar(self) -> None:
        bar = _progress_bar(50, 100, 12)
        assert bar.count("#") == 5
        assert bar.count(" ") == 5

    def test_zero_ceiling(self) -> None:
        bar = _progress_bar(0, 0, 8)
        assert bar == "|" + " " * 6 + "|"


class TestTimeGained:
    """Positive-tense formatter wrapping format_relative_time."""

    def test_strips_ago_suffix(self) -> None:
        # 6m worth of seconds -> "+6m"
        assert _time_gained(360).startswith("+")
        assert " ago" not in _time_gained(360)

    def test_seconds(self) -> None:
        assert _time_gained(45) == "+45s"


class TestAggregateToolEvents:
    """SQLite aggregation helper."""

    def test_missing_db_returns_none(self, tmp_path: Path) -> None:
        assert _aggregate_tool_events(tmp_path / "nope.db") is None

    def test_filters_null_byte_rows(self, tmp_path: Path) -> None:
        """Backfilled rows with NULL bytes_in/bytes_out must not be aggregated."""
        db = tmp_path / "session.db"
        _populate_tool_events(
            db,
            [
                ("Read", 100, 200, 0),
                ("Bash", None, None, None),  # backfilled — should be skipped
                ("Read", 50, 150, 1),
            ],
        )
        summary = _aggregate_tool_events(db)
        assert summary is not None
        assert summary["total_in"] == 150
        assert summary["total_out"] == 350
        assert summary["cache_hits"] == 1
        assert summary["cache_bytes"] == 150
        assert summary["per_tool"]["read"]["calls"] == 2
        assert "bash" not in summary["per_tool"]

    def test_empty_db_returns_zero_summary(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        summary = _aggregate_tool_events(db)
        assert summary is not None
        assert summary["total_out"] == 0


class TestMainCtxStats:
    """End-to-end CLI behavior."""

    def test_returns_zero_when_data_present(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(
            db,
            [
                ("Read", 200, 1024, 0),
                ("Bash", 50, 512, 1),
                ("Read", 100, 2048, 0),
            ],
        )
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-ctx-stats"]),
            patch("builtins.print", side_effect=side_effect),
        ):
            result = main_ctx_stats()
        assert result == 0
        output = "\n".join(lines)
        assert "Without savings" in output
        assert "With savings" in output
        assert "%" in output  # percentage reduction line
        assert "session time gained" in output
        assert "read" in output  # per-tool breakdown
        assert "Cache:" in output  # cache metrics line

    def test_falls_back_to_state_file(self, tmp_path: Path, monkeypatch) -> None:
        """When .ll/history.db is absent, render the ll-context-state.json fallback."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir(exist_ok=True)
        (tmp_path / ".ll" / "ll-context-state.json").write_text(
            json.dumps(
                {
                    "estimated_tokens": 12345,
                    "tool_calls": 7,
                    "breakdown": {"read": 1000, "bash": 500},
                }
            ),
            encoding="utf-8",
        )
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-ctx-stats"]),
            patch("builtins.print", side_effect=side_effect),
        ):
            result = main_ctx_stats()
        assert result == 0
        output = "\n".join(lines)
        assert "12,345" in output or "12345" in output
        assert "read" in output

    def test_returns_one_when_no_data(self, tmp_path: Path, monkeypatch) -> None:
        """Exit 1 when neither the SQLite store nor the fallback file is present."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("sys.argv", ["ll-ctx-stats"]),
            patch("builtins.print"),
        ):
            result = main_ctx_stats()
        assert result == 1

    def test_json_mode(self, tmp_path: Path, monkeypatch) -> None:
        """--json emits parseable JSON with bytes_processed/reduction_pct."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 100, 900, 0)])
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-ctx-stats", "--json"]),
            patch("builtins.print", side_effect=side_effect),
        ):
            result = main_ctx_stats()
        assert result == 0
        data = json.loads("\n".join(lines))
        assert data["source"] == "sqlite"
        assert data["bytes_processed"] == 1000
        assert "reduction_pct" in data
        assert "per_tool" in data
        assert data.get("skill_health") is None  # no skill events seeded

    def test_skill_health_section_present(self, tmp_path: Path, monkeypatch) -> None:
        """Skill-health section appears in human-readable output when skill events present."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 200, 1024, 0)])
        _populate_skill_events(db, [("2026-01-01T00:00:00Z", "s1", "manage-issue", "")])
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-ctx-stats"]),
            patch("builtins.print", side_effect=side_effect),
        ):
            result = main_ctx_stats()
        assert result == 0
        output = "\n".join(lines)
        assert "Skill health" in output
        assert "manage-issue" in output

    def test_skill_health_absent_when_no_skill_rows(self, tmp_path: Path, monkeypatch) -> None:
        """Skill-health section is omitted when skill_events table is empty."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 200, 1024, 0)])
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-ctx-stats"]),
            patch("builtins.print", side_effect=side_effect),
        ):
            result = main_ctx_stats()
        assert result == 0
        output = "\n".join(lines)
        assert "Skill health" not in output

    def test_json_mode_skill_health_present(self, tmp_path: Path, monkeypatch) -> None:
        """--json includes skill_health list when skill events are present."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 100, 900, 0)])
        _populate_skill_events(
            db,
            [
                ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
                ("2026-01-01T00:01:00Z", "s1", "manage-issue", ""),
                ("2026-01-01T00:02:00Z", "s1", "run-tests", ""),
            ],
        )
        _insert_correction(db, "2026-01-01T00:00:30Z", "s1", "no, not that")
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-ctx-stats", "--json"]),
            patch("builtins.print", side_effect=side_effect),
        ):
            result = main_ctx_stats()
        assert result == 0
        data = json.loads("\n".join(lines))
        assert "skill_health" in data
        assert isinstance(data["skill_health"], list)
        skills = {row["skill"]: row for row in data["skill_health"]}
        assert "manage-issue" in skills
        assert skills["manage-issue"]["invocations"] == 2
        assert "correction_rate" in skills["manage-issue"]

    def test_json_mode_skill_health_none_when_no_skill_rows(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """--json has skill_health=null when no skill events recorded."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 100, 900, 0)])
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-ctx-stats", "--json"]),
            patch("builtins.print", side_effect=side_effect),
        ):
            result = main_ctx_stats()
        assert result == 0
        data = json.loads("\n".join(lines))
        assert data.get("skill_health") is None

    def test_db_flag_uses_explicit_path(self, tmp_path: Path, monkeypatch) -> None:
        """--db PATH overrides the default .ll/history.db location."""
        monkeypatch.chdir(tmp_path)
        custom = tmp_path / "elsewhere" / "alt.db"
        custom.parent.mkdir()
        _populate_tool_events(custom, [("Read", 1, 99, 0)])
        with (
            patch("sys.argv", ["ll-ctx-stats", "--db", str(custom), "--json"]),
            patch("builtins.print") as printed,
        ):
            result = main_ctx_stats()
        assert result == 0
        rendered = "".join(str(call.args[0]) for call in printed.call_args_list if call.args)
        assert "sqlite" in rendered


class TestToolEventsRoundtrip:
    """Cross-module sanity: connect() round-trips the FEAT-1623 byte columns."""

    def test_recent_tool_rows_carry_byte_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        _populate_tool_events(db, [("Read", 7, 42, 1)])
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT bytes_in, bytes_out, cache_hit FROM tool_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        assert row["bytes_in"] == 7
        assert row["bytes_out"] == 42
        assert row["cache_hit"] == 1


class TestComputeCacheRateFromJsonl:
    """Cache hit rate computation from JSONL transcript."""

    def _write_jsonl(self, path: Path, entries: list[dict]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_returns_none_when_no_project_folder(self, tmp_path: Path) -> None:
        with patch("little_loops.cli.ctx_stats.get_project_folder", return_value=None):
            assert _compute_cache_rate_from_jsonl(tmp_path) is None

    def test_returns_none_when_no_jsonl_files(self, tmp_path: Path) -> None:
        project_folder = tmp_path / "projects"
        project_folder.mkdir()
        with patch("little_loops.cli.ctx_stats.get_project_folder", return_value=project_folder):
            assert _compute_cache_rate_from_jsonl(tmp_path) is None

    def test_computes_hit_rate(self, tmp_path: Path) -> None:
        project_folder = tmp_path / "projects"
        project_folder.mkdir()
        self._write_jsonl(
            project_folder / "session.jsonl",
            [
                {
                    "type": "assistant",
                    "uuid": "a1",
                    "message": {
                        "usage": {
                            "cache_read_input_tokens": 61559,
                            "cache_creation_input_tokens": 3689,
                            "input_tokens": 1,
                        }
                    },
                }
            ],
        )
        with patch("little_loops.cli.ctx_stats.get_project_folder", return_value=project_folder):
            result = _compute_cache_rate_from_jsonl(tmp_path)
        assert result is not None
        assert result["cache_read"] == 61559
        assert result["cache_write"] == 3689
        assert result["uncached"] == 1
        expected_pct = round(61559 / (61559 + 3689 + 1) * 100)
        assert result["hit_rate_pct"] == expected_pct

    def test_aggregates_multiple_turns(self, tmp_path: Path) -> None:
        project_folder = tmp_path / "projects"
        project_folder.mkdir()
        self._write_jsonl(
            project_folder / "session.jsonl",
            [
                {
                    "type": "assistant",
                    "uuid": "a1",
                    "message": {
                        "usage": {
                            "cache_read_input_tokens": 100,
                            "cache_creation_input_tokens": 10,
                            "input_tokens": 5,
                        }
                    },
                },
                {
                    "type": "assistant",
                    "uuid": "a2",
                    "message": {
                        "usage": {
                            "cache_read_input_tokens": 200,
                            "cache_creation_input_tokens": 20,
                            "input_tokens": 2,
                        }
                    },
                },
            ],
        )
        with patch("little_loops.cli.ctx_stats.get_project_folder", return_value=project_folder):
            result = _compute_cache_rate_from_jsonl(tmp_path)
        assert result is not None
        assert result["cache_read"] == 300
        assert result["cache_write"] == 30
        assert result["uncached"] == 7

    def test_deduplicates_by_uuid(self, tmp_path: Path) -> None:
        project_folder = tmp_path / "projects"
        project_folder.mkdir()
        self._write_jsonl(
            project_folder / "session.jsonl",
            [
                {
                    "type": "assistant",
                    "uuid": "dup",
                    "message": {
                        "usage": {
                            "cache_read_input_tokens": 100,
                            "cache_creation_input_tokens": 10,
                            "input_tokens": 1,
                        }
                    },
                },
                {
                    "type": "assistant",
                    "uuid": "dup",
                    "message": {
                        "usage": {
                            "cache_read_input_tokens": 100,
                            "cache_creation_input_tokens": 10,
                            "input_tokens": 1,
                        }
                    },
                },
            ],
        )
        with patch("little_loops.cli.ctx_stats.get_project_folder", return_value=project_folder):
            result = _compute_cache_rate_from_jsonl(tmp_path)
        assert result is not None
        assert result["cache_read"] == 100  # counted once only
        assert result["cache_write"] == 10

    def test_skips_agent_jsonl_files(self, tmp_path: Path) -> None:
        project_folder = tmp_path / "projects"
        project_folder.mkdir()
        self._write_jsonl(
            project_folder / "agent-worker.jsonl",
            [
                {
                    "type": "assistant",
                    "uuid": "a1",
                    "message": {
                        "usage": {
                            "cache_read_input_tokens": 9000,
                            "cache_creation_input_tokens": 0,
                            "input_tokens": 1,
                        }
                    },
                }
            ],
        )
        (project_folder / "session.jsonl").write_text("")
        with patch("little_loops.cli.ctx_stats.get_project_folder", return_value=project_folder):
            assert _compute_cache_rate_from_jsonl(tmp_path) is None

    def test_returns_none_when_total_zero(self, tmp_path: Path) -> None:
        project_folder = tmp_path / "projects"
        project_folder.mkdir()
        self._write_jsonl(
            project_folder / "session.jsonl",
            [
                {
                    "type": "assistant",
                    "uuid": "a1",
                    "message": {
                        "usage": {
                            "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0,
                            "input_tokens": 0,
                        }
                    },
                }
            ],
        )
        with patch("little_loops.cli.ctx_stats.get_project_folder", return_value=project_folder):
            assert _compute_cache_rate_from_jsonl(tmp_path) is None

    def test_skips_non_assistant_entries(self, tmp_path: Path) -> None:
        project_folder = tmp_path / "projects"
        project_folder.mkdir()
        self._write_jsonl(
            project_folder / "session.jsonl",
            [
                {"type": "user", "message": {"content": "hello"}},
                {
                    "type": "assistant",
                    "uuid": "a1",
                    "message": {
                        "usage": {
                            "cache_read_input_tokens": 50,
                            "cache_creation_input_tokens": 5,
                            "input_tokens": 1,
                        }
                    },
                },
            ],
        )
        with patch("little_loops.cli.ctx_stats.get_project_folder", return_value=project_folder):
            result = _compute_cache_rate_from_jsonl(tmp_path)
        assert result is not None
        assert result["cache_read"] == 50


class TestCacheHitRateInOutput:
    """Cache hit rate appears in _render() and --json when JSONL data is available."""

    def _populate_and_run(
        self,
        tmp_path: Path,
        monkeypatch,
        extra_argv: list[str] | None = None,
        cache_rate: dict | None = None,
    ) -> tuple[int, str]:
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        import sqlite3

        from little_loops.session_store import ensure_db

        ensure_db(db)
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, result_size, bytes_in, bytes_out, cache_hit) "
            "VALUES('2026-01-01T00:00:00Z', 's1', 'Read', 'h', 100, 200, 1024, 0)"
        )
        conn.commit()
        conn.close()

        lines: list[str] = []
        argv = ["ll-ctx-stats"] + (extra_argv or [])
        with (
            patch("sys.argv", argv),
            patch(
                "builtins.print", side_effect=lambda *a, **_: lines.append(str(a[0]) if a else "")
            ),
            patch(
                "little_loops.cli.ctx_stats._compute_cache_rate_from_jsonl", return_value=cache_rate
            ),
        ):
            rc = main_ctx_stats()
        return rc, "\n".join(lines)

    def test_hit_rate_line_shown_in_render(self, tmp_path: Path, monkeypatch) -> None:
        cache_rate = {"cache_read": 61559, "cache_write": 3689, "uncached": 1, "hit_rate_pct": 94}
        rc, output = self._populate_and_run(tmp_path, monkeypatch, cache_rate=cache_rate)
        assert rc == 0
        assert "Cache hit rate: 94%" in output
        assert "cache_read=61,559" in output
        assert "cache_write=3,689" in output

    def test_hit_rate_line_absent_when_no_jsonl(self, tmp_path: Path, monkeypatch) -> None:
        rc, output = self._populate_and_run(tmp_path, monkeypatch, cache_rate=None)
        assert rc == 0
        assert "Cache hit rate" not in output

    def test_json_includes_cache_hit_rate(self, tmp_path: Path, monkeypatch) -> None:
        cache_rate = {"cache_read": 500, "cache_write": 50, "uncached": 2, "hit_rate_pct": 89}
        rc, output = self._populate_and_run(
            tmp_path, monkeypatch, extra_argv=["--json"], cache_rate=cache_rate
        )
        assert rc == 0
        data = json.loads(output)
        assert data["cache_hit_rate_pct"] == 89
        assert data["cache_read_tokens"] == 500
        assert data["cache_write_tokens"] == 50
        assert data["uncached_tokens"] == 2

    def test_json_cache_hit_rate_null_when_no_jsonl(self, tmp_path: Path, monkeypatch) -> None:
        rc, output = self._populate_and_run(
            tmp_path, monkeypatch, extra_argv=["--json"], cache_rate=None
        )
        assert rc == 0
        data = json.loads(output)
        assert data["cache_hit_rate_pct"] is None


class TestLearningTestsSection:
    """Learning tests dashboard section in ll-ctx-stats."""

    def _write_config(self, tmp_path: Path, *, enabled: bool, stale_after_days: int = 30) -> None:
        config_path = tmp_path / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {"learning_tests": {"enabled": enabled, "stale_after_days": stale_after_days}}
            ),
            encoding="utf-8",
        )

    def _write_record(self, tmp_path: Path, target: str, status: str, date: str) -> None:
        record = LearnTestRecord(
            target=target, date=date, status=status, assertions=[], raw_output_path=None
        )
        write_record(record, base_dir=tmp_path / ".ll" / "learning-tests")

    def _run(
        self,
        tmp_path: Path,
        argv: list[str] | None = None,
        imported: set[str] | None = None,
    ) -> tuple[int, str]:
        lines: list[str] = []
        patch_targets = [
            patch("sys.argv", ["ll-ctx-stats"] + (argv or [])),
            patch(
                "builtins.print", side_effect=lambda *a, **_: lines.append(str(a[0]) if a else "")
            ),
            patch("little_loops.cli.ctx_stats._compute_cache_rate_from_jsonl", return_value=None),
        ]
        if imported is not None:
            patch_targets.append(
                patch(
                    "little_loops.cli.ctx_stats.get_imported_packages",
                    return_value=imported,
                )
            )
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in patch_targets:
                stack.enter_context(p)
            rc = main_ctx_stats()
        return rc, "\n".join(lines)

    def test_section_present_when_enabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Learning tests section appears when learning_tests.enabled: true."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 200, 1024, 0)])
        self._write_config(tmp_path, enabled=True)
        self._write_record(tmp_path, "anthropic", "proven", "2026-06-01")

        rc, output = self._run(tmp_path, imported=set())
        assert rc == 0
        assert "Learning tests:" in output

    def test_section_absent_when_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Learning tests section is omitted when learning_tests.enabled: false."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 200, 1024, 0)])
        self._write_config(tmp_path, enabled=False)

        rc, output = self._run(tmp_path)
        assert rc == 0
        assert "Learning tests:" not in output

    def test_section_absent_when_no_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Learning tests section is omitted when no config file exists (default disabled)."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 200, 1024, 0)])

        rc, output = self._run(tmp_path)
        assert rc == 0
        assert "Learning tests:" not in output

    def test_counts_shown_correctly(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Proven/stale/refuted counts appear in the output."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 200, 1024, 0)])
        self._write_config(tmp_path, enabled=True)
        recent = datetime.date.today().isoformat()
        self._write_record(tmp_path, "anthropic", "proven", recent)
        self._write_record(tmp_path, "boto3", "stale", "2026-05-01")
        self._write_record(tmp_path, "stripe", "refuted", "2026-04-01")

        rc, output = self._run(tmp_path, imported=set())
        assert rc == 0
        assert "3 total" in output
        assert "1 proven" in output
        assert "1 stale" in output
        assert "1 refuted" in output

    def test_date_aware_stale_reclassification(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A proven record beyond stale_after_days threshold is counted as stale."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 200, 1024, 0)])
        self._write_config(tmp_path, enabled=True, stale_after_days=10)
        old_date = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
        self._write_record(tmp_path, "requests", "proven", old_date)

        rc, output = self._run(tmp_path, imported=set())
        assert rc == 0
        assert "0 proven" in output
        assert "1 stale" in output

    def test_gap_list_shows_unregistered_package(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Packages imported but absent from registry appear in coverage gaps."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 200, 1024, 0)])
        self._write_config(tmp_path, enabled=True)
        self._write_record(tmp_path, "requests", "proven", "2026-06-01")

        rc, output = self._run(tmp_path, imported={"boto3", "requests"})
        assert rc == 0
        assert "boto3" in output  # gap
        # requests is covered — should NOT appear in gap list
        # (just check it doesn't appear next to "gaps")
        gap_line = next((ln for ln in output.splitlines() if "gaps" in ln.lower()), "")
        assert "boto3" in gap_line
        assert "requests" not in gap_line

    def test_no_gap_line_when_all_covered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Coverage gaps line is omitted when all imported packages have records."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 200, 1024, 0)])
        self._write_config(tmp_path, enabled=True)
        self._write_record(tmp_path, "anthropic", "proven", "2026-06-01")

        rc, output = self._run(tmp_path, imported={"anthropic"})
        assert rc == 0
        assert "Coverage gaps" not in output

    def test_json_mode_includes_learning_tests(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--json output includes learning_tests key when enabled."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 200, 1024, 0)])
        self._write_config(tmp_path, enabled=True)
        self._write_record(tmp_path, "anthropic", "proven", datetime.date.today().isoformat())

        lines: list[str] = []
        with (
            patch("sys.argv", ["ll-ctx-stats", "--json"]),
            patch(
                "builtins.print", side_effect=lambda *a, **_: lines.append(str(a[0]) if a else "")
            ),
            patch("little_loops.cli.ctx_stats._compute_cache_rate_from_jsonl", return_value=None),
            patch("little_loops.cli.ctx_stats.get_imported_packages", return_value={"boto3"}),
        ):
            rc = main_ctx_stats()
        assert rc == 0
        data = json.loads("\n".join(lines))
        lt = data.get("learning_tests")
        assert lt is not None
        assert lt["total"] == 1
        assert lt["proven"] == 1
        assert lt["stale"] == 0
        assert lt["refuted"] == 0
        assert "boto3" in lt["gaps"]

    def test_json_mode_learning_tests_null_when_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--json has learning_tests: null when disabled."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "history.db"
        db.parent.mkdir(exist_ok=True)
        _populate_tool_events(db, [("Read", 200, 1024, 0)])
        self._write_config(tmp_path, enabled=False)

        lines: list[str] = []
        with (
            patch("sys.argv", ["ll-ctx-stats", "--json"]),
            patch(
                "builtins.print", side_effect=lambda *a, **_: lines.append(str(a[0]) if a else "")
            ),
            patch("little_loops.cli.ctx_stats._compute_cache_rate_from_jsonl", return_value=None),
        ):
            rc = main_ctx_stats()
        assert rc == 0
        data = json.loads("\n".join(lines))
        assert data.get("learning_tests") is None


@pytest.fixture(autouse=True)
def _isolate_terminal_width(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin terminal width so progress-bar output stays stable across CI shells."""
    monkeypatch.setattr("little_loops.cli.ctx_stats.terminal_width", lambda _default=80: 100)

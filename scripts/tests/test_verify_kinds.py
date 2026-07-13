"""Tests for ll-verify-kinds — CREATE TABLE / VALID_KINDS registration gate (ENH-2581)."""

from __future__ import annotations

from unittest.mock import patch

from little_loops.cli.verify_kinds import _all_migration_tables, _run, main_verify_kinds


class TestAllMigrationTables:
    def test_finds_known_tables(self) -> None:
        tables = _all_migration_tables()
        assert "tool_events" in tables
        assert "raw_events" in tables
        assert "issue_snapshots" in tables


class TestRun:
    def test_clean_state_returns_zero(self) -> None:
        """Every real CREATE TABLE is either kind-registered or explicitly kindless."""
        exit_code, unregistered = _run()
        assert exit_code == 0
        assert unregistered == []

    def test_flags_unregistered_table(self) -> None:
        """A CREATE TABLE not in _KIND_TABLE or _KINDLESS_TABLES is flagged."""
        with patch(
            "little_loops.cli.verify_kinds._all_migration_tables",
            return_value={"tool_events", "mystery_events"},
        ):
            exit_code, unregistered = _run()
        assert exit_code == 1
        assert unregistered == ["mystery_events"]


class TestMainVerifyKinds:
    def test_clean_state_returns_zero(self) -> None:
        with patch("sys.argv", ["ll-verify-kinds"]):
            assert main_verify_kinds() == 0

    def test_dirty_state_returns_one_with_error(self, capsys) -> None:
        with (
            patch("sys.argv", ["ll-verify-kinds"]),
            patch(
                "little_loops.cli.verify_kinds._all_migration_tables",
                return_value={"mystery_events"},
            ),
        ):
            ret = main_verify_kinds()
        captured = capsys.readouterr()
        assert ret == 1
        assert "mystery_events" in captured.err

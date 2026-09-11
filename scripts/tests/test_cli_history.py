"""Tests for ll-history CLI subcommands.

Focuses on coverage NOT already in test_issue_history_cli.py:
- root subcommand (completely untested)
- analyze --format yaml routing
- sessions --json edge case
- export stdout mode

Note: imports inside main_history() are function-local, so mocking goes to
source modules (little_loops.issue_history.*, little_loops.history_reader.*),
NOT to little_loops.cli.history.*.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.history import main_history


def _make_empty_analysis():
    """Build a minimal HistoryAnalysis for mocking calculate_analysis."""
    from little_loops.issue_history import HistoryAnalysis, HistorySummary

    return HistoryAnalysis(
        generated_date=date(2026, 1, 1),
        total_completed=0,
        total_active=0,
        date_range_start=None,
        date_range_end=None,
        summary=HistorySummary(total_count=0),
    )


# ---------------------------------------------------------------------------
# root subcommand
# ---------------------------------------------------------------------------


class TestHistoryRootSubcommand:
    """Tests for ll-history root subcommand (completely untested elsewhere)."""

    def test_root_no_db_returns_1(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """root returns 1 when no DB or no root node found."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        with patch.object(sys, "argv", ["ll-history", "root"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1
        captured = capsys.readouterr()
        assert "No project-root summary node found" in captured.out

    def test_root_missing_db_still_returns_1(self, tmp_path: Path) -> None:
        """root returns 1 when .ll/history.db does not exist."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        with patch.object(sys, "argv", ["ll-history", "root"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1

    def test_root_json_flag_accepted_returns_1_without_db(self, tmp_path: Path) -> None:
        """--json flag is accepted and returns 1 gracefully when no DB."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        with patch.object(sys, "argv", ["ll-history", "root", "--json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1

    def test_root_expand_flag_accepted(self, tmp_path: Path) -> None:
        """--expand flag is accepted without crashing."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        with patch.object(sys, "argv", ["ll-history", "root", "--expand"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1

    def test_root_limit_flag_accepted(self, tmp_path: Path) -> None:
        """--limit flag is accepted without crashing."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        with patch.object(sys, "argv", ["ll-history", "root", "--limit", "5"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1


# ---------------------------------------------------------------------------
# analyze subcommand — yaml format routing
# ---------------------------------------------------------------------------


class TestHistoryAnalyzeYaml:
    """Test analyze --format yaml routing (yaml not heavily tested elsewhere)."""

    def test_analyze_yaml_calls_format_yaml_function(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

        # Imports inside main_history are function-local → mock at source module
        with patch.object(
            sys, "argv", ["ll-history", "analyze", "--format", "yaml", "-d", str(issues_dir)]
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.issue_history.scan_completed_issues", return_value=[]):
                    with patch(
                        "little_loops.issue_history.calculate_analysis",
                        return_value=_make_empty_analysis(),
                    ):
                        with patch("little_loops.issue_history.format_analysis_yaml") as mock_fmt:
                            mock_fmt.return_value = "analysis: empty\n"
                            result = main_history()

        assert result == 0
        mock_fmt.assert_called_once()
        captured = capsys.readouterr()
        assert "analysis: empty" in captured.out

    def test_analyze_yaml_exit_code_zero(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

        with patch.object(
            sys, "argv", ["ll-history", "analyze", "--format", "yaml", "-d", str(issues_dir)]
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.issue_history.scan_completed_issues", return_value=[]):
                    with patch(
                        "little_loops.issue_history.calculate_analysis",
                        return_value=_make_empty_analysis(),
                    ):
                        result = main_history()

        assert result == 0


# ---------------------------------------------------------------------------
# rework subcommand (FEAT-2867)
# ---------------------------------------------------------------------------


class TestHistoryReworkSubcommand:
    """Test the rework subcommand's argument wiring and format routing."""

    def test_rework_text_default_empty_history(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "rework"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "Rework Rate Analysis" in captured.out
        assert "No closed-issue history found" in captured.out

    def test_rework_json_format_routes_to_json_formatter(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "rework", "--format", "json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["windows"] == []
        assert payload["min_sample_size"] == 5

    def test_rework_min_sample_and_follow_up_days_flags_accepted(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(
            sys,
            "argv",
            ["ll-history", "rework", "--min-sample", "2", "--follow-up-days", "7"],
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0

    def test_rework_help_exits_zero_after_quality_subparser_added(self) -> None:
        """FEAT-3183: adding the `quality` subparser must not disturb `rework`."""
        with patch.object(sys, "argv", ["ll-history", "rework", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main_history()
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# quality subcommand (FEAT-3183)
# ---------------------------------------------------------------------------


class TestHistoryQualitySubcommand:
    """Test the quality subcommand's argument wiring and format routing."""

    def test_quality_text_default_empty_history(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "Agent Quality Report" in captured.out
        assert "No closed-issue history found" in captured.out

    def test_quality_json_format_routes_to_json_formatter(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality", "--format", "json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["windows"] == []
        assert payload["min_sample_size"] == 5
        assert len(payload["definitions"]) == 4

    def test_quality_min_sample_flag_accepted(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality", "--min-sample", "2"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0

    def test_quality_help_exits_zero(self) -> None:
        with patch.object(sys, "argv", ["ll-history", "quality", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main_history()
        assert exc_info.value.code == 0

    def test_quality_sensitivity_flag_accepted(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality", "--sensitivity", "0.5"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0

    def test_quality_baseline_windows_flag_accepted(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality", "--baseline-windows", "2"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0

    def test_quality_all_windows_flag_accepted(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality", "--all-windows"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0

    def test_quality_sensitivity_negative_rejected(self) -> None:
        with patch.object(sys, "argv", ["ll-history", "quality", "--sensitivity=-1"]):
            with pytest.raises(SystemExit) as exc_info:
                main_history()
        assert exc_info.value.code != 0

    def test_quality_baseline_windows_zero_rejected(self) -> None:
        with patch.object(sys, "argv", ["ll-history", "quality", "--baseline-windows=0"]):
            with pytest.raises(SystemExit) as exc_info:
                main_history()
        assert exc_info.value.code != 0


class TestHistoryQualityWorkspaceFlag:
    """`--workspace` (FEAT-3410): manifest-driven cross-repo aggregation."""

    @staticmethod
    def _member_db(repo_dir: Path, *, schema_version: str) -> None:
        """A member db with the *full* current schema (all tables), then a schema_version override.

        FEAT-3418's totals pass reads every one of the 9 union-view relations
        via ``PRAGMA table_info()``, which assumes a schema-version-matching
        member actually has those tables (true for any real, migrated
        ``history.db``) -- so this builds a real schema via `ensure_db()`
        rather than a hand-rolled ``meta``-only table, then overwrites
        ``schema_version`` when a caller needs a skewed value.
        """
        import sqlite3

        from little_loops.session_store.schema import SCHEMA_VERSION, ensure_db

        (repo_dir / ".issues").mkdir(parents=True, exist_ok=True)
        ll_dir = repo_dir / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        db_path = ll_dir / "history.db"
        ensure_db(db_path)
        if schema_version != str(SCHEMA_VERSION):
            conn = sqlite3.connect(db_path)
            conn.execute(
                "UPDATE meta SET value = ? WHERE key = 'schema_version'", (schema_version,)
            )
            conn.commit()
            conn.close()

    def test_workspace_flag_two_member_manifest_shows_both_labels(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store.schema import SCHEMA_VERSION

        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        self._member_db(tmp_path / "member_a", schema_version=str(SCHEMA_VERSION))
        self._member_db(tmp_path / "member_b", schema_version=str(SCHEMA_VERSION))
        (tmp_path / "ll-workspace.yaml").write_text(
            "members:\n"
            "  - repo: member_a\n"
            "    role: primary\n"
            "  - repo: member_b\n"
            "    role: sibling\n"
        )

        with patch.object(sys, "argv", ["ll-history", "quality", "--workspace"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        out = capsys.readouterr().out
        assert "member_a (primary)" in out
        assert "member_b (sibling)" in out

    def test_workspace_bare_flag_no_manifest_matches_no_flag_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()

        with patch.object(sys, "argv", ["ll-history", "quality"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                assert main_history() == 0
        no_flag_output = capsys.readouterr().out

        with patch.object(sys, "argv", ["ll-history", "quality", "--workspace"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                assert main_history() == 0
        bare_flag_output = capsys.readouterr().out

        assert bare_flag_output == no_flag_output

    def test_workspace_missing_declared_manifest_exits_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        missing = tmp_path / "does-not-exist.yaml"

        with patch.object(sys, "argv", ["ll-history", "quality", "--workspace", str(missing)]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result != 0
        assert str(missing) in capsys.readouterr().err

    def test_workspace_flag_absent_ignores_discoverable_manifest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store.schema import SCHEMA_VERSION

        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        self._member_db(tmp_path / "member_a", schema_version=str(SCHEMA_VERSION))
        (tmp_path / "ll-workspace.yaml").write_text(
            "members:\n  - repo: member_a\n    role: primary\n"
        )

        with patch.object(sys, "argv", ["ll-history", "quality"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        out = capsys.readouterr().out
        assert "member_a (primary)" not in out
        assert "No closed-issue history found" in out


# ---------------------------------------------------------------------------
# activity subcommand (FEAT-3446)
# ---------------------------------------------------------------------------


class TestHistoryActivity:
    """`ll-history activity` (FEAT-3446): workspace activity counts + JSON contract."""

    _MEMBER_KEYS = [
        "repo_path",
        "role",
        "label",
        "status",
        "ok",
        "error",
        "instrumented",
        "has_history",
        "loops_run",
        "loops_completed",
        "issues_completed",
        "issues_deferred",
        "issues_closed",
    ]
    _TOTALS_KEYS = [
        "members",
        "instrumented_members",
        "instrumented",
        "has_history_members",
        "has_history",
        "ok_members",
        "loops_run",
        "loops_completed",
        "issues_completed",
        "issues_deferred",
        "issues_closed",
    ]

    @staticmethod
    def _healthy_member(tmp_path: Path, name: str, role: str) -> None:
        """Create a member repo with a real current-schema db via the write API.

        Deliberately named ``<name>-history.db`` (non-default-shaped): the
        autouse ``_isolate_history_db`` fixture routes default-shaped
        ``.ll/history.db`` opens through one shared ``LL_HISTORY_DB`` env var,
        which would collapse every member onto the same file. The manifest
        entry carries an explicit ``db_path`` to match.
        """
        from little_loops.session_store.writers import record_issue_event

        repo_path = tmp_path / name
        (repo_path / ".issues").mkdir(parents=True, exist_ok=True)
        (repo_path / ".ll").mkdir(exist_ok=True)
        db_path = repo_path / ".ll" / f"{name}-history.db"
        record_issue_event(db_path, f"{name}-BUG-1", "done")

    @staticmethod
    def _write_manifest(tmp_path: Path, members: list[dict]) -> Path:
        manifest = tmp_path / "ll-workspace.yaml"
        lines = ["members:"]
        for entry in members:
            lines.append(f"  - repo: {entry['repo']}")
            lines.append(f"    role: {entry['role']}")
            if "db_path" in entry:
                lines.append(f"    db_path: {entry['db_path']}")
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return manifest

    def test_workspace_json_golden_shape(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """AC 1: exact JSON contract — key order, null-unavailable counts, OR totals."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        self._healthy_member(tmp_path, "member_a", "source")
        (tmp_path / "member_b" / ".issues").mkdir(parents=True, exist_ok=True)
        manifest = self._write_manifest(
            tmp_path,
            [
                {"repo": "member_a", "role": "source", "db_path": ".ll/member_a-history.db"},
                {"repo": "member_b", "role": "consumer", "db_path": ".ll/member_b-history.db"},
            ],
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "activity",
                "--workspace",
                str(manifest),
                "--since",
                "2020-01-01T00:00:00Z",
                "--format",
                "json",
            ],
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert list(payload.keys()) == ["since", "until", "per_repo", "totals"]
        assert payload["since"] == "2020-01-01T00:00:00Z"
        assert payload["until"] is None
        assert len(payload["per_repo"]) == 2

        healthy, missing_db = payload["per_repo"]
        assert list(healthy.keys()) == self._MEMBER_KEYS
        assert healthy["role"] == "source"
        assert healthy["label"] == "member_a (source)"
        assert healthy["repo_path"].endswith("member_a")
        assert healthy["status"] == "ok"
        assert healthy["ok"] is True
        assert healthy["error"] is None
        assert healthy["instrumented"] is True
        assert healthy["has_history"] is True
        assert healthy["issues_completed"] == 1
        assert healthy["issues_deferred"] == 0
        assert healthy["issues_closed"] is None

        assert list(missing_db.keys()) == self._MEMBER_KEYS
        assert missing_db["status"] == "db_missing"
        assert missing_db["ok"] is False
        assert missing_db["instrumented"] is False
        assert missing_db["has_history"] is False
        assert missing_db["error"] is not None
        assert "not found" in missing_db["error"]
        for field in ("loops_run", "loops_completed", "issues_completed", "issues_deferred"):
            assert missing_db[field] is None
        assert missing_db["issues_closed"] is None

        assert list(payload["totals"].keys()) == self._TOTALS_KEYS
        assert payload["totals"]["members"] == 2
        assert payload["totals"]["instrumented_members"] == 1
        assert payload["totals"]["instrumented"] is True
        assert payload["totals"]["has_history_members"] == 1
        assert payload["totals"]["has_history"] is True
        assert payload["totals"]["ok_members"] == 1
        assert payload["totals"]["issues_completed"] == 1
        assert payload["totals"]["issues_closed"] is None

    def test_bare_flag_matches_explicit_manifest_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """AC 2: bare --workspace discovers the same manifest an explicit path names."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        self._healthy_member(tmp_path, "member_a", "source")
        manifest = self._write_manifest(
            tmp_path,
            [{"repo": "member_a", "role": "source", "db_path": ".ll/member_a-history.db"}],
        )

        with patch.object(sys, "argv", ["ll-history", "activity", "--workspace"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                assert main_history() == 0
        bare = capsys.readouterr().out

        with patch.object(sys, "argv", ["ll-history", "activity", "--workspace", str(manifest)]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                assert main_history() == 0
        explicit = capsys.readouterr().out

        assert bare == explicit

    def test_absent_flag_single_repo_result(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC 2: no flag = single-repo result with the pinned fallback member shape."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        # Anchor db resolution at the tmp project regardless of the developer's
        # shell (ENH-3449 test hygiene).
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)

        with patch.object(sys, "argv", ["ll-history", "activity", "--format", "json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["per_repo"]) == 1
        member = payload["per_repo"][0]
        # cli_event_context pre-creates the local db via its cli_events insert,
        # so the fallback member is `ok` with zero counts while capture is on.
        assert member["status"] == "ok"
        assert member["role"] == "source"
        assert member["label"] == f"{tmp_path.name} (source)"
        assert member["repo_path"] == str(tmp_path)
        assert member["issues_completed"] == 0
        # ENH-3450 golden: the fallback db carries only a cli_events row —
        # schema'd but empty, so has_history is False (Decision 5: analytics
        # churn is not workspace history).
        assert member["has_history"] is False
        assert payload["totals"]["has_history"] is False
        assert payload["totals"]["ok_members"] == 1

    def test_activity_env_kill_switch_db_missing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ENH-3449: LL_ANALYTICS_CAPTURE=0 makes activity side-effect-free.

        Read-only polling contract: exit 0, local member db_missing/ok:false/
        instrumented:false, and no .ll/history.db authored by the run.
        """
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        monkeypatch.setenv("LL_ANALYTICS_CAPTURE", "0")
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)

        with patch.object(sys, "argv", ["ll-history", "activity", "--format", "json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        member = payload["per_repo"][0]
        assert member["status"] == "db_missing"
        assert member["ok"] is False
        assert member["instrumented"] is False
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_activity_without_env_var_writes_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ENH-3449: without the kill switch the cli_events row is still written."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        monkeypatch.delenv("LL_ANALYTICS_CAPTURE", raising=False)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)

        with patch.object(sys, "argv", ["ll-history", "activity", "--format", "json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
                # Row check inside the cwd patch: recent() re-resolves the
                # default-shaped path, and an unpatched cwd would trip the
                # conftest production-db guard.
                from little_loops.session_store import recent

                rows = recent(tmp_path / ".ll" / "history.db", kind="cli")
        capsys.readouterr()

        assert result == 0
        assert len(rows) == 1
        assert rows[0]["binary"] == "ll-history"

    def test_activity_config_gate_suppresses_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ENH-3449: analytics.capture.cli_commands excluding ll-history suppresses the row."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"analytics": {"capture": {"cli_commands": ["ll-session"]}}}),
            encoding="utf-8",
        )
        monkeypatch.delenv("LL_ANALYTICS_CAPTURE", raising=False)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)

        with patch.object(sys, "argv", ["ll-history", "activity", "--format", "json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        capsys.readouterr()

        assert result == 0
        assert not (tmp_path / ".ll" / "history.db").exists(), (
            "config gate must suppress the cli_events insert entirely"
        )

    def test_activity_analytics_enabled_false_suppresses_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ENH-3449: analytics.enabled=false (ll-init opt-out shape) suppresses the row."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"analytics": {"enabled": False}}),
            encoding="utf-8",
        )
        monkeypatch.delenv("LL_ANALYTICS_CAPTURE", raising=False)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)

        with patch.object(sys, "argv", ["ll-history", "activity", "--format", "json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        capsys.readouterr()

        assert result == 0
        assert not (tmp_path / ".ll" / "history.db").exists(), (
            "analytics.enabled=false must suppress the cli_events insert entirely"
        )

    def test_bare_flag_zero_members_matches_no_flag_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """AC 2: zero discovered members -> single-repo fallback, identical output."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()

        with patch.object(sys, "argv", ["ll-history", "activity", "--format", "json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                assert main_history() == 0
        no_flag_output = capsys.readouterr().out

        with patch.object(
            sys, "argv", ["ll-history", "activity", "--workspace", "--format", "json"]
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                assert main_history() == 0
        bare_flag_output = capsys.readouterr().out

        assert bare_flag_output == no_flag_output

    def test_missing_declared_manifest_exits_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """AC 2: declared-but-missing manifest -> exit 1 with the path on stderr."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        missing = tmp_path / "does-not-exist.yaml"

        with patch.object(sys, "argv", ["ll-history", "activity", "--workspace", str(missing)]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result != 0
        assert str(missing) in capsys.readouterr().err

    def test_invalid_since_rejected(self) -> None:
        """AC 3: invalid --since is a parser-level usage error, not a traceback."""
        with patch.object(sys, "argv", ["ll-history", "activity", "--since", "not-a-date"]):
            with pytest.raises(SystemExit) as exc_info:
                main_history()
        assert exc_info.value.code != 0

    def test_invalid_until_rejected(self) -> None:
        """AC 3: invalid --until is a parser-level usage error, not a traceback."""
        with patch.object(sys, "argv", ["ll-history", "activity", "--until", "2026-13-45"]):
            with pytest.raises(SystemExit) as exc_info:
                main_history()
        assert exc_info.value.code != 0

    def test_all_four_formats_render_with_scope_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """AC 4: all four --format values render; the scope flag never gates them."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        self._healthy_member(tmp_path, "member_a", "source")
        self._write_manifest(
            tmp_path,
            [{"repo": "member_a", "role": "source", "db_path": ".ll/member_a-history.db"}],
        )

        for fmt, expect_parseable in [
            ("json", True),
            ("yaml", False),
            ("markdown", False),
            ("text", False),
        ]:
            with patch.object(
                sys, "argv", ["ll-history", "activity", "--workspace", "--format", fmt]
            ):
                with patch("pathlib.Path.cwd", return_value=tmp_path):
                    assert main_history() == 0
            out = capsys.readouterr().out
            assert out.strip(), f"empty output for --format {fmt}"
            assert "member_a (source)" in out
            if expect_parseable:
                assert json.loads(out)["totals"]["members"] == 1

    def test_no_ok_member_totals_all_null(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """AC 5: no ok member -> exit 0, full totals object with null counts."""
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        (tmp_path / "member_b" / ".issues").mkdir(parents=True, exist_ok=True)
        self._write_manifest(
            tmp_path,
            [{"repo": "member_b", "role": "consumer", "db_path": ".ll/member_b-history.db"}],
        )

        with patch.object(
            sys, "argv", ["ll-history", "activity", "--workspace", "--format", "json"]
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["totals"]["members"] == 1
        assert payload["totals"]["ok_members"] == 0
        assert payload["totals"]["instrumented"] is False
        # ENH-3450: count/any over `is True` only — no True member -> 0/false.
        assert payload["totals"]["has_history_members"] == 0
        assert payload["totals"]["has_history"] is False
        for field in ("loops_run", "loops_completed", "issues_completed", "issues_deferred"):
            assert payload["totals"][field] is None
        assert payload["totals"]["issues_closed"] is None


# ---------------------------------------------------------------------------
# sessions subcommand — json output
# ---------------------------------------------------------------------------


class TestHistorySessionsJson:
    """Test sessions subcommand --json flag."""

    def test_sessions_json_empty_returns_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        with patch.object(sys, "argv", ["ll-history", "sessions", "ENH-999", "--json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                # sessions_for_issue is from little_loops.history_reader
                with patch("little_loops.history_reader.sessions_for_issue", return_value=[]):
                    result = main_history()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert data == []

    def test_sessions_no_match_text_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        with patch.object(sys, "argv", ["ll-history", "sessions", "ENH-999"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.history_reader.sessions_for_issue", return_value=[]):
                    result = main_history()
        assert result == 0
        captured = capsys.readouterr()
        assert "No sessions found" in captured.out


# ---------------------------------------------------------------------------
# export subcommand — stdout mode
# ---------------------------------------------------------------------------


class TestHistoryExportStdout:
    """Test export subcommand output to stdout."""

    def test_export_prints_to_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

        with patch.object(
            sys,
            "argv",
            ["ll-history", "export", "testing", "-d", str(issues_dir)],
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.issue_history.scan_completed_issues", return_value=[]):
                    with patch(
                        "little_loops.issue_history.synthesize_docs",
                        return_value="# Doc output\n",
                    ):
                        result = main_history()
        assert result == 0
        captured = capsys.readouterr()
        assert "# Doc output" in captured.out

    def test_export_empty_issues_exits_zero(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

        with patch.object(
            sys, "argv", ["ll-history", "export", "some-topic", "-d", str(issues_dir)]
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.issue_history.scan_completed_issues", return_value=[]):
                    result = main_history()
        assert result == 0


# ---------------------------------------------------------------------------
# analyze subcommand — db_path propagation
# ---------------------------------------------------------------------------


class TestHistoryAnalyzeDbPath:
    """Test that analyze branch resolves and passes db_path to calculate_analysis."""

    def test_analyze_passes_db_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """analyze branch should pass a resolved db_path to calculate_analysis."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "analyze", "-d", str(issues_dir)]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.issue_history.scan_completed_issues", return_value=[]):
                    with patch(
                        "little_loops.issue_history.calculate_analysis",
                        return_value=_make_empty_analysis(),
                    ) as mock_calc:
                        main_history()

        mock_calc.assert_called_once()
        call_kwargs = mock_calc.call_args.kwargs
        assert "db_path" in call_kwargs
        assert call_kwargs["db_path"] is not None

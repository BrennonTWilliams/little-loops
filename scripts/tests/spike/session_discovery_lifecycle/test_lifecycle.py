"""AC tests for the FEAT-3417 session-discovery lifecycle spike.

See .ll/spikes/spike-FEAT-3417.md for the risk each test retires.
"""

from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path

from scripts.tests.spike.session_discovery_lifecycle import lifecycle as lc


def _make_state_db(path: Path, rows: list[tuple], *, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    cols = columns or ["id", "rollout_path", "cwd", "source", "created_at", "updated_at"]
    conn.execute(f"CREATE TABLE threads ({', '.join(c + ' TEXT' for c in cols)})")
    if rows:
        placeholders = ", ".join("?" for _ in cols)
        conn.executemany(f"INSERT INTO threads VALUES ({placeholders})", rows)
    conn.commit()
    conn.close()


def _write_rollout(path: Path, session_id: str, cwd: str, extra_lines: list[dict] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "timestamp": "2026-09-08T00:00:00Z",
        "type": "session_meta",
        "payload": {"id": session_id, "cwd": cwd, "cli_version": "0.130.0"},
    }
    lines = [header] + (extra_lines or [])
    with path.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


class TestDetectSessionsCodexSqlitePath:
    def test_detect_sessions_codex_uses_sqlite_when_present(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        rollout = home / "rollout-a.jsonl"
        _write_rollout(rollout, "sess-a", str(cwd))
        _make_state_db(
            home / ".codex" / "state_1.sqlite",
            [("sess-a", str(rollout), str(cwd), "exec", "1000", "2000")],
        )

        handles = lc.detect_sessions(cwd, "codex", home=home)

        assert len(handles) == 1
        assert handles[0].session_id == "sess-a"
        assert handles[0].path == rollout
        assert handles[0].updated_at == 2000.0

    def test_detect_sessions_codex_picks_newest_state_db_by_name(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        old_rollout = home / "old.jsonl"
        new_rollout = home / "new.jsonl"
        _write_rollout(old_rollout, "sess-old", str(cwd))
        _write_rollout(new_rollout, "sess-new", str(cwd))
        # state_2 predates state_10 lexicographically but must lose numerically.
        _make_state_db(
            home / ".codex" / "state_2.sqlite",
            [("sess-old", str(old_rollout), str(cwd), "exec", "1", "1")],
        )
        _make_state_db(
            home / ".codex" / "state_10.sqlite",
            [("sess-new", str(new_rollout), str(cwd), "exec", "1", "9999")],
        )

        handles = lc.detect_sessions(cwd, "codex", home=home)

        assert len(handles) == 1
        assert handles[0].session_id == "sess-new"

    def test_detect_sessions_codex_filters_stale_rollout_paths(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        live_rollout = home / "live.jsonl"
        _write_rollout(live_rollout, "sess-live", str(cwd))
        deleted_rollout = home / "deleted.jsonl"  # never created on disk

        _make_state_db(
            home / ".codex" / "state_1.sqlite",
            [
                ("sess-live", str(live_rollout), str(cwd), "exec", "1", "2000"),
                ("sess-deleted", str(deleted_rollout), str(cwd), "exec", "1", "3000"),
            ],
        )

        handles = lc.detect_sessions(cwd, "codex", home=home)

        assert len(handles) == 1
        assert handles[0].session_id == "sess-live"

    def test_detect_sessions_codex_orders_newest_first_and_respects_limit(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        rollouts = []
        rows = []
        for i in range(3):
            r = home / f"r{i}.jsonl"
            _write_rollout(r, f"sess-{i}", str(cwd))
            rollouts.append(r)
            rows.append((f"sess-{i}", str(r), str(cwd), "exec", "1", str(i)))
        _make_state_db(home / ".codex" / "state_1.sqlite", rows)

        handles = lc.detect_sessions(cwd, "codex", home=home, limit=2)

        assert [h.session_id for h in handles] == ["sess-2", "sess-1"]


class TestDetectSessionsCodexFallback:
    def test_detect_sessions_codex_falls_back_to_date_scan_when_db_missing(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        day_dir = home / ".codex" / "sessions" / "2026" / "09" / "08"
        rollout = day_dir / "rollout-2026-09-08T00-00-00Z-uuid1.jsonl"
        _write_rollout(rollout, "sess-scan", str(cwd))
        other_cwd_rollout = day_dir / "rollout-2026-09-08T00-00-01Z-uuid2.jsonl"
        _write_rollout(other_cwd_rollout, "sess-other", "/repo/other")

        handles = lc.detect_sessions(cwd, "codex", home=home)

        assert len(handles) == 1
        assert handles[0].session_id == "sess-scan"
        assert handles[0].path == rollout

    def test_detect_sessions_codex_falls_back_when_db_schema_mismatched(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        # DB present but missing the `cwd`/`updated_at` columns this contract requires.
        _make_state_db(
            home / ".codex" / "state_1.sqlite",
            rows=[],
            columns=["id", "rollout_path"],
        )
        day_dir = home / ".codex" / "sessions" / "2026" / "09" / "08"
        rollout = day_dir / "rollout-2026-09-08T00-00-00Z-uuid1.jsonl"
        _write_rollout(rollout, "sess-scan", str(cwd))

        handles = lc.detect_sessions(cwd, "codex", home=home)

        assert len(handles) == 1
        assert handles[0].session_id == "sess-scan"

    def test_detect_sessions_codex_scan_orders_newest_date_dir_first(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        early = home / ".codex" / "sessions" / "2026" / "01" / "01" / "rollout-early.jsonl"
        late = home / ".codex" / "sessions" / "2026" / "09" / "08" / "rollout-late.jsonl"
        _write_rollout(early, "sess-early", str(cwd))
        _write_rollout(late, "sess-late", str(cwd))

        handles = lc.detect_sessions(cwd, "codex", home=home)

        assert [h.session_id for h in handles] == ["sess-late", "sess-early"]

    def test_detect_sessions_missing_host_home_returns_empty_not_raise(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")

        handles = lc.detect_sessions(cwd, "codex", home=home)

        assert handles == []


class TestIterEventsDispatch:
    def test_iter_events_dispatches_by_host_without_cross_contamination(self, tmp_path):
        cwd = Path("/repo/project")
        codex_rollout = tmp_path / "rollout.jsonl"
        _write_rollout(
            codex_rollout,
            "sess-codex",
            str(cwd),
            extra_lines=[
                {
                    "timestamp": "2026-09-08T00:00:01Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "hi"},
                }
            ],
        )
        claude_transcript = tmp_path / "claude.jsonl"
        claude_transcript.write_text(
            json.dumps({"type": "user", "timestamp": "2026-09-08T00:00:00Z", "message": {"role": "user"}})
            + "\n"
        )

        codex_handle = lc.SessionHandle(
            host="codex", session_id="sess-codex", path=codex_rollout, cwd=cwd, updated_at=1.0
        )
        claude_handle = lc.SessionHandle(
            host="claude-code", session_id="sess-claude", path=claude_transcript, cwd=cwd, updated_at=1.0
        )

        codex_events = list(lc.iter_events(codex_handle))
        claude_events = list(lc.iter_events(claude_handle))

        assert [e.type for e in codex_events] == ["session_meta", "event_msg"]
        assert all(e.host == "codex" for e in codex_events)
        assert codex_events[1].payload == {"type": "user_message", "message": "hi"}

        assert [e.type for e in claude_events] == ["user"]
        assert all(e.host == "claude-code" for e in claude_events)
        # Claude payload is the whole record (no header-only convention),
        # proving the two parsers don't share a payload shape.
        assert "message" in claude_events[0].payload

    def test_iter_events_unknown_host_yields_nothing(self, tmp_path):
        handle = lc.SessionHandle(
            host="unknown-host", session_id="x", path=tmp_path / "missing.jsonl", cwd=tmp_path, updated_at=0.0
        )

        assert list(lc.iter_events(handle)) == []


class TestIsolationGuard:
    def test_lifecycle_module_has_no_production_imports(self):
        source = (Path(__file__).parent / "lifecycle.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_prefixes = ("little_loops", "scripts.little_loops")

        offending = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefixes):
                        offending.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith(forbidden_prefixes):
                    offending.append(node.module)

        assert offending == [], f"spike imports production module(s): {offending}"

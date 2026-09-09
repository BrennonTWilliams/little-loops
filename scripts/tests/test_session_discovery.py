"""Tests for the session-discovery lifecycle seam (FEAT-3417).

Promoted from ``scripts/tests/spike/session_discovery_lifecycle/test_lifecycle.py``
(11 original tests) plus the coverage the promotion review required: host=None
union, include_agents on both hosts, list_workspaces, dual cwd matching on
both Codex paths, the archived_sessions/ scan fallback, and the
unusable-DB-at-first-statement case.

Every test passes ``home=tmp_path`` (never writes into the shared fake home
that ``_isolate_session_log_dir`` points ``Path.home()`` at — see
conftest.py's docstring for why that dir must stay read-only-by-convention).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from little_loops.session_store import sessions as ss


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


def _write_rollout(
    path: Path, session_id: str, cwd: str, extra_lines: list[dict] | None = None
) -> None:
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

        handles = ss.detect_sessions(cwd, "codex", home=home)

        assert len(handles) == 1
        assert handles[0].session_id == "sess-a"
        assert handles[0].path == rollout
        assert handles[0].updated_at == 2000.0
        assert handles[0].is_agent is False

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

        handles = ss.detect_sessions(cwd, "codex", home=home)

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

        handles = ss.detect_sessions(cwd, "codex", home=home)

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

        handles = ss.detect_sessions(cwd, "codex", home=home, limit=2)

        assert [h.session_id for h in handles] == ["sess-2", "sess-1"]

    def test_detect_sessions_codex_matches_resolved_cwd_spelling(self, tmp_path):
        """A DB row keyed on the resolved cwd (macOS /tmp -> /private/tmp style
        rewrite) still matches a caller passing the unresolved spelling."""
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        resolved_cwd = cwd.resolve()
        rollout = home / "rollout-a.jsonl"
        _write_rollout(rollout, "sess-a", str(resolved_cwd))
        _make_state_db(
            home / ".codex" / "state_1.sqlite",
            [("sess-a", str(rollout), str(resolved_cwd), "exec", "1", "2000")],
        )

        handles = ss.detect_sessions(cwd, "codex", home=home)

        assert len(handles) == 1
        assert handles[0].session_id == "sess-a"
        # Handle.cwd is the caller's spelling, not the row's.
        assert handles[0].cwd == cwd

    def test_detect_sessions_codex_agent_role_sets_is_agent(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        rollout = home / "rollout-a.jsonl"
        _write_rollout(rollout, "sess-a", str(cwd))
        _make_state_db(
            home / ".codex" / "state_1.sqlite",
            [("sess-a", str(rollout), str(cwd), "researcher", "2000")],
            columns=["id", "rollout_path", "cwd", "agent_role", "updated_at"],
        )

        default_handles = ss.detect_sessions(cwd, "codex", home=home)
        assert default_handles == []  # subagent excluded by default

        all_handles = ss.detect_sessions(cwd, "codex", home=home, include_agents=True)
        assert len(all_handles) == 1
        assert all_handles[0].is_agent is True


class TestDetectSessionsCodexFallback:
    def test_detect_sessions_codex_falls_back_to_date_scan_when_db_missing(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        day_dir = home / ".codex" / "sessions" / "2026" / "09" / "08"
        rollout = day_dir / "rollout-2026-09-08T00-00-00Z-uuid1.jsonl"
        _write_rollout(rollout, "sess-scan", str(cwd))
        other_cwd_rollout = day_dir / "rollout-2026-09-08T00-00-01Z-uuid2.jsonl"
        _write_rollout(other_cwd_rollout, "sess-other", "/repo/other")

        handles = ss.detect_sessions(cwd, "codex", home=home)

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

        handles = ss.detect_sessions(cwd, "codex", home=home)

        assert len(handles) == 1
        assert handles[0].session_id == "sess-scan"

    def test_detect_sessions_codex_falls_back_when_db_unusable_at_first_statement(self, tmp_path):
        """sqlite3.connect(..., mode=ro) succeeds on a non-database file; the
        error only surfaces at the first statement (PRAGMA/SELECT), which is
        the real failure point this fallback must guard — distinct from a
        missing file or a schema mismatch (covered above)."""
        home = tmp_path
        db_path = home / ".codex" / "state_1.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(b"not a sqlite database")
        cwd = Path("/repo/project")
        day_dir = home / ".codex" / "sessions" / "2026" / "09" / "08"
        rollout = day_dir / "rollout-2026-09-08T00-00-00Z-uuid1.jsonl"
        _write_rollout(rollout, "sess-scan", str(cwd))

        handles = ss.detect_sessions(cwd, "codex", home=home)

        assert len(handles) == 1
        assert handles[0].session_id == "sess-scan"

    def test_detect_sessions_codex_scan_orders_newest_date_dir_first(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        early = home / ".codex" / "sessions" / "2026" / "01" / "01" / "rollout-early.jsonl"
        late = home / ".codex" / "sessions" / "2026" / "09" / "08" / "rollout-late.jsonl"
        _write_rollout(early, "sess-early", str(cwd))
        _write_rollout(late, "sess-late", str(cwd))

        handles = ss.detect_sessions(cwd, "codex", home=home)

        assert [h.session_id for h in handles] == ["sess-late", "sess-early"]

    def test_detect_sessions_codex_scan_includes_archived_sessions_tree(self, tmp_path):
        """archived_sessions/ is flat on codex-cli 0.152.1 (confirmed by live
        capture), not date-keyed — a defensive **/*.jsonl glob must still find
        it and interleave it with sessions/ by updated_at."""
        home = tmp_path
        cwd = Path("/repo/project")
        live = home / ".codex" / "sessions" / "2026" / "09" / "08" / "rollout-live.jsonl"
        archived = home / ".codex" / "archived_sessions" / "rollout-archived.jsonl"
        _write_rollout(live, "sess-live", str(cwd))
        _write_rollout(archived, "sess-archived", str(cwd))

        handles = ss.detect_sessions(cwd, "codex", home=home)

        assert {h.session_id for h in handles} == {"sess-live", "sess-archived"}

    def test_detect_sessions_missing_host_home_returns_empty_not_raise(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")

        handles = ss.detect_sessions(cwd, "codex", home=home)

        assert handles == []


class TestDetectSessionsClaudeCode:
    def test_detect_sessions_claude_code_resolves_via_home_not_get_project_folder(
        self, tmp_path, monkeypatch
    ):
        """Must not call get_project_folder/get_sessions_folder (both read
        Path.home() and would ignore the home= override)."""
        # Point the real Path.home() somewhere that must NOT be consulted.
        decoy_home = tmp_path / "decoy-home"
        monkeypatch.setattr(Path, "home", lambda: decoy_home)

        home = tmp_path / "explicit-home"
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        encoded = encode_project_path(str(cwd.resolve()))
        project_dir = home / ".claude" / "projects" / encoded
        session_file = project_dir / "sess-1.jsonl"
        session_file.parent.mkdir(parents=True)
        session_file.write_text(json.dumps({"type": "user", "cwd": str(cwd)}) + "\n")

        handles = ss.detect_sessions(cwd, "claude-code", home=home)

        assert len(handles) == 1
        assert handles[0].path == session_file

    def test_detect_sessions_claude_code_excludes_agent_sessions_by_default(self, tmp_path):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        project_dir = home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))
        project_dir.mkdir(parents=True)
        (project_dir / "sess-1.jsonl").write_text("{}\n")
        (project_dir / "agent-sess-2.jsonl").write_text("{}\n")

        default_handles = ss.detect_sessions(cwd, "claude-code", home=home)
        assert [h.session_id for h in default_handles] == ["sess-1"]

        all_handles = ss.detect_sessions(cwd, "claude-code", home=home, include_agents=True)
        assert {h.session_id for h in all_handles} == {"sess-1", "agent-sess-2"}
        agent_handle = next(h for h in all_handles if h.session_id == "agent-sess-2")
        assert agent_handle.is_agent is True


class TestDetectSessionsHostNone:
    def test_detect_sessions_host_none_unions_and_orders_across_hosts(self, tmp_path):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        project_dir = home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))
        project_dir.mkdir(parents=True)
        claude_session = project_dir / "claude-sess.jsonl"
        claude_session.write_text("{}\n")
        import os

        os.utime(claude_session, (1000, 1000))

        codex_rollout = home / "codex-sess.jsonl"
        _write_rollout(codex_rollout, "codex-sess", str(cwd))
        _make_state_db(
            home / ".codex" / "state_1.sqlite",
            [("codex-sess", str(codex_rollout), str(cwd), "exec", "1", "5000")],
        )

        handles = ss.detect_sessions(cwd, home=home)

        assert [h.host for h in handles] == ["codex", "claude-code"]
        assert [h.session_id for h in handles] == ["codex-sess", "claude-sess"]

    def test_detect_sessions_host_none_limit_applies_after_merge(self, tmp_path):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        project_dir = home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))
        project_dir.mkdir(parents=True)
        import os

        for i, ts in enumerate([100, 200, 300]):
            f = project_dir / f"claude-{i}.jsonl"
            f.write_text("{}\n")
            os.utime(f, (ts, ts))

        codex_rollout = home / "codex-sess.jsonl"
        _write_rollout(codex_rollout, "codex-sess", str(cwd))
        _make_state_db(
            home / ".codex" / "state_1.sqlite",
            [("codex-sess", str(codex_rollout), str(cwd), "exec", "1", "1000")],
        )

        handles = ss.detect_sessions(cwd, home=home, limit=2)

        assert len(handles) == 2
        assert handles[0].session_id == "codex-sess"


class TestListWorkspaces:
    def test_list_workspaces_claude_code(self, tmp_path):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        project_dir = home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))
        project_dir.mkdir(parents=True)
        (project_dir / "sess.jsonl").write_text(json.dumps({"cwd": str(cwd)}) + "\n")

        workspaces = ss.list_workspaces("claude-code", home=home)

        assert workspaces == [cwd]

    def test_list_workspaces_codex_via_sqlite(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        rollout = home / "rollout.jsonl"
        _write_rollout(rollout, "sess-a", str(cwd))
        _make_state_db(
            home / ".codex" / "state_1.sqlite",
            [("sess-a", str(rollout), str(cwd), "exec", "1", "2000")],
        )

        workspaces = ss.list_workspaces("codex", home=home, existing_only=False)

        assert workspaces == [cwd]

    def test_list_workspaces_codex_scan_fallback(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        day_dir = home / ".codex" / "sessions" / "2026" / "09" / "08"
        _write_rollout(day_dir / "rollout.jsonl", "sess-a", str(cwd))

        workspaces = ss.list_workspaces("codex", home=home, existing_only=False)

        assert workspaces == [cwd]

    def test_list_workspaces_unknown_host_returns_empty(self, tmp_path):
        assert ss.list_workspaces("unknown-host", home=tmp_path) == []


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
            json.dumps(
                {"type": "user", "timestamp": "2026-09-08T00:00:00Z", "message": {"role": "user"}}
            )
            + "\n"
        )

        codex_handle = ss.SessionHandle(
            host="codex", session_id="sess-codex", path=codex_rollout, cwd=cwd, updated_at=1.0
        )
        claude_handle = ss.SessionHandle(
            host="claude-code",
            session_id="sess-claude",
            path=claude_transcript,
            cwd=cwd,
            updated_at=1.0,
        )

        codex_events = list(ss.iter_events(codex_handle))
        claude_events = list(ss.iter_events(claude_handle))

        assert [e.type for e in codex_events] == ["session_meta", "event_msg"]
        assert all(e.host == "codex" for e in codex_events)
        assert codex_events[1].payload == {"type": "user_message", "message": "hi"}

        assert [e.type for e in claude_events] == ["user"]
        assert all(e.host == "claude-code" for e in claude_events)
        # Claude payload is the whole record (no header-only convention),
        # proving the two parsers don't share a payload shape.
        assert "message" in claude_events[0].payload

    def test_iter_events_unknown_host_yields_nothing(self, tmp_path):
        handle = ss.SessionHandle(
            host="unknown-host",
            session_id="x",
            path=tmp_path / "missing.jsonl",
            cwd=tmp_path,
            updated_at=0.0,
        )

        assert list(ss.iter_events(handle)) == []


class TestParseCodexRolloutFixtures:
    """Parser tests against the two committed real-shape fixtures
    (codex-cli 0.152.1) — see scripts/tests/fixtures/codex/README.md."""

    def test_parses_interactive_fixture_header_and_unknown_types_pass_through(self, fixtures_dir):
        path = fixtures_dir / "codex" / "rollout-interactive.jsonl"

        events = list(ss.parse_codex_rollout(path))

        assert events[0].type == "session_meta"
        assert events[0].payload["id"] == "01a086ea-c8bc-79f1-9faa-1ce2716aa80f"
        assert events[0].payload["cwd"] == "/workspace/project"
        assert events[0].payload["cli_version"] == "0.152.1"
        # Oversized line 1 (inlined base_instructions) parses without error.
        assert "base_instructions" in events[0].payload

        # world_state is an unrecognized top-level type on 0.152.1 — passed
        # through untouched, not raised or special-cased.
        world_state_events = [e for e in events if e.type == "world_state"]
        assert len(world_state_events) == 1
        assert set(world_state_events[0].payload.keys()) >= {"full", "state"}

        # 0.152.1 response_item/event_msg subtypes pass through untouched too.
        subtypes = {
            e.payload.get("type") for e in events if e.type in ("response_item", "event_msg")
        }
        assert "custom_tool_call" in subtypes
        assert "custom_tool_call_output" in subtypes
        assert "reasoning" in subtypes
        assert "item_completed" in subtypes
        assert "token_count" in subtypes

    def test_parses_exec_fixture_header(self, fixtures_dir):
        path = fixtures_dir / "codex" / "rollout-exec.jsonl"

        events = list(ss.parse_codex_rollout(path))

        assert events[0].type == "session_meta"
        assert events[0].payload["id"] == "01a086eb-75f9-75c2-b2ad-59202d992489"
        assert events[0].payload["cwd"] == "/workspace/project"
        assert any(
            e.payload.get("type") == "task_complete" for e in events if e.type == "event_msg"
        )


class TestIsolationGuard:
    def test_spike_directory_removed(self):
        spike_dir = Path(__file__).parent / "spike" / "session_discovery_lifecycle"
        assert not spike_dir.exists(), "spike directory should be removed after promotion"

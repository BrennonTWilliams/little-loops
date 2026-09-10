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

    def test_detect_sessions_finds_dir_encoded_from_unresolved_symlinked_cwd(self, tmp_path):
        """A project dir encoded from an unresolved symlinked cwd is found via the
        both-spellings probe (ENH-3427) — the resolved-only encoding used to miss it."""
        home = tmp_path / "home"
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        symlink_cwd = tmp_path / "link"
        symlink_cwd.symlink_to(real_dir)

        from little_loops.user_messages import encode_project_path

        encoded = encode_project_path(str(symlink_cwd.absolute()))
        project_dir = home / ".claude" / "projects" / encoded
        session_file = project_dir / "sess-1.jsonl"
        session_file.parent.mkdir(parents=True)
        session_file.write_text(json.dumps({"type": "user", "cwd": str(symlink_cwd)}) + "\n")

        handles = ss.detect_sessions(symlink_cwd, "claude-code", home=home)

        assert len(handles) == 1
        assert handles[0].path == session_file


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


class TestNonObjectJsonLines:
    """A line that parses as JSON but is not an object must be skipped, not
    raise — the generator/scan convention is 'never raise' (gemini/omp)."""

    def test_parsers_skip_non_object_lines(self, tmp_path):
        codex = tmp_path / "codex.jsonl"
        codex.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": "x", "cwd": "/w"}})
            + '\n[1, 2]\n"str"\n42\n'
            + json.dumps({"type": "event_msg", "payload": "not-a-dict"})
            + "\n"
        )
        claude = tmp_path / "claude.jsonl"
        claude.write_text('[1, 2]\n"str"\n' + json.dumps({"type": "user"}) + "\n")

        codex_events = list(ss.parse_codex_rollout(codex))
        claude_events = list(ss.parse_claude_transcript(claude))

        assert [e.type for e in codex_events] == ["session_meta", "event_msg"]
        assert codex_events[1].payload == {}  # non-dict payload coerced, not raised
        assert [e.type for e in claude_events] == ["user"]

    def test_scan_fallback_and_list_workspaces_skip_non_object_headers(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/project")
        day_dir = home / ".codex" / "sessions" / "2026" / "09" / "09"
        day_dir.mkdir(parents=True)
        (day_dir / "rollout-bad-list.jsonl").write_text("[1, 2]\n")
        (day_dir / "rollout-bad-payload.jsonl").write_text(
            json.dumps({"type": "session_meta", "payload": "str"}) + "\n"
        )
        _write_rollout(day_dir / "rollout-good.jsonl", "sess-good", str(cwd))

        handles = ss.detect_sessions(cwd, "codex", home=home)
        workspaces = ss.list_workspaces("codex", home=home, existing_only=False)

        assert [h.session_id for h in handles] == ["sess-good"]
        assert workspaces == [cwd]

    def test_claude_list_workspaces_skips_non_object_records(self, tmp_path):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        project_dir = home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))
        project_dir.mkdir(parents=True)
        (project_dir / "sess.jsonl").write_text("[1, 2]\n" + json.dumps({"cwd": str(cwd)}) + "\n")

        assert ss.list_workspaces("claude-code", home=home) == [cwd]


class TestCodexSqliteScanParity:
    def test_sqlite_path_and_scan_fallback_return_same_sessions(self, tmp_path):
        """AC: for a fixture tree containing one archived rollout, the sqlite
        `threads` path and the date-dir scan fallback discover the same
        sessions. Compared on (session_id, path): `updated_at` legitimately
        differs (DB integer vs. file mtime) and `is_agent` has no scan-side
        signal, so full handle equality is not the contract."""
        home = tmp_path
        cwd = Path("/repo/project")
        live = home / ".codex" / "sessions" / "2026" / "09" / "08" / "rollout-live.jsonl"
        archived = home / ".codex" / "archived_sessions" / "rollout-archived.jsonl"
        _write_rollout(live, "sess-live", str(cwd))
        _write_rollout(archived, "sess-archived", str(cwd))
        db = home / ".codex" / "state_1.sqlite"
        _make_state_db(
            db,
            [
                ("sess-live", str(live), str(cwd), "exec", "1", "2000"),
                ("sess-archived", str(archived), str(cwd), "exec", "1", "1000"),
            ],
        )

        via_sqlite = ss.detect_sessions(cwd, "codex", home=home)
        db.unlink()
        via_scan = ss.detect_sessions(cwd, "codex", home=home)

        key = lambda hs: {(h.session_id, h.path) for h in hs}  # noqa: E731
        assert (
            key(via_sqlite) == key(via_scan) == {("sess-live", live), ("sess-archived", archived)}
        )
        assert all(h.host == "codex" and h.cwd == cwd for h in via_sqlite + via_scan)


# --- ENH-3420: opencode/pi/kimi-code/qwen/gemini/omp registered in the seam ---


class TestDetectSessionsOpencodePi:
    """opencode/pi are Claude-shaped on disk; same home-aware probe pattern
    as claude-code, stamped with their own host."""

    def test_detect_sessions_opencode_resolves_via_home_not_real_home(self, tmp_path, monkeypatch):
        decoy_home = tmp_path / "decoy-home"
        monkeypatch.setattr(Path, "home", lambda: decoy_home)
        home = tmp_path / "explicit-home"
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        project_dir = home / ".opencode" / "projects" / encode_project_path(str(cwd.resolve()))
        project_dir.mkdir(parents=True)
        (project_dir / "sess-1.jsonl").write_text(json.dumps({"type": "user"}) + "\n")

        handles = ss.detect_sessions(cwd, "opencode", home=home)

        assert len(handles) == 1
        assert handles[0].host == "opencode"
        assert handles[0].session_id == "sess-1"

    def test_detect_sessions_pi_resolves_via_home(self, tmp_path):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        project_dir = home / ".pi" / "projects" / encode_project_path(str(cwd.resolve()))
        project_dir.mkdir(parents=True)
        (project_dir / "sess-1.jsonl").write_text(json.dumps({"type": "user"}) + "\n")

        handles = ss.detect_sessions(cwd, "pi", home=home)

        assert [h.session_id for h in handles] == ["sess-1"]
        assert handles[0].host == "pi"

    def test_iter_events_opencode_and_pi_stamp_their_own_host(self, tmp_path):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        encoded = encode_project_path(str(cwd.resolve()))
        for host, cli_dir in (("opencode", ".opencode"), ("pi", ".pi")):
            project_dir = home / cli_dir / "projects" / encoded
            project_dir.mkdir(parents=True)
            (project_dir / "sess.jsonl").write_text(
                json.dumps({"type": "user", "message": {"role": "user"}}) + "\n"
            )
            handle = ss.detect_sessions(cwd, host, home=home)[0]
            events = list(ss.iter_events(handle))
            assert [e.host for e in events] == [host]
            assert events[0].payload["type"] == "user"


class TestDetectSessionsKimiCode:
    def _make_kimi_workspace(self, home: Path, cwd: Path, monkeypatch) -> Path:
        monkeypatch.delenv("KIMI_CODE_HOME", raising=False)
        kimi_home = home / ".kimi-code"
        session_dir = kimi_home / "sessions" / "wd_proj" / "session_1"
        wire = session_dir / "agents" / "main" / "wire.jsonl"
        wire.parent.mkdir(parents=True)
        wire.write_text(
            json.dumps({"type": "tool_call", "timestamp": "2026-09-09T00:00:00Z"})
            + "\n"
            + json.dumps({"type": "tool_result", "timestamp": "2026-09-09T00:00:01Z"})
            + "\n"
        )
        (kimi_home / "session_index.jsonl").write_text(
            json.dumps(
                {
                    "sessionId": "session_1",
                    "sessionDir": str(session_dir),
                    "workDir": str(cwd.resolve()),
                }
            )
            + "\n"
        )
        return wire

    def test_detect_sessions_kimi_resolves_via_session_index_and_wire_glob(
        self, tmp_path, monkeypatch
    ):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        wire = self._make_kimi_workspace(home, cwd, monkeypatch)

        handles = ss.detect_sessions(cwd, "kimi-code", home=home)

        assert len(handles) == 1
        assert handles[0].path == wire
        # session_id is the session_* directory name, never the "wire" stem.
        assert handles[0].session_id == "session_1"
        assert handles[0].host == "kimi-code"

    def test_iter_events_kimi_wire_is_raw_passthrough(self, tmp_path, monkeypatch):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        self._make_kimi_workspace(home, cwd, monkeypatch)
        handle = ss.detect_sessions(cwd, "kimi-code", home=home)[0]

        events = list(ss.iter_events(handle))

        assert [e.type for e in events] == ["tool_call", "tool_result"]
        assert all(e.host == "kimi-code" for e in events)
        assert events[0].payload["type"] == "tool_call"

    def test_kimi_host_layout_has_real_entry_and_backfill_glob_finds_wire(
        self, tmp_path, monkeypatch
    ):
        """kimi-code gets a real HostLayout entry as of ENH-3422 (D5, inverting
        the prior deferral regression guard): host_layout_for("kimi-code")
        carries the wire glob, so backfill_worker's directory-glob path
        (`path_arg.glob(layout.session_glob)`) now finds the wire file."""
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        wire = self._make_kimi_workspace(home, cwd, monkeypatch)
        kimi_workspace_dir = home / ".kimi-code" / "sessions" / "wd_proj"

        from little_loops.session_store import host_layout_for

        layout = host_layout_for("kimi-code")
        assert layout.session_glob == "session_*/agents/main/wire.jsonl"
        assert list(kimi_workspace_dir.glob(layout.session_glob)) == [wire]


class TestDetectSessionsLayoutNormalizedHosts:
    """qwen/gemini/omp: iter_events payload equals the existing normalizer's
    output for the same file, host stamped; session_id per the per-host rule."""

    def test_qwen_iter_events_matches_normalize_qwen_record(self, tmp_path, fixtures_dir):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.session_store.qwen import normalize_qwen_record
        from little_loops.user_messages import encode_project_path

        project_dir = home / ".qwen" / "projects" / encode_project_path(str(cwd.resolve()))
        chats_dir = project_dir / "chats"
        chats_dir.mkdir(parents=True)
        fixture = fixtures_dir / "qwen" / "session.jsonl"
        session_file = chats_dir / "61c364ea.jsonl"
        session_file.write_text(fixture.read_text(encoding="utf-8"))

        handles = ss.detect_sessions(cwd, "qwen", home=home)
        assert len(handles) == 1
        assert handles[0].session_id == "61c364ea"

        events = list(ss.iter_events(handles[0]))
        expected = [
            r
            for r in (
                normalize_qwen_record(json.loads(line))
                for line in fixture.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            if r is not None
        ]
        assert [e.payload for e in events] == expected
        assert all(e.host == "qwen" for e in events)

    def test_gemini_iter_events_matches_normalizer_and_session_id_from_header(
        self, tmp_path, fixtures_dir
    ):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.session_store.gemini import normalize_gemini_session

        chats_dir = home / ".gemini" / "tmp" / "some-slug" / "chats"
        chats_dir.mkdir(parents=True)
        fixture = fixtures_dir / "gemini" / "session.jsonl"
        session_file = chats_dir / "session-1.jsonl"
        session_file.write_text(fixture.read_text(encoding="utf-8"))
        (home / ".gemini" / "projects.json").write_text(
            json.dumps({"projects": {str(cwd.resolve()): "some-slug"}})
        )

        handles = ss.detect_sessions(cwd, "gemini", home=home)
        assert len(handles) == 1
        # From the header, not the "session-1" filename stem.
        assert handles[0].session_id == "11111111-2222-3333-4444-555555555555"

        events = list(ss.iter_events(handles[0]))
        expected = list(normalize_gemini_session(fixture))
        assert [e.payload for e in events] == expected
        assert all(e.host == "gemini" for e in events)

    def test_omp_iter_events_matches_normalizer_and_session_id_from_header(
        self, tmp_path, fixtures_dir, monkeypatch
    ):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.delenv("PI_CONFIG_DIR", raising=False)
        from little_loops.session_store.omp import normalize_omp_session
        from little_loops.user_messages import encode_omp_session_dir

        encoded = encode_omp_session_dir(cwd, home=home)
        session_dir = home / ".omp" / "agent" / "sessions" / encoded
        session_dir.mkdir(parents=True)
        fixture = fixtures_dir / "omp" / "session.jsonl"
        session_file = session_dir / "1780000000000_11111111-2222-3333-4444-555555555555.jsonl"
        session_file.write_text(fixture.read_text(encoding="utf-8"))

        handles = ss.detect_sessions(cwd, "omp", home=home)
        assert len(handles) == 1
        # From the "type": "session" record, not the filename stem.
        assert handles[0].session_id == "11111111-2222-3333-4444-555555555555"

        events = list(ss.iter_events(handles[0]))
        expected = list(normalize_omp_session(fixture))
        assert [e.payload for e in events] == expected
        assert all(e.host == "omp" for e in events)

    def test_omp_home_relative_encoding_honors_home_override(self, tmp_path, monkeypatch):
        """A cwd under an explicit home must resolve to the home-relative
        "-<rel>" encoding computed against *that* home, proving
        encode_omp_session_dir(home=...) is honored end-to-end through
        detect_sessions (no Path.home patching reaches the right answer)."""
        decoy_home = tmp_path / "decoy-home"
        monkeypatch.setattr(Path, "home", lambda: decoy_home)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.delenv("PI_CONFIG_DIR", raising=False)
        home = tmp_path / "explicit-home"
        cwd = home / "workspace" / "project"
        cwd.mkdir(parents=True)
        from little_loops.user_messages import encode_omp_session_dir

        expected_encoded = encode_omp_session_dir(cwd, home=home)
        assert expected_encoded == "-workspace-project"
        session_dir = home / ".omp" / "agent" / "sessions" / expected_encoded
        session_dir.mkdir(parents=True)
        session_file = session_dir / "ts_sess.jsonl"
        session_file.write_text(
            json.dumps({"type": "session", "id": "sess", "cwd": str(cwd)}) + "\n"
        )

        handles = ss.detect_sessions(cwd, "omp", home=home)

        assert len(handles) == 1
        assert handles[0].path == session_file


class TestHandlesFromPathsMatchesDiscoveryD3:
    """ENH-3422 D3: handles_from_paths derives the same session_id
    detect_sessions reports for the same file, for every host whose id
    doesn't come from the plain filename stem — gemini/omp (file header),
    kimi-code (the session_* directory two levels up), and codex (the
    line-1 payload.id, mirroring _scan_rollout_tree)."""

    def test_gemini_session_id_matches_header_rule(self, tmp_path, fixtures_dir):
        fixture = fixtures_dir / "gemini" / "session.jsonl"
        session_file = tmp_path / "session-1.jsonl"
        session_file.write_text(fixture.read_text(encoding="utf-8"))

        handles = ss.handles_from_paths([session_file], "gemini")

        assert len(handles) == 1
        assert handles[0].session_id == "11111111-2222-3333-4444-555555555555"
        assert handles[0].host == "gemini"

    def test_omp_session_id_matches_header_rule(self, tmp_path, fixtures_dir):
        fixture = fixtures_dir / "omp" / "session.jsonl"
        session_file = tmp_path / "1780000000000_11111111-2222-3333-4444-555555555555.jsonl"
        session_file.write_text(fixture.read_text(encoding="utf-8"))

        handles = ss.handles_from_paths([session_file], "omp")

        assert len(handles) == 1
        assert handles[0].session_id == "11111111-2222-3333-4444-555555555555"

    def test_kimi_session_id_matches_directory_rule(self, tmp_path):
        session_dir = tmp_path / ".kimi-code" / "sessions" / "wd_proj" / "session_1"
        wire = session_dir / "agents" / "main" / "wire.jsonl"
        wire.parent.mkdir(parents=True)
        wire.write_text(
            json.dumps({"type": "tool_call", "timestamp": "2026-09-09T00:00:00Z"}) + "\n"
        )

        handles = ss.handles_from_paths([wire], "kimi-code")

        assert len(handles) == 1
        assert handles[0].session_id == "session_1"

    def test_codex_session_id_matches_header_rule(self, fixtures_dir):
        fixture = fixtures_dir / "codex" / "rollout-interactive.jsonl"
        with fixture.open(encoding="utf-8") as f:
            expected_id = json.loads(f.readline())["payload"]["id"]

        handles = ss.handles_from_paths([fixture], "codex")

        assert len(handles) == 1
        assert handles[0].session_id == expected_id


class TestBackfillRawEventsCodexHandleD3:
    """ENH-3422 D3: a codex handle's session_id (not present in the payload's
    own sessionId field) still reaches raw_events.session_id via the
    handle.session_id fallback, and _backfill_sessions seeds it."""

    def test_codex_handle_seeds_session_id_via_fallback(self, tmp_path, fixtures_dir):
        from little_loops.session_store import connect, ensure_db, rebuild
        from little_loops.session_store.lifecycle import _backfill_raw_events

        fixture = fixtures_dir / "codex" / "rollout-interactive.jsonl"
        with fixture.open(encoding="utf-8") as f:
            expected_id = json.loads(f.readline())["payload"]["id"]

        handle = ss.handles_from_paths([fixture], "codex")[0]
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            count = _backfill_raw_events(conn, [handle], host="codex")
            conn.commit()
            session_ids = {
                row[0] for row in conn.execute("SELECT DISTINCT session_id FROM raw_events")
            }
        finally:
            conn.close()
        assert count > 0
        assert session_ids == {expected_id}

        counts = rebuild(db)
        assert counts["sessions"] == 1
        conn = connect(db)
        try:
            row = conn.execute("SELECT session_id FROM sessions").fetchone()
        finally:
            conn.close()
        assert row[0] == expected_id


class TestIncludeAgentsNoOpOnNonClaudeHosts:
    def test_qwen_include_agents_is_a_no_op(self, tmp_path):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        project_dir = home / ".qwen" / "projects" / encode_project_path(str(cwd.resolve()))
        chats_dir = project_dir / "chats"
        chats_dir.mkdir(parents=True)
        (chats_dir / "sess-1.jsonl").write_text(json.dumps({"type": "user"}) + "\n")
        subagent_dir = project_dir / "subagents" / "sess-1"
        subagent_dir.mkdir(parents=True)
        (subagent_dir / "agent.jsonl").write_text(json.dumps({"type": "user"}) + "\n")

        without = ss.detect_sessions(cwd, "qwen", home=home, include_agents=False)
        with_agents = ss.detect_sessions(cwd, "qwen", home=home, include_agents=True)

        assert without == with_agents


class TestHeaderSessionId:
    def test_omp_header_scan_stops_at_first_message_line(self, tmp_path):
        path = tmp_path / "session.jsonl"
        lines = [
            json.dumps({"type": "title"}),
            json.dumps({"type": "session", "id": "sess-omp"}),
            json.dumps({"type": "message", "id": "m1", "message": {"role": "user"}}),
        ]
        path.write_text("\n".join(lines) + "\n")

        assert ss._header_session_id("omp", path) == "sess-omp"

    def test_omp_header_scan_is_bounded_stops_before_a_later_session_record(self, tmp_path):
        """No `type: "session"` record before the first message: must return
        None, never continue past the message to a later (contradicting)
        session record — proves the scan is bounded, not whole-file like
        normalize_omp_session's."""
        path = tmp_path / "session.jsonl"
        lines = [
            json.dumps({"type": "message", "id": "m1", "message": {"role": "user"}}),
            json.dumps({"type": "session", "id": "should-not-be-seen"}),
        ]
        path.write_text("\n".join(lines) + "\n")

        assert ss._header_session_id("omp", path) is None

    def test_gemini_header_from_line_one(self, tmp_path):
        path = tmp_path / "session.jsonl"
        path.write_text(json.dumps({"sessionId": "sess-gem"}) + "\n")

        assert ss._header_session_id("gemini", path) == "sess-gem"

    def test_gemini_malformed_header_returns_none(self, tmp_path):
        path = tmp_path / "session.jsonl"
        path.write_text("[1, 2]\n")

        assert ss._header_session_id("gemini", path) is None


class TestListWorkspacesLayoutHosts:
    def test_opencode_home_leak_guard(self, tmp_path, monkeypatch):
        decoy_home = tmp_path / "decoy-home-with-sessions"
        from little_loops.user_messages import encode_project_path

        decoy_project = (
            decoy_home / ".opencode" / "projects" / encode_project_path("/some/other/cwd")
        )
        decoy_project.mkdir(parents=True)
        (decoy_project / "sess.jsonl").write_text(json.dumps({"cwd": "/some/other/cwd"}) + "\n")
        monkeypatch.setattr(Path, "home", lambda: decoy_home)

        empty_home = tmp_path / "empty-home"
        empty_home.mkdir()

        assert ss.list_workspaces("opencode", home=empty_home) == []

    def test_qwen_list_workspaces(self, tmp_path):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        chats_dir = home / ".qwen" / "projects" / encode_project_path(str(cwd.resolve())) / "chats"
        chats_dir.mkdir(parents=True)
        (chats_dir / "sess.jsonl").write_text(json.dumps({"cwd": str(cwd)}) + "\n")

        assert ss.list_workspaces("qwen", home=home) == [cwd]

    def test_gemini_list_workspaces_via_projects_json(self, tmp_path):
        home = tmp_path
        cwd = Path("/repo/gemini-project")
        (home / ".gemini").mkdir(parents=True)
        (home / ".gemini" / "projects.json").write_text(
            json.dumps({"projects": {str(cwd): "some-slug"}})
        )

        assert ss.list_workspaces("gemini", home=home, existing_only=False) == [cwd]

    def test_gemini_list_workspaces_missing_registry_returns_empty(self, tmp_path):
        assert ss.list_workspaces("gemini", home=tmp_path) == []

    def test_kimi_list_workspaces_via_session_index(self, tmp_path, monkeypatch):
        home = tmp_path
        monkeypatch.delenv("KIMI_CODE_HOME", raising=False)
        kimi_home = home / ".kimi-code"
        kimi_home.mkdir(parents=True)
        cwd = Path("/repo/kimi-project")
        (kimi_home / "session_index.jsonl").write_text(
            json.dumps({"sessionId": "session_1", "sessionDir": "/x", "workDir": str(cwd)}) + "\n"
        )

        assert ss.list_workspaces("kimi-code", home=home, existing_only=False) == [cwd]

    def test_omp_list_workspaces_always_empty(self, tmp_path):
        assert ss.list_workspaces("omp", home=tmp_path) == []


class TestNonObjectJsonLinesExtended:
    """Extends TestNonObjectJsonLines to gemini and kimi (ENH-3420)."""

    def test_gemini_non_object_line1_and_set_value_do_not_raise(self, tmp_path):
        path = tmp_path / "session.jsonl"
        path.write_text(
            "[1, 2]\n"
            + json.dumps({"$set": "not-a-dict"})
            + "\n"
            + json.dumps({"id": "m1", "timestamp": "t", "type": "user", "content": []})
            + "\n"
        )

        from little_loops.session_store.gemini import normalize_gemini_session

        events = list(normalize_gemini_session(path))

        assert len(events) == 1
        assert events[0]["sessionId"] is None

    def test_parse_kimi_wire_skips_non_object_lines(self, tmp_path):
        path = tmp_path / "wire.jsonl"
        path.write_text(
            '[1, 2]\n"str"\n42\n' + json.dumps({"type": "tool_call", "timestamp": "t"}) + "\n"
        )

        events = list(ss.parse_kimi_wire(path))

        assert [e.type for e in events] == ["tool_call"]
        assert all(e.host == "kimi-code" for e in events)


class TestDetectSessionsUnionAcrossFourHosts:
    def test_union_returns_four_hosts_newest_first(self, tmp_path, monkeypatch):
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.delenv("PI_CONFIG_DIR", raising=False)
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        import os

        from little_loops.user_messages import encode_omp_session_dir, encode_project_path

        claude_dir = home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))
        claude_dir.mkdir(parents=True)
        claude_file = claude_dir / "claude-sess.jsonl"
        claude_file.write_text("{}\n")
        os.utime(claude_file, (100, 100))

        codex_rollout = home / "codex-sess.jsonl"
        _write_rollout(codex_rollout, "codex-sess", str(cwd))
        _make_state_db(
            home / ".codex" / "state_1.sqlite",
            [("codex-sess", str(codex_rollout), str(cwd), "exec", "1", "400")],
        )

        qwen_chats = home / ".qwen" / "projects" / encode_project_path(str(cwd.resolve())) / "chats"
        qwen_chats.mkdir(parents=True)
        qwen_file = qwen_chats / "qwen-sess.jsonl"
        qwen_file.write_text("{}\n")
        os.utime(qwen_file, (200, 200))

        omp_dir = home / ".omp" / "agent" / "sessions" / encode_omp_session_dir(cwd, home=home)
        omp_dir.mkdir(parents=True)
        omp_file = omp_dir / "ts_omp-sess.jsonl"
        omp_file.write_text(json.dumps({"type": "session", "id": "omp-sess"}) + "\n")
        os.utime(omp_file, (300, 300))

        handles = ss.detect_sessions(cwd, home=home)

        assert len(handles) == 4
        assert [h.host for h in handles] == ["codex", "omp", "qwen", "claude-code"]


class TestDetectSessionsStatRace:
    """BUG-2489: a session file deleted between glob() and stat() is skipped,
    not raised, in all three discovery paths (ENH-3429 — the codex-rollout
    scan fallback, claude-code, and the shared _LAYOUT_HOSTS path)."""

    def _flaky_stat(self, victim_name: str):
        real_stat = Path.stat

        def flaky(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            if self.name == victim_name:
                raise FileNotFoundError(2, "No such file or directory", str(self))
            return real_stat(self, *args, **kwargs)

        return flaky

    def test_codex_scan_fallback_skips_file_that_vanishes_before_stat(self, tmp_path, monkeypatch):
        home = tmp_path
        cwd = Path("/repo/project")
        survivor = home / ".codex" / "sessions" / "2026" / "09" / "08" / "survivor.jsonl"
        ghost = home / ".codex" / "sessions" / "2026" / "09" / "08" / "ghost.jsonl"
        _write_rollout(survivor, "sess-survivor", str(cwd))
        _write_rollout(ghost, "sess-ghost", str(cwd))

        monkeypatch.setattr(Path, "stat", self._flaky_stat("ghost.jsonl"))

        handles = ss.detect_sessions(cwd, "codex", home=home)

        assert [h.session_id for h in handles] == ["sess-survivor"]

    def test_claude_code_skips_file_that_vanishes_before_stat(self, tmp_path, monkeypatch):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        project_dir = home / ".claude" / "projects" / encode_project_path(str(cwd.resolve()))
        project_dir.mkdir(parents=True)
        (project_dir / "survivor.jsonl").write_text("{}\n")
        (project_dir / "ghost.jsonl").write_text("{}\n")

        monkeypatch.setattr(Path, "stat", self._flaky_stat("ghost.jsonl"))

        handles = ss.detect_sessions(cwd, "claude-code", home=home)

        assert [h.session_id for h in handles] == ["survivor"]

    def test_layout_host_skips_file_that_vanishes_before_stat(self, tmp_path, monkeypatch):
        home = tmp_path
        cwd = tmp_path / "project"
        cwd.mkdir()
        from little_loops.user_messages import encode_project_path

        chats_dir = home / ".qwen" / "projects" / encode_project_path(str(cwd.resolve())) / "chats"
        chats_dir.mkdir(parents=True)
        (chats_dir / "survivor.jsonl").write_text("{}\n")
        (chats_dir / "ghost.jsonl").write_text("{}\n")

        monkeypatch.setattr(Path, "stat", self._flaky_stat("ghost.jsonl"))

        handles = ss.detect_sessions(cwd, "qwen", home=home)

        assert [h.session_id for h in handles] == ["survivor"]

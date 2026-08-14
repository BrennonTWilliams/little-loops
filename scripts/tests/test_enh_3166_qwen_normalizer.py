"""ENH-3166: qwen wire-format normalization, chats/ discovery, host plumbing.

Qwen session JSONL is Claude-shaped at the envelope level but divergent in the
message body (``message.parts[]``, ``functionCall``/``functionResponse``, role
``"model"``, a disjoint tool-name vocabulary, ``provenance``/subtype fields).
These tests pin down:

- ``normalize_qwen_record`` — the record-level mapping into Claude shape
- ``host_layout_for`` — the widened descriptor (projects root, session glob,
  tool vocabulary, normalizer, ingest volume guard)
- ``discover_all_projects`` / ``_has_ll_activity`` / ``_extract_cwd_from_project``
  honoring ``chats/`` and normalized qwen ll activity
- ``raw_events.host`` stamped from the ingested files (CLI + hook worker),
  not the ambient host
- ``rebuild()`` deriving ``tool_events``/``message_events``/
  ``assistant_messages`` from qwen rows, with Claude output unchanged

Fixtures under ``fixtures/qwen/`` are sanitized captures from real qwen
0.21.6 output — the suite never reads ``~/.qwen``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.backfill_worker import main as worker_main
from little_loops.cli.logs import (
    _extract_cwd_from_project,
    _has_ll_activity,
    discover_all_projects,
)
from little_loops.session_store import (
    HostLayout,
    backfill_raw_events,
    connect,
    ensure_db,
    host_layout_for,
    normalize_qwen_record,
    qwen_skip_at_ingest,
    rebuild,
)

FIXTURES = Path(__file__).parent / "fixtures" / "qwen"
SESSION_FIXTURE = FIXTURES / "session.jsonl"
NOISE_FIXTURE = FIXTURES / "noise.jsonl"

SESSION_ID = "61c364ea-0000-4000-8000-0000000000f1"


def _load_fixture(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class TestNormalizeQwenRecord:
    """normalize_qwen_record maps qwen wire records into Claude shape."""

    def test_user_record_maps_parts_to_content_blocks(self) -> None:
        record = _load_fixture(SESSION_FIXTURE)[0]
        assert record["type"] == "user" and record["provenance"] == "real_user"

        out = normalize_qwen_record(record)

        assert out is not None
        assert out["type"] == "user"
        assert out["sessionId"] == SESSION_ID
        assert out["timestamp"] == record["timestamp"]
        message = out["message"]
        assert message["role"] == "user"
        assert message["content"] == [
            {"type": "text", "text": "Check which ll issues are still open."}
        ]

    def test_notification_user_record_is_dropped(self) -> None:
        notification = _load_fixture(NOISE_FIXTURE)[0]
        assert notification["subtype"] == "notification"

        assert normalize_qwen_record(notification) is None

    def test_mid_turn_user_message_is_dropped_despite_real_user_provenance(self) -> None:
        """provenance == real_user alone is NOT a clean discriminator (0.21.6
        stamps mid-turn injections with it too); the subtype must exclude them."""
        mid_turn = _load_fixture(NOISE_FIXTURE)[1]
        assert mid_turn["provenance"] == "real_user"
        assert mid_turn["subtype"] == "mid_turn_user_message"

        assert normalize_qwen_record(mid_turn) is None

    def test_assistant_record_maps_role_and_blocks(self) -> None:
        record = _load_fixture(SESSION_FIXTURE)[1]
        assert record["message"]["role"] == "model"

        out = normalize_qwen_record(record)

        assert out is not None
        assert out["type"] == "assistant"
        message = out["message"]
        assert message["role"] == "assistant"
        blocks = message["content"]
        # thought:true part → thinking block (preserved, never user-visible text)
        assert blocks[0] == {
            "type": "thinking",
            "thinking": "The user wants the open ll issues. I'll list them via the ll-issues CLI.",
        }
        assert blocks[1] == {"type": "text", "text": "I'll check the open issues now."}
        # functionCall → tool_use with id preserved and canonical Claude name
        assert blocks[2] == {
            "type": "tool_use",
            "id": "call_aaa111",
            "name": "Bash",
            "input": {
                "command": "ll-issues list --status open",
                "description": "List open ll issues",
            },
        }

    def test_unmapped_tool_name_passes_through(self) -> None:
        record = {
            "type": "assistant",
            "provenance": "assistant_output",
            "sessionId": "s",
            "timestamp": "2026-08-05T22:48:19.419Z",
            "message": {
                "role": "model",
                "parts": [{"functionCall": {"id": "call_x", "name": "mcp__srv__tool", "args": {}}}],
            },
        }

        out = normalize_qwen_record(record)

        assert out is not None
        block = out["message"]["content"][0]
        assert block["name"] == "mcp__srv__tool"
        assert block["id"] == "call_x"

    def test_successful_tool_result_maps_to_claude_user_record(self) -> None:
        record = _load_fixture(SESSION_FIXTURE)[2]
        assert record["type"] == "tool_result"

        out = normalize_qwen_record(record)

        assert out is not None
        # Claude carries tool results inside user records
        assert out["type"] == "user"
        block = out["message"]["content"][0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "call_aaa111"
        assert block["content"] == "ENH-3166 open P2 qwen wire-format normalizer"
        assert block["is_error"] is False

    def test_failing_tool_result_carries_is_error(self) -> None:
        record = _load_fixture(SESSION_FIXTURE)[4]
        assert record["toolCallResult"]["status"] == "error"

        out = normalize_qwen_record(record)

        assert out is not None
        block = out["message"]["content"][0]
        assert block["tool_use_id"] == "call_bbb222"
        assert block["is_error"] is True
        # string-shaped functionResponse.response (observed on failures) is kept
        assert "File not found" in str(block["content"])

    def test_system_records_have_no_claude_equivalent(self) -> None:
        for record in _load_fixture(NOISE_FIXTURE)[2:]:
            assert record["type"] == "system"
            assert normalize_qwen_record(record) is None

    def test_envelope_fields_survive_normalization(self) -> None:
        record = _load_fixture(SESSION_FIXTURE)[1]

        out = normalize_qwen_record(record)

        assert out is not None
        for key in ("uuid", "parentUuid", "sessionId", "timestamp", "cwd", "version"):
            assert out[key] == record[key]


class TestQwenSkipAtIngest:
    def test_ui_telemetry_is_skipped(self) -> None:
        telemetry = _load_fixture(NOISE_FIXTURE)[2]
        assert telemetry["subtype"] == "ui_telemetry"
        assert qwen_skip_at_ingest(telemetry) is True

    def test_other_records_are_kept(self) -> None:
        for record in _load_fixture(SESSION_FIXTURE):
            assert qwen_skip_at_ingest(record) is False
        notification = _load_fixture(NOISE_FIXTURE)[0]
        assert qwen_skip_at_ingest(notification) is False


class TestHostLayoutRegistry:
    def test_qwen_layout_widens_without_losing_enh_3165_fields(self) -> None:
        layout = host_layout_for("qwen")

        assert isinstance(layout, HostLayout)
        # ENH-3165 subagent fields unchanged
        assert layout.glob == "subagents/*"
        assert layout.parent_from == "child_dir"
        assert layout.sidecar_suffix == ".meta.json"
        assert layout.sessions_subdir == "chats"
        # ENH-3166 widening
        assert layout.name == "qwen"
        assert layout.projects_root == Path.home() / ".qwen" / "projects"
        assert layout.session_glob == "chats/*.jsonl"
        assert layout.tool_names["run_shell_command"] == "Bash"
        assert layout.tool_names["edit"] == "Edit"
        assert layout.tool_names["read_file"] == "Read"
        assert layout.tool_names["grep_search"] == "Grep"
        assert layout.tool_names["write_file"] == "Write"
        assert layout.tool_names["glob"] == "Glob"
        assert layout.tool_names["list_directory"] == "LS"
        assert layout.tool_names["todo_write"] == "TodoWrite"
        assert layout.normalize is not None
        assert layout.skip_at_ingest is not None

    def test_claude_layout_is_normalizer_free(self) -> None:
        layout = host_layout_for("claude-code")

        assert layout.projects_root == Path.home() / ".claude" / "projects"
        assert layout.session_glob == "*.jsonl"
        assert layout.sessions_subdir == ""
        assert layout.normalize is None
        assert layout.skip_at_ingest is None
        assert layout.tool_names == {}

    def test_registered_claude_shaped_hosts_get_projects_roots(self) -> None:
        assert host_layout_for("codex").projects_root == Path.home() / ".codex" / "projects"
        assert host_layout_for("opencode").projects_root == Path.home() / ".opencode" / "projects"
        assert host_layout_for("pi").projects_root == Path.home() / ".pi" / "projects"

    def test_unknown_host_lenient_subagent_fields_strict_projects_root(self) -> None:
        layout = host_layout_for("mystery-cli")

        assert layout.name == "mystery-cli"
        assert layout.projects_root is None
        # ENH-3165 leniency survives for the subagent fields
        assert layout.glob == "*/subagents"
        assert layout.parent_from == "parent_dir"
        assert layout.sessions_subdir == ""

    def test_kimi_code_has_no_static_projects_root(self) -> None:
        assert host_layout_for("kimi-code").projects_root is None


class TestQwenDiscovery:
    """discover_all_projects + walkers honor chats/ and normalized records."""

    def _make_qwen_home(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        home = tmp_path / "home"
        project = tmp_path / "work" / "myproj"
        project.mkdir(parents=True)
        encoded = str(project).replace("/", "-")
        chats = home / ".qwen" / "projects" / encoded / "chats"
        chats.mkdir(parents=True)
        text = SESSION_FIXTURE.read_text(encoding="utf-8").replace(
            "/tmp/ll-qwen-fixture", str(project)
        )
        (chats / "61c364ea.jsonl").write_text(text, encoding="utf-8")
        return home, project, chats.parent

    def test_discover_all_projects_finds_qwen_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home, project, project_dir = self._make_qwen_home(tmp_path)
        logger = logging.getLogger("little_loops.cli.logs")

        with patch("pathlib.Path.home", return_value=home):
            found = discover_all_projects(logger, host="qwen")

        assert found == [project]

    def test_has_ll_activity_detects_normalized_run_shell_command(self, tmp_path: Path) -> None:
        """A run_shell_command functionCall whose args.command matches ll-\\w+
        must register as ll activity once normalized (not just Claude Bash)."""
        home, _project, project_dir = self._make_qwen_home(tmp_path)

        with patch("pathlib.Path.home", return_value=home):
            assert _has_ll_activity(project_dir, host_layout_for("qwen")) is True

    def test_extract_cwd_honors_chats_glob(self, tmp_path: Path) -> None:
        home, project, project_dir = self._make_qwen_home(tmp_path)

        with patch("pathlib.Path.home", return_value=home):
            cwd = _extract_cwd_from_project(project_dir, host_layout_for("qwen"))

        assert cwd == project


class TestRawEventsHostPlumbing:
    """raw_events.host reflects the ingested files, not the ambient host."""

    def test_explicit_host_stamps_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)

        backfill_raw_events(db, jsonl_files=[SESSION_FIXTURE], since_ts=0.0, host="qwen")

        conn = connect(db)
        try:
            hosts = {row[0] for row in conn.execute("SELECT DISTINCT host FROM raw_events")}
        finally:
            conn.close()
        assert hosts == {"qwen"}

    def test_ui_telemetry_skipped_at_ingest_for_qwen(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """~47% of qwen volume is ui_telemetry with no rebuild consumer —
        skip it at ingest (documented decision, ENH-3166)."""
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)

        backfill_raw_events(db, jsonl_files=[NOISE_FIXTURE], since_ts=0.0, host="qwen")

        conn = connect(db)
        try:
            rows = conn.execute("SELECT raw_line FROM raw_events").fetchall()
        finally:
            conn.close()
        from little_loops.session_store.writers import _unpack_payload

        unpacked = [_unpack_payload(raw) for (raw,) in rows]
        telemetry = sum(1 for line in unpacked if '"ui_telemetry"' in line)
        # 6 fixture lines minus the 2 ui_telemetry records (the remaining
        # system records — slash_command, at_command — still ingest verbatim)
        assert len(unpacked) == 4
        assert telemetry == 0

    def test_no_host_stamps_ambient(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)
        claude_jsonl = tmp_path / "claude.jsonl"
        claude_jsonl.write_text(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "cs1",
                    "timestamp": "2026-08-05T10:00:00Z",
                    "message": {"role": "user", "content": "hello"},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        backfill_raw_events(db, jsonl_files=[claude_jsonl], since_ts=0.0)

        conn = connect(db)
        try:
            hosts = {row[0] for row in conn.execute("SELECT DISTINCT host FROM raw_events")}
        finally:
            conn.close()
        assert hosts == {"claude-code"}


class TestRebuildQwenRecords:
    """rebuild() derives cache tables from qwen raw_events rows."""

    def _ingest_qwen(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)
        backfill_raw_events(
            db, jsonl_files=[SESSION_FIXTURE, NOISE_FIXTURE], since_ts=0.0, host="qwen"
        )
        return db

    def test_rebuild_derives_tool_events_with_canonical_names(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = self._ingest_qwen(tmp_path, monkeypatch)

        counts = rebuild(db)

        assert counts["tools"] == 2
        conn = connect(db)
        try:
            names = sorted(row[0] for row in conn.execute("SELECT tool_name FROM tool_events"))
        finally:
            conn.close()
        assert names == ["Bash", "Read"]

    def test_rebuild_message_events_only_real_user_no_subtype(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """notification and mid_turn_user_message must not poison
        message_events; verified against a fixture containing all three."""
        db = self._ingest_qwen(tmp_path, monkeypatch)

        counts = rebuild(db)

        assert counts["messages"] == 1
        conn = connect(db)
        try:
            contents = [row[0] for row in conn.execute("SELECT content FROM message_events")]
        finally:
            conn.close()
        assert contents == ["Check which ll issues are still open."]

    def test_rebuild_assistant_messages_drop_thinking_and_count_tools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = self._ingest_qwen(tmp_path, monkeypatch)

        counts = rebuild(db)

        assert counts["assistant_messages"] == 3
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT content, tool_use_count FROM assistant_messages ORDER BY ts"
            ).fetchall()
        finally:
            conn.close()
        assert rows[0][0] == "I'll check the open issues now."
        assert rows[0][1] == 1
        # thought:true text never surfaces as assistant content
        assert all("ll-issues CLI" not in row[0] for row in rows)

    def test_rebuild_seeds_session_from_qwen_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = self._ingest_qwen(tmp_path, monkeypatch)

        counts = rebuild(db)

        assert counts["sessions"] == 1
        conn = connect(db)
        try:
            row = conn.execute("SELECT session_id FROM sessions").fetchone()
        finally:
            conn.close()
        assert row[0] == SESSION_ID

    def test_system_noise_yields_no_derived_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = self._ingest_qwen(tmp_path, monkeypatch)

        counts = rebuild(db)

        assert counts["skill_events"] == 0
        assert counts["usage_events"] == 0


class TestClaudeParity:
    """Claude-host ingestion/rebuild behavior is unchanged (byte-identical AC)."""

    CLAUDE_LINES = [
        {
            "type": "user",
            "sessionId": "claude-s1",
            "timestamp": "2026-08-05T10:00:00Z",
            "cwd": "/tmp/claude-proj",
            "message": {"role": "user", "content": "run the ll checks"},
        },
        {
            "type": "assistant",
            "sessionId": "claude-s1",
            "timestamp": "2026-08-05T10:00:05Z",
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-1",
                "content": [
                    {"type": "text", "text": "Running checks now."},
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "Bash",
                        "input": {"command": "ll-check all"},
                    },
                ],
                "usage": {"input_tokens": 100, "output_tokens": 20},
            },
        },
    ]

    def test_claude_rebuild_counts_and_lines_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        db = tmp_path / "history.db"
        ensure_db(db)
        jsonl = tmp_path / "claude.jsonl"
        original_lines = [json.dumps(r) for r in self.CLAUDE_LINES]
        jsonl.write_text("\n".join(original_lines) + "\n", encoding="utf-8")

        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)
        counts = rebuild(db)

        assert counts["sessions"] == 1
        assert counts["tools"] == 1
        assert counts["messages"] == 1
        assert counts["assistant_messages"] == 1
        assert counts["usage_events"] == 1

        # Claude rows bypass the loads/normalize/dumps round-trip entirely:
        # raw_events cursor replay yields the verbatim source lines.
        from little_loops.session_store.writers import _iter_events

        conn = connect(db)
        try:
            rows = list(
                _iter_events(conn.execute("SELECT raw_line, source_path, host FROM raw_events"))
            )
        finally:
            conn.close()
        assert [line for line, _label in rows] == original_lines


class TestBackfillWorkerHost:
    """The SessionStart hook worker stamps the ingested host (ENH-3166)."""

    def _make_qwen_project(self, tmp_path: Path) -> tuple[Path, Path]:
        project = tmp_path / "proj"
        chats = project / "chats"
        chats.mkdir(parents=True)
        (chats / "61c364ea.jsonl").write_text(
            SESSION_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        return project, tmp_path / "history.db"

    def test_dir_arg_finds_chats_and_stamps_host(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        project, db = self._make_qwen_project(tmp_path)

        exit_code = worker_main([str(db), str(project), "--host", "qwen"])

        assert exit_code == 0
        conn = connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
            hosts = {row[0] for row in conn.execute("SELECT DISTINCT host FROM raw_events")}
        finally:
            conn.close()
        assert count == 6
        assert hosts == {"qwen"}

    def test_flags_are_position_insensitive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LL_HOST_CLI", "claude-code")
        project, db = self._make_qwen_project(tmp_path)

        exit_code = worker_main([str(db), "--host", "qwen", str(project), "--rebuild"])

        assert exit_code == 0
        conn = connect(db)
        try:
            hosts = {row[0] for row in conn.execute("SELECT DISTINCT host FROM raw_events")}
            sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        finally:
            conn.close()
        assert hosts == {"qwen"}
        assert sessions == 1  # --rebuild ran


class TestSessionStartHookPassesHost:
    """session_start spawns the worker with --host from the adapter envelope."""

    def _mock_popen(self, monkeypatch: pytest.MonkeyPatch) -> list[list]:
        calls: list[list] = []

        class _FakePopen:
            def __init__(self_inner, args, **kw):
                calls.append(list(args))

        monkeypatch.setattr("little_loops.hooks.session_start.subprocess.Popen", _FakePopen)
        return calls

    def test_worker_argv_carries_host_and_project_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.hooks.session_start import handle
        from little_loops.hooks.types import LLHookEvent

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir(exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps({}))
        monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)
        monkeypatch.setenv("LL_HOOK_HOST", "qwen")
        import little_loops.user_messages as um

        monkeypatch.setattr(um, "get_project_folder", lambda *a, **kw: tmp_path)
        calls = self._mock_popen(monkeypatch)

        handle(LLHookEvent(host="qwen", intent="session_start", payload={}))

        assert len(calls) == 1
        argv = calls[0]
        assert "--host" in argv
        assert argv[argv.index("--host") + 1] == "qwen"
        # The worker resolves chats/ via the layout's session_glob; the hook
        # passes the project root, not a pre-joined chats/ path.
        assert str(tmp_path) in argv
        assert str(tmp_path / "chats") not in argv

"""Tests for LLHookEvent and LLHookResult dataclasses (FEAT-1448).

Mirrors the round-trip pattern in ``test_events.py:TestLLEvent`` (separate
methods for ``to_dict``, ``from_dict``, ``roundtrip``, JSON serializability),
plus a ``test_to_dict_skips_none`` for the new None-skipping behavior
introduced on these dataclasses.
"""

from __future__ import annotations

import json
import subprocess
import sys

from little_loops.hooks.types import LLHookEvent, LLHookResult


class TestLLHookEvent:
    """Tests for the LLHookEvent dataclass."""

    def test_creation(self) -> None:
        """LLHookEvent can be constructed with host plus optional fields."""
        event = LLHookEvent(
            host="claude-code",
            intent="pre_compact",
            timestamp="2026-05-12T12:00:00Z",
            payload={"reason": "auto"},
            session_id="abc123",
            cwd="/repo",
        )
        assert event.host == "claude-code"
        assert event.intent == "pre_compact"
        assert event.timestamp == "2026-05-12T12:00:00Z"
        assert event.payload == {"reason": "auto"}
        assert event.session_id == "abc123"
        assert event.cwd == "/repo"

    def test_host_required(self) -> None:
        """host is a required positional field — defaults to empty string only via from_dict fallback."""
        event = LLHookEvent(host="opencode")
        assert event.host == "opencode"
        # Other fields have sensible defaults
        assert event.intent == ""
        assert event.timestamp == ""
        assert event.payload == {}
        assert event.session_id is None
        assert event.cwd is None

    def test_to_dict(self) -> None:
        """to_dict produces wire-format dict with all populated fields."""
        event = LLHookEvent(
            host="claude-code",
            intent="session_start",
            timestamp="2026-05-12T12:05:00Z",
            payload={"matcher": "*"},
            session_id="sess-1",
            cwd="/repo",
        )
        d = event.to_dict()
        assert d["host"] == "claude-code"
        assert d["intent"] == "session_start"
        assert d["ts"] == "2026-05-12T12:05:00Z"
        assert d["payload"] == {"matcher": "*"}
        assert d["session_id"] == "sess-1"
        assert d["cwd"] == "/repo"
        # Wire format uses "ts" not "timestamp"
        assert "timestamp" not in d

    def test_to_dict_skips_none(self) -> None:
        """to_dict omits optional fields when they are None."""
        event = LLHookEvent(host="opencode", intent="pre_tool_use")
        d = event.to_dict()
        assert "session_id" not in d
        assert "cwd" not in d
        # Required-ish fields still appear (even if empty)
        assert d["host"] == "opencode"
        assert d["intent"] == "pre_tool_use"

    def test_to_dict_json_serializable(self) -> None:
        """to_dict output is JSON serializable."""
        event = LLHookEvent(host="claude-code", intent="session_end")
        json.dumps(event.to_dict())  # must not raise

    def test_from_dict(self) -> None:
        """from_dict reconstructs LLHookEvent from a flat dict."""
        raw = {
            "host": "claude-code",
            "intent": "pre_compact",
            "ts": "2026-05-12T12:00:00Z",
            "payload": {"reason": "manual"},
            "session_id": "abc123",
            "cwd": "/repo",
        }
        event = LLHookEvent.from_dict(raw)
        assert event.host == "claude-code"
        assert event.intent == "pre_compact"
        assert event.timestamp == "2026-05-12T12:00:00Z"
        assert event.payload == {"reason": "manual"}
        assert event.session_id == "abc123"
        assert event.cwd == "/repo"

    def test_from_dict_accepts_timestamp_alias(self) -> None:
        """from_dict accepts the field-name alias 'timestamp' as well as wire-key 'ts'."""
        raw = {"host": "opencode", "timestamp": "2026-05-12T12:00:00Z"}
        event = LLHookEvent.from_dict(raw)
        assert event.timestamp == "2026-05-12T12:00:00Z"

    def test_from_dict_missing_fields(self) -> None:
        """from_dict tolerates missing fields with defaults."""
        event = LLHookEvent.from_dict({})
        assert event.host == ""
        assert event.intent == ""
        assert event.timestamp == ""
        assert event.payload == {}
        assert event.session_id is None
        assert event.cwd is None

    def test_roundtrip(self) -> None:
        """to_dict -> from_dict preserves all data."""
        original = LLHookEvent(
            host="claude-code",
            intent="post_tool_use",
            timestamp="2026-05-12T12:00:00Z",
            payload={"tool": "Bash", "exit_code": 0},
            session_id="sess-7",
            cwd="/home/user/proj",
        )
        restored = LLHookEvent.from_dict(original.to_dict())
        assert restored.host == original.host
        assert restored.intent == original.intent
        assert restored.timestamp == original.timestamp
        assert restored.payload == original.payload
        assert restored.session_id == original.session_id
        assert restored.cwd == original.cwd

    def test_roundtrip_with_none_optionals(self) -> None:
        """Roundtrip preserves None for optional fields."""
        original = LLHookEvent(host="claude-code", intent="user_prompt_submit")
        restored = LLHookEvent.from_dict(original.to_dict())
        assert restored.session_id is None
        assert restored.cwd is None


class TestLLHookResult:
    """Tests for the LLHookResult dataclass."""

    def test_creation_defaults(self) -> None:
        """LLHookResult constructs with sensible defaults (pass, no feedback)."""
        result = LLHookResult()
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.decision is None
        assert result.data == {}
        assert result.stdout is None

    def test_creation_full(self) -> None:
        """LLHookResult constructs with all fields populated."""
        result = LLHookResult(
            exit_code=2,
            feedback="duplicate issue ID",
            decision="deny",
            data={"existing_id": "FEAT-042"},
            stdout="duplicate issue ID detected\n",
        )
        assert result.exit_code == 2
        assert result.feedback == "duplicate issue ID"
        assert result.decision == "deny"
        assert result.data == {"existing_id": "FEAT-042"}
        assert result.stdout == "duplicate issue ID detected\n"

    def test_to_dict_minimal(self) -> None:
        """to_dict on a default result yields only exit_code (no None or empty noise)."""
        d = LLHookResult().to_dict()
        assert d == {"exit_code": 0}

    def test_to_dict_skips_none(self) -> None:
        """to_dict omits feedback/decision/stdout when None and data when empty."""
        result = LLHookResult(exit_code=1)
        d = result.to_dict()
        assert d == {"exit_code": 1}
        assert "feedback" not in d
        assert "decision" not in d
        assert "data" not in d
        assert "stdout" not in d

    def test_to_dict_full(self) -> None:
        """to_dict includes every populated field."""
        result = LLHookResult(
            exit_code=2,
            feedback="blocked",
            decision="deny",
            data={"reason": "duplicate"},
            stdout="blocked: duplicate id\n",
        )
        d = result.to_dict()
        assert d["exit_code"] == 2
        assert d["feedback"] == "blocked"
        assert d["decision"] == "deny"
        assert d["data"] == {"reason": "duplicate"}
        assert d["stdout"] == "blocked: duplicate id\n"

    def test_to_dict_json_serializable(self) -> None:
        """to_dict output is JSON serializable."""
        result = LLHookResult(exit_code=0, feedback="ok", data={"k": "v"})
        json.dumps(result.to_dict())  # must not raise

    def test_from_dict(self) -> None:
        """from_dict reconstructs LLHookResult from a flat dict."""
        raw = {
            "exit_code": 2,
            "feedback": "blocked",
            "decision": "deny",
            "data": {"reason": "duplicate"},
            "stdout": "blocked: duplicate id\n",
        }
        result = LLHookResult.from_dict(raw)
        assert result.exit_code == 2
        assert result.feedback == "blocked"
        assert result.decision == "deny"
        assert result.data == {"reason": "duplicate"}
        assert result.stdout == "blocked: duplicate id\n"

    def test_from_dict_missing_fields(self) -> None:
        """from_dict tolerates missing fields with defaults."""
        result = LLHookResult.from_dict({})
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.decision is None
        assert result.data == {}
        assert result.stdout is None

    def test_roundtrip(self) -> None:
        """to_dict -> from_dict preserves all data."""
        original = LLHookResult(
            exit_code=2,
            feedback="blocked",
            decision="deny",
            data={"reason": "duplicate", "id": "BUG-1"},
            stdout="blocked: duplicate id\n",
        )
        restored = LLHookResult.from_dict(original.to_dict())
        assert restored.exit_code == original.exit_code
        assert restored.feedback == original.feedback
        assert restored.decision == original.decision
        assert restored.data == original.data
        assert restored.stdout == original.stdout

    def test_roundtrip_minimal(self) -> None:
        """Roundtrip on a minimal result preserves None/empty defaults."""
        original = LLHookResult()
        restored = LLHookResult.from_dict(original.to_dict())
        assert restored.exit_code == 0
        assert restored.feedback is None
        assert restored.decision is None
        assert restored.data == {}
        assert restored.stdout is None


class TestHooksMainModule:
    """Smoke tests for the ``python -m little_loops.hooks`` CLI dispatcher."""

    def test_module_dispatch_exit_zero(self) -> None:
        """``python -m little_loops.hooks`` returns exit 0 and prints usage to stderr."""
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "little_loops.hooks" in result.stderr

    def test_dispatch_pre_compact_happy_path(self, tmp_path) -> None:
        """``pre_compact`` intent reads stdin JSON, exits 2, and prints feedback to stderr."""
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "pre_compact"],
            input=json.dumps({"transcript_path": "/tmp/t.jsonl"}),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 2
        assert "Task state preserved" in result.stderr
        assert (tmp_path / ".ll" / "ll-precompact-state.json").is_file()

    def test_dispatch_pre_compact_handoff_happy_path(self, tmp_path) -> None:
        """``pre_compact_handoff`` intent reads stdin JSON, exits 2, and writes the prompt file."""
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "pre_compact_handoff"],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 2
        assert "Session handoff snapshot written" in result.stderr
        assert (tmp_path / ".ll" / "ll-continue-prompt.md").is_file()

    def test_dispatch_session_start_happy_path(self, tmp_path) -> None:
        """``session_start`` intent runs the handler and exits 0 (no config in tmp dir)."""
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "session_start"],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        # No config in tmp_path → the "No config found" warning is emitted to stderr.
        assert "No config found" in result.stderr

    def test_dispatch_user_prompt_submit_happy_path(self, tmp_path) -> None:
        """``user_prompt_submit`` intent runs the handler and exits 0.

        With no config in tmp_path and a prompt in the payload, the handler
        emits the no-config reminder on stdout and exits 0.
        """
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "user_prompt_submit"],
            input=json.dumps({"prompt": "fix the authentication bug in this project"}),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0, f"returncode={result.returncode}; stderr={result.stderr!r}"
        # No config in tmp_path → the "No config found" reminder is emitted on stdout.
        assert "No config found" in result.stdout

    def test_dispatch_post_tool_use_happy_path(self, tmp_path) -> None:
        """``post_tool_use`` intent runs the byte-tracking handler and exits 0 (FEAT-1623).

        The handler persists per-tool byte metrics into ``.ll/history.db`` when
        ``analytics.enabled`` is true; with no config in ``tmp_path``, the
        analytics guard short-circuits the write so the subprocess emits no
        stdout/stderr and the SQLite database is never created.
        """
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "post_tool_use"],
            input=json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "ls"},
                    "tool_response": {"exit_code": 0},
                }
            ),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0, f"returncode={result.returncode}; stderr={result.stderr!r}"
        # No config in tmp_path → analytics guard skips the write; no output.
        assert result.stdout == ""
        assert result.stderr == ""
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_dispatch_pre_tool_use_happy_path(self, tmp_path) -> None:
        """``pre_tool_use`` intent runs the opt-in no-op handler and exits 0 (FEAT-1489).

        The handler is registered for dispatch but not invoked by any default
        host wiring — users opt in via host config. The CLI path is exercised
        here to confirm the dispatcher table includes it.
        """
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "pre_tool_use"],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0, f"returncode={result.returncode}; stderr={result.stderr!r}"
        assert result.stdout == ""
        assert result.stderr == ""

    def test_dispatch_edit_batch_nudge_happy_path(self, tmp_path) -> None:
        """``edit_batch_nudge`` exits 2 with a batching reminder once the unbatched run trips (FEAT-2470).

        The handler is stateful: a single Edit no longer nudges. Seed the
        per-session counter one below the threshold with a stale ``last_ts`` so
        this Edit reads as unbatched and reaches ``_NUDGE_THRESHOLD``; the CLI
        dispatcher then writes the feedback to stderr and propagates exit 2.
        """
        from little_loops.hooks.edit_batch_nudge import _NUDGE_THRESHOLD

        state_file = tmp_path / ".ll" / "ll-edit-batch-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        # run just below threshold, last_ts=0 → large gap → counts as unbatched.
        state_file.write_text(
            json.dumps({"session_id": "s1", "run": _NUDGE_THRESHOLD - 1, "last_ts": 0.0})
        )
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "edit_batch_nudge"],
            input=json.dumps(
                {"tool_name": "Edit", "session_id": "s1", "tool_input": {"file_path": "/tmp/x"}}
            ),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 2, f"returncode={result.returncode}; stderr={result.stderr!r}"
        assert "batch" in result.stderr.lower()

    def test_dispatch_edit_batch_nudge_single_edit_silent(self, tmp_path) -> None:
        """A lone Edit no longer nudges — the stateful run starts at 1 (FEAT-2470)."""
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "edit_batch_nudge"],
            input=json.dumps({"tool_name": "Edit", "session_id": "s1"}),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0, f"returncode={result.returncode}; stderr={result.stderr!r}"
        assert result.stderr == ""

    def test_dispatch_edit_batch_nudge_passthrough(self, tmp_path) -> None:
        """``edit_batch_nudge`` exits 0 with no feedback for a non-edit tool (FEAT-2470)."""
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "edit_batch_nudge"],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0, f"returncode={result.returncode}; stderr={result.stderr!r}"
        assert result.stderr == ""

    def test_dispatch_session_end_happy_path(self, tmp_path) -> None:
        """``session_end`` intent runs the handler and exits 0 (no config in tmp dir).

        With no config in tmp_path the handler short-circuits before producing
        any output, so both stdout and stderr must be empty strings.
        """
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "session_end"],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0, f"returncode={result.returncode}; stderr={result.stderr!r}"
        assert result.stdout == ""
        assert result.stderr == ""

    def test_dispatch_unknown_intent(self) -> None:
        """Unknown intent name exits non-zero with an error message on stderr."""
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "no_such_intent"],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        assert "no_such_intent" in result.stderr or "Unknown intent" in result.stderr

    def test_dispatch_pre_compact_empty_stdin(self, tmp_path) -> None:
        """Empty stdin → returncode 0 noop (malformed-payload branch)."""
        result = subprocess.run(
            [sys.executable, "-m", "little_loops.hooks", "pre_compact"],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0

    def test_ll_hook_host_env_var_propagates(self, monkeypatch, tmp_path) -> None:
        """LL_HOOK_HOST env var sets LLHookEvent.host on the dispatched event.

        Stubs the dispatch table with a handler that captures the event, then
        runs main_hooks() in-process to verify the host field on the event the
        handler receives.
        """
        import io
        import os

        from little_loops import hooks as hooks_pkg

        captured: list[LLHookEvent] = []

        def stub_handler(event: LLHookEvent) -> LLHookResult:
            captured.append(event)
            return LLHookResult(exit_code=0)

        monkeypatch.setattr(hooks_pkg, "_dispatch_table", lambda: {"session_start": stub_handler})
        monkeypatch.setenv("LL_HOOK_HOST", "opencode")
        monkeypatch.setattr(sys, "argv", ["little_loops.hooks", "session_start"])
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        monkeypatch.chdir(tmp_path)

        # Force isatty() to return False so main_hooks reads stdin.
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

        rc = hooks_pkg.main_hooks()
        assert rc == 0
        event = captured[0]
        assert event.host == "opencode"
        assert event.intent == "session_start"
        assert os.path.realpath(event.cwd or "") == os.path.realpath(str(tmp_path))

    def test_ll_hook_host_env_var_propagates_codex(self, monkeypatch, tmp_path) -> None:
        """LL_HOOK_HOST=codex sets LLHookEvent.host on the dispatched event (FEAT-957).

        Parallel of ``test_ll_hook_host_env_var_propagates`` to lock in the
        codex value, since the Python dispatcher reads ``LL_HOOK_HOST`` and
        the Codex adapter sets it to ``"codex"`` on the subprocess.
        """
        import io

        from little_loops import hooks as hooks_pkg

        captured: list[LLHookEvent] = []

        def stub_handler(event: LLHookEvent) -> LLHookResult:
            captured.append(event)
            return LLHookResult(exit_code=0)

        monkeypatch.setattr(hooks_pkg, "_dispatch_table", lambda: {"session_start": stub_handler})
        monkeypatch.setenv("LL_HOOK_HOST", "codex")
        monkeypatch.setattr(sys, "argv", ["little_loops.hooks", "session_start"])
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

        rc = hooks_pkg.main_hooks()
        assert rc == 0
        event = captured[0]
        assert event.host == "codex"
        assert event.intent == "session_start"

    def test_ll_hook_host_defaults_to_claude_code(self, monkeypatch, tmp_path) -> None:
        """Without LL_HOOK_HOST set, the host defaults to ``claude-code``."""
        import io

        from little_loops import hooks as hooks_pkg

        captured: list[LLHookEvent] = []

        def stub_handler(event: LLHookEvent) -> LLHookResult:
            captured.append(event)
            return LLHookResult(exit_code=0)

        monkeypatch.setattr(hooks_pkg, "_dispatch_table", lambda: {"session_start": stub_handler})
        monkeypatch.delenv("LL_HOOK_HOST", raising=False)
        monkeypatch.setattr(sys, "argv", ["little_loops.hooks", "session_start"])
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

        rc = hooks_pkg.main_hooks()
        assert rc == 0
        assert captured[0].host == "claude-code"

    def test_main_hooks_session_id_propagates_from_payload(self, monkeypatch, tmp_path) -> None:
        """session_id in the host payload reaches LLHookEvent.session_id (ENH-2495)."""
        import io

        from little_loops import hooks as hooks_pkg

        captured: list[LLHookEvent] = []

        def stub_handler(event: LLHookEvent) -> LLHookResult:
            captured.append(event)
            return LLHookResult(exit_code=0)

        monkeypatch.setattr(hooks_pkg, "_dispatch_table", lambda: {"session_start": stub_handler})
        monkeypatch.setattr(sys, "argv", ["little_loops.hooks", "session_start"])
        monkeypatch.setattr(sys, "stdin", io.StringIO('{"session_id": "abc123"}'))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

        rc = hooks_pkg.main_hooks()
        assert rc == 0
        assert captured[0].session_id == "abc123"

    def test_main_hooks_session_id_defaults_to_none(self, monkeypatch, tmp_path) -> None:
        """Missing session_id in the host payload leaves LLHookEvent.session_id None (ENH-2495)."""
        import io

        from little_loops import hooks as hooks_pkg

        captured: list[LLHookEvent] = []

        def stub_handler(event: LLHookEvent) -> LLHookResult:
            captured.append(event)
            return LLHookResult(exit_code=0)

        monkeypatch.setattr(hooks_pkg, "_dispatch_table", lambda: {"session_start": stub_handler})
        monkeypatch.setattr(sys, "argv", ["little_loops.hooks", "session_start"])
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

        rc = hooks_pkg.main_hooks()
        assert rc == 0
        assert captured[0].session_id is None

    def test_dispatch_table_merges_hook_intent_registry(self, monkeypatch) -> None:
        """_dispatch_table() merges _HOOK_INTENT_REGISTRY with built-ins; built-ins win on collision.

        Registry isolation: _HOOK_INTENT_REGISTRY is module-level mutable state, so
        each test mutating it must reset via monkeypatch to prevent test order coupling.
        """
        from little_loops import hooks as hooks_pkg
        from little_loops.hooks import _dispatch_table

        def custom_handler(event: LLHookEvent) -> LLHookResult:
            return LLHookResult(exit_code=0)

        def shadow_handler(event: LLHookEvent) -> LLHookResult:
            return LLHookResult(exit_code=99)

        monkeypatch.setattr(
            hooks_pkg,
            "_HOOK_INTENT_REGISTRY",
            {"my_intent": custom_handler, "session_start": shadow_handler},
        )

        table = _dispatch_table()
        # Extension intent appears alongside built-ins.
        assert "my_intent" in table
        assert table["my_intent"] is custom_handler
        assert "pre_compact" in table
        assert "pre_compact_handoff" in table
        assert "session_end" in table
        assert "session_start" in table
        # Built-in shadows extension on collision.
        assert table["session_start"] is not shadow_handler

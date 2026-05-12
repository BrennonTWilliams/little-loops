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

    def test_creation_full(self) -> None:
        """LLHookResult constructs with all fields populated."""
        result = LLHookResult(
            exit_code=2,
            feedback="duplicate issue ID",
            decision="deny",
            data={"existing_id": "FEAT-042"},
        )
        assert result.exit_code == 2
        assert result.feedback == "duplicate issue ID"
        assert result.decision == "deny"
        assert result.data == {"existing_id": "FEAT-042"}

    def test_to_dict_minimal(self) -> None:
        """to_dict on a default result yields only exit_code (no None or empty noise)."""
        d = LLHookResult().to_dict()
        assert d == {"exit_code": 0}

    def test_to_dict_skips_none(self) -> None:
        """to_dict omits feedback/decision when None and data when empty."""
        result = LLHookResult(exit_code=1)
        d = result.to_dict()
        assert d == {"exit_code": 1}
        assert "feedback" not in d
        assert "decision" not in d
        assert "data" not in d

    def test_to_dict_full(self) -> None:
        """to_dict includes every populated field."""
        result = LLHookResult(
            exit_code=2,
            feedback="blocked",
            decision="deny",
            data={"reason": "duplicate"},
        )
        d = result.to_dict()
        assert d["exit_code"] == 2
        assert d["feedback"] == "blocked"
        assert d["decision"] == "deny"
        assert d["data"] == {"reason": "duplicate"}

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
        }
        result = LLHookResult.from_dict(raw)
        assert result.exit_code == 2
        assert result.feedback == "blocked"
        assert result.decision == "deny"
        assert result.data == {"reason": "duplicate"}

    def test_from_dict_missing_fields(self) -> None:
        """from_dict tolerates missing fields with defaults."""
        result = LLHookResult.from_dict({})
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.decision is None
        assert result.data == {}

    def test_roundtrip(self) -> None:
        """to_dict -> from_dict preserves all data."""
        original = LLHookResult(
            exit_code=2,
            feedback="blocked",
            decision="deny",
            data={"reason": "duplicate", "id": "BUG-1"},
        )
        restored = LLHookResult.from_dict(original.to_dict())
        assert restored.exit_code == original.exit_code
        assert restored.feedback == original.feedback
        assert restored.decision == original.decision
        assert restored.data == original.data

    def test_roundtrip_minimal(self) -> None:
        """Roundtrip on a minimal result preserves None/empty defaults."""
        original = LLHookResult()
        restored = LLHookResult.from_dict(original.to_dict())
        assert restored.exit_code == 0
        assert restored.feedback is None
        assert restored.decision is None
        assert restored.data == {}


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

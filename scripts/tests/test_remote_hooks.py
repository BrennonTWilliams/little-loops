"""Hook, worker and CLI behavior under a remote history backend (FEAT-3535, Step 7).

``SessionStart`` never migrates or rebuilds a remote store and never lets its digest read
outlast the hook timeout; the detached backfill worker refuses a rebuild; a transcript path
recorded on another machine is labelled, not an error.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from little_loops.hooks.session_start import handle
from little_loops.session_store import db as db_mod
from little_loops.session_store import remote_schema, remote_telemetry
from little_loops.session_store.hrana import HranaClient
from tests.hrana_stub import HranaStub
from tests.test_hook_session_start import _event

TOKEN = "sentinel-token-DO-NOT-LEAK"


@pytest.fixture
def remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HranaStub]:
    stub = HranaStub(token=TOKEN).start()
    monkeypatch.setenv("LL_HISTORY_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("LL_HISTORY_URL", stub.url)
    monkeypatch.delenv("LL_HISTORY_DB", raising=False)
    monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)
    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text(
        json.dumps(
            {
                "history": {
                    "backend": {
                        "provider": "libsql",
                        "url_env": "LL_HISTORY_URL",
                        "project_id": "acme-api",
                    }
                }
            }
        )
    )
    monkeypatch.chdir(tmp_path)
    remote_schema.clear_verification_cache()
    remote_telemetry.reset_for_tests()
    db_mod.clear_backend_config_cache()
    remote_schema.migrate_remote(HranaClient(stub.url, TOKEN), "acme-api")
    try:
        yield stub
    finally:
        stub.stop()
        remote_schema.clear_verification_cache()
        db_mod.clear_backend_config_cache()


class TestSessionStart:
    def _popen(self, monkeypatch: pytest.MonkeyPatch) -> list[list]:
        calls: list[list] = []

        class _FakePopen:
            def __init__(self_inner, args, **kw):  # noqa: N805
                calls.append(list(args))

        monkeypatch.setattr("little_loops.hooks.session_start.subprocess.Popen", _FakePopen)
        return calls

    def test_never_asks_the_worker_to_rebuild_a_remote_store(
        self, remote: HranaStub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The stub has no ``last_rebuild_version``: a local store would get ``--rebuild``.
        calls = self._popen(monkeypatch)
        import little_loops.user_messages as um

        monkeypatch.setattr(um, "get_project_folder", lambda *a, **kw: tmp_path)
        handle(_event())
        assert len(calls) == 1
        assert "backfill_worker" in " ".join(calls[0])
        assert "--rebuild" not in calls[0]

    def test_does_not_migrate_a_remote_store_on_start(
        self, remote: HranaStub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._popen(monkeypatch)
        before = len(remote.requests)
        handle(_event())
        assert not any("begin immediate" in r["body"].lower() for r in remote.requests[before:])

    def test_the_digest_is_not_read_from_a_remote_store(
        self, remote: HranaStub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._popen(monkeypatch)
        import little_loops.history_reader as hr

        def _boom(*a, **k):
            raise AssertionError("project_digest must not run against a remote store")

        monkeypatch.setattr(hr, "project_digest", _boom)
        assert handle(_event()).exit_code == 0


class TestPostToolUse:
    def test_writes_the_tool_event_to_the_remote_store(
        self, remote: HranaStub, tmp_path: Path
    ) -> None:
        from little_loops.hooks.post_tool_use import handle as post_tool_use
        from little_loops.hooks.types import LLHookEvent

        cfg = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        cfg["analytics"] = {"enabled": True}
        (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps(cfg))
        db_mod.clear_backend_config_cache()
        event = LLHookEvent(
            host="claude-code",
            intent="post_tool_use",
            cwd=str(tmp_path),
            session_id="sess-9",
            payload={
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "tool_response": {"exit_code": 0},
                "session_id": "sess-9",
            },
        )
        assert post_tool_use(event).exit_code == 0
        row = remote.db.execute("select tool_name, session_id from tool_events").fetchone()
        assert row == ("Bash", "sess-9")
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_a_dead_endpoint_never_fails_the_hook(self, remote: HranaStub, tmp_path: Path) -> None:
        from little_loops.hooks.post_tool_use import handle as post_tool_use
        from little_loops.hooks.types import LLHookEvent

        cfg = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        cfg["analytics"] = {"enabled": True}
        cfg["history"]["backend"]["telemetry_timeout_ms"] = 200
        (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps(cfg))
        db_mod.clear_backend_config_cache()
        remote.stop()
        event = LLHookEvent(
            host="claude-code",
            intent="post_tool_use",
            cwd=str(tmp_path),
            session_id="s",
            payload={"tool_name": "Bash", "tool_input": {}, "tool_response": {}, "session_id": "s"},
        )
        assert post_tool_use(event).exit_code == 0


class TestDeadEndpointDegrades:
    """BUG-3659: a dead/suppressed remote endpoint never changes hook output or stops ll-action."""

    @pytest.fixture
    def dead(self, remote: HranaStub, tmp_path: Path) -> HranaStub:
        cfg = json.loads((tmp_path / ".ll" / "ll-config.json").read_text())
        cfg["analytics"] = {"enabled": True, "capture": {"hooks": True}}
        cfg["history"]["backend"]["telemetry_timeout_ms"] = 200
        (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps(cfg))
        db_mod.clear_backend_config_cache()
        remote.stop()
        return remote

    def _dispatch(self, monkeypatch: pytest.MonkeyPatch) -> int:
        import io

        from little_loops import hooks as hooks_pkg
        from little_loops.hooks.types import LLHookResult

        def handler(event) -> LLHookResult:
            return LLHookResult(exit_code=2, stdout='{"decision": "block"}', feedback="nope")

        monkeypatch.setattr(hooks_pkg, "_dispatch_table", lambda: {"pre_tool_use": handler})
        monkeypatch.setattr(sys, "argv", ["little_loops.hooks", "pre_tool_use"])
        monkeypatch.setattr(
            sys, "stdin", io.StringIO(json.dumps({"session_id": "s", "tool_name": "Bash"}))
        )
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
        return hooks_pkg.main_hooks()

    def _assert_intact(self, rc: int, capsys: pytest.CaptureFixture[str]) -> None:
        out, err = capsys.readouterr()
        assert rc == 2
        assert out == '{"decision": "block"}'
        assert "nope" in err
        assert "Traceback" not in err
        assert TOKEN not in err

    def test_main_hooks_keeps_handler_output_under_a_stopped_stub(
        self, dead: HranaStub, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._assert_intact(self._dispatch(monkeypatch), capsys)

    def test_main_hooks_keeps_handler_output_inside_the_suppression_window(
        self, dead: HranaStub, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        remote_telemetry.mark_unreachable(dead.url)
        before = len(dead.requests)
        self._assert_intact(self._dispatch(monkeypatch), capsys)
        assert len(dead.requests) == before

    def test_main_hooks_swallows_a_wrap_failure_but_not_a_handler_failure(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        import io

        from little_loops import hooks as hooks_pkg
        from little_loops import session_store
        from little_loops.hooks.types import LLHookResult

        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"analytics": {"enabled": True, "capture": {"hooks": True}}})
        )
        monkeypatch.chdir(tmp_path)

        class _BrokenWrap:
            def __init__(self, *a, **k) -> None:
                pass

            def __enter__(self):
                return type("C", (), {"exit_code": None, "stderr_preview": None})()

            def __exit__(self, exc_type, *rest) -> None:
                if exc_type is None:
                    raise ValueError("wrap exploded")

        monkeypatch.setattr(session_store, "hook_event_context", _BrokenWrap)
        monkeypatch.setattr(sys, "argv", ["little_loops.hooks", "pre_tool_use"])
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

        ok = lambda e: LLHookResult(exit_code=2, stdout="out")  # noqa: E731
        monkeypatch.setattr(hooks_pkg, "_dispatch_table", lambda: {"pre_tool_use": ok})
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        assert hooks_pkg.main_hooks() == 2
        assert capsys.readouterr().out == "out"

        def boom(e):
            raise RuntimeError("handler failed")

        monkeypatch.setattr(hooks_pkg, "_dispatch_table", lambda: {"pre_tool_use": boom})
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        with pytest.raises(RuntimeError, match="handler failed"):
            hooks_pkg.main_hooks()

    def test_ll_action_runs_the_skill_under_a_stopped_stub(self, dead: HranaStub) -> None:
        import argparse
        import subprocess
        from unittest.mock import patch

        from little_loops.cli.action import cmd_invoke

        args = argparse.Namespace(skill="explore-api", args=[], timeout=30, output="stream-json")
        done = subprocess.CompletedProcess(args=[], returncode=3, stdout="", stderr="")
        with patch(
            "little_loops.subprocess_utils.run_claude_command", return_value=done
        ) as mock_run:
            assert cmd_invoke(args) == 3
        assert mock_run.called

    def test_hook_writers_log_debug_when_suppressed_and_warn_otherwise(
        self, dead: HranaStub, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        from little_loops.session_store.writers import record_hook_event

        caplog.set_level(logging.DEBUG, logger="little_loops.session_store.writers")
        kwargs: dict[str, Any] = {
            "session_id": "s",
            "event_name": "PreToolUse",
            "matcher": None,
            "script": None,
            "exit_code": 0,
            "duration_ms": 1,
        }
        record_hook_event(Path(".ll/history.db"), **kwargs)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1

        caplog.clear()
        remote_telemetry.mark_unreachable(dead.url)
        record_hook_event(Path(".ll/history.db"), **kwargs)
        (rec,) = [r for r in caplog.records if "record_hook_event" in r.getMessage()]
        assert rec.levelno == logging.DEBUG and not rec.exc_info
        assert all(TOKEN not in r.getMessage() for r in caplog.records)

    def test_skill_event_context_body_still_runs_under_a_stopped_stub(
        self, dead: HranaStub
    ) -> None:
        from little_loops.session_store.writers import skill_event_context

        ran = []
        with skill_event_context(Path(".ll/history.db"), None, "explore-api", "") as completion:
            ran.append(True)
            completion.exit_code = 0
        assert ran


class TestBackfillWorker:
    def test_a_rebuild_is_refused_with_a_message_and_no_traceback(
        self, remote: HranaStub, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.cli.backfill_worker import main

        src = tmp_path / "s.jsonl"
        src.write_text("")
        assert main([str(tmp_path / ".ll" / "history.db"), str(src), "--rebuild"]) == 1
        err = capsys.readouterr().err
        assert "rebuild" in err and "libsql" in err
        assert "Traceback" not in err

    def test_ingest_only_is_allowed(self, remote: HranaStub, tmp_path: Path) -> None:
        from little_loops.cli.backfill_worker import main

        src = tmp_path / "s.jsonl"
        src.write_text(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "sessionId": "s",
                    "message": {},
                }
            )
            + "\n"
        )
        assert main([str(tmp_path / ".ll" / "history.db"), str(src)]) == 0
        assert remote.db.execute("select count(*) from raw_events").fetchone()[0] == 1


class TestSessionPathCommand:
    def test_a_foreign_transcript_path_is_labelled_not_an_error(
        self, remote: HranaStub, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.cli.session import main_session

        remote.db.execute(
            "insert into sessions(session_id, jsonl_path) values ('s1', '/nonexistent/other-machine/s1.jsonl')"
        )
        monkeypatch.setattr(sys, "argv", ["ll-session", "path", "s1"])
        assert main_session() == 0
        assert "recorded on another machine" in capsys.readouterr().out

    def test_a_local_transcript_path_is_printed_plain(
        self,
        remote: HranaStub,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from little_loops.cli.session import main_session

        here = tmp_path / "s2.jsonl"
        here.write_text("")
        remote.db.execute(
            "insert into sessions(session_id, jsonl_path) values ('s2', ?)", (str(here),)
        )
        monkeypatch.setattr(sys, "argv", ["ll-session", "path", "s2"])
        assert main_session() == 0
        out = capsys.readouterr().out
        assert str(here) in out and "another machine" not in out

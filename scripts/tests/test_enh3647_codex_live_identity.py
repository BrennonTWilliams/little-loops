"""Producer-backed Codex live identity tests for ENH-3647."""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from little_loops.fsm.runners import DefaultActionRunner
from little_loops.host_runner import HostInvocation
from little_loops.session_store import ensure_db, record_usage_event
from little_loops.subprocess_utils import TokenUsage, run_claude_command

FIXTURES = Path(__file__).parent / "fixtures" / "codex"


def _run_codex_fixture(path: Path) -> tuple[list[str], list[TokenUsage]]:
    """Feed captured NDJSON through the real subprocess reader with a fake host command."""
    invocation = HostInvocation(
        binary=sys.executable,
        args=[
            "-c",
            "import pathlib,sys;sys.stdout.write(pathlib.Path(sys.argv[1]).read_text())",
            str(path),
        ],
        env={},
    )
    runner = Mock()
    runner.name = "codex"
    runner.build_streaming.return_value = invocation
    session_ids: list[str] = []
    usage_events: list[TokenUsage] = []
    with patch("little_loops.subprocess_utils.resolve_host", return_value=runner):
        result = run_claude_command(
            "fixture",
            on_session_id_detected=session_ids.append,
            on_usage_detailed=usage_events.append,
        )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    return session_ids, usage_events


@pytest.mark.parametrize(
    "fixture",
    [
        "exec-json-v0.158.0.jsonl",
        "exec-json-resume-v0.158.0.jsonl",
        "exec-json-fork-v0.158.0.jsonl",
        "exec-json-turn.jsonl",
    ],
)
def test_live_thread_started_stamps_host_identity(fixture: str) -> None:
    """Each capture's own thread.started ID qualifies its live usage event."""
    path = FIXTURES / fixture
    native_thread_id = json.loads(path.read_text().splitlines()[0])["thread_id"]
    session_ids, usage_events = _run_codex_fixture(path)

    assert session_ids == [native_thread_id]
    assert len(usage_events) == 1
    usage = usage_events[0]
    assert usage.session_id == native_thread_id
    assert usage.identity_basis == "host_observed"
    assert usage.scope_kind == "unknown"
    assert usage.host == "codex"
    assert usage.provenance == "measured"
    assert usage.invocation_id is not None
    assert str(uuid.UUID(usage.invocation_id)) == usage.invocation_id
    assert uuid.UUID(usage.invocation_id).version == 4


def test_resume_and_fork_distinguish_thread_and_invocation_identity() -> None:
    """Resume has the original thread ID; fork has its own, and every process has a local UUID."""
    _, first = _run_codex_fixture(FIXTURES / "exec-json-v0.158.0.jsonl")
    _, resumed = _run_codex_fixture(FIXTURES / "exec-json-resume-v0.158.0.jsonl")
    _, forked = _run_codex_fixture(FIXTURES / "exec-json-fork-v0.158.0.jsonl")

    assert first[0].session_id == resumed[0].session_id
    assert forked[0].session_id != first[0].session_id
    assert len({first[0].invocation_id, resumed[0].invocation_id, forked[0].invocation_id}) == 3
    assert first[0].scope_kind == resumed[0].scope_kind == forked[0].scope_kind == "unknown"


def test_live_usage_without_thread_started_has_no_host_identity(tmp_path: Path) -> None:
    """A missing producer thread ID never gets replaced with the local invocation UUID."""
    path = tmp_path / "missing-thread.jsonl"
    lines = (FIXTURES / "exec-json-v0.158.0.jsonl").read_text().splitlines()
    path.write_text("\n".join(lines[1:]) + "\n")

    session_ids, usage_events = _run_codex_fixture(path)
    assert session_ids == []
    assert len(usage_events) == 1
    assert usage_events[0].session_id is None
    assert usage_events[0].identity_basis is None
    assert usage_events[0].invocation_id is not None


def test_fsm_runner_retains_codex_thread_and_usage_identity() -> None:
    """The existing session callback carries the native thread through ActionResult."""
    path = FIXTURES / "exec-json-v0.158.0.jsonl"
    native_thread_id = json.loads(path.read_text().splitlines()[0])["thread_id"]
    invocation = HostInvocation(
        binary=sys.executable,
        args=[
            "-c",
            "import pathlib,sys;sys.stdout.write(pathlib.Path(sys.argv[1]).read_text())",
            str(path),
        ],
        env={},
    )
    host = Mock()
    host.name = "codex"
    host.build_streaming.return_value = invocation

    with patch("little_loops.subprocess_utils.resolve_host", return_value=host):
        result = DefaultActionRunner().run("/ll:fixture", 30, True)

    assert result.exit_code == 0
    assert result.session_id == native_thread_id
    assert len(result.usage_events) == 1
    assert result.usage_events[0].session_id == native_thread_id
    assert result.usage_events[0].identity_basis == "host_observed"


def test_live_writer_persists_host_thread_and_local_invocation(tmp_path: Path) -> None:
    """The writer stores distinct native thread and local process identities."""
    _, usages = _run_codex_fixture(FIXTURES / "exec-json-fork-v0.158.0.jsonl")
    usage = usages[0]
    db = tmp_path / "history.db"
    ensure_db(db)
    record_usage_event(
        db,
        run_id="codex-live",
        ts="2026-09-29T00:00:00Z",
        state="check",
        model="gpt-5.6-sol",
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_creation_tokens=usage.cache_creation_tokens,
        provenance=usage.provenance,
        host=usage.host,
        scope_kind=usage.scope_kind,
        observed_at=usage.observed_at,
        observed_at_basis=usage.observed_at_basis,
        session_id=usage.session_id,
        identity_basis=usage.identity_basis,
        invocation_id=usage.invocation_id,
    )
    record_usage_event(
        db,
        run_id="legacy-live",
        ts="2026-09-29T00:00:00Z",
        state=None,
        model="gpt-5.6-sol",
        input_tokens=1,
        output_tokens=1,
        cache_read_tokens=0,
        cache_creation_tokens=0,
    )

    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT run_id, channel, host, session_id, identity_basis, invocation_id, "
            "scope_kind FROM usage_events ORDER BY id"
        ).fetchall()

    assert rows == [
        (
            "codex-live",
            "live",
            "codex",
            usage.session_id,
            "host_observed",
            usage.invocation_id,
            "unknown",
        ),
        ("legacy-live", "live", None, None, None, None, "unknown"),
    ]

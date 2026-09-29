"""Stop usage refresh is a small, detached hook-side operation."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from little_loops.hooks import main_hooks
from little_loops.hooks.types import LLHookEvent
from little_loops.hooks.usage_stop import handle


def _event(root: Path, source: Path, *, host: str = "claude-code") -> LLHookEvent:
    return LLHookEvent(
        host=host,
        intent="usage_stop",
        cwd=str(root),
        session_id="session-1",
        payload={"session_id": "session-1", "transcript_path": str(source)},
    )


@pytest.mark.parametrize("host", ["claude-code", "codex"])
def test_stop_spawns_detached_worker_without_reading_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text("{}")
    source = tmp_path / "not-yet-written.jsonl"
    calls: list[tuple[list[str], dict]] = []

    def fake_popen(args: list[str], **kwargs: object) -> object:
        calls.append((args, kwargs))
        return object()

    monkeypatch.setattr("little_loops.hooks.usage_stop.subprocess.Popen", fake_popen)
    monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)
    result = handle(_event(tmp_path, source, host=host))
    assert result.exit_code == 0
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[3:5] == [str(tmp_path / ".ll" / "history.db"), str(source)]
    assert args[args.index("--host") + 1] == host
    assert "--usage-trigger" in args
    assert int(args[args.index("--requested-at-ns") + 1]) > 0
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL


@pytest.mark.parametrize("skip", ["non_interactive", "other_host", "missing_path", "no_config"])
def test_stop_skips_unproven_or_disabled_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, skip: str
) -> None:
    (tmp_path / ".ll").mkdir()
    if skip != "no_config":
        (tmp_path / ".ll" / "ll-config.json").write_text("{}")
    source = tmp_path / "session.jsonl"
    event = _event(tmp_path, source, host="pi" if skip == "other_host" else "claude-code")
    if skip == "non_interactive":
        monkeypatch.setenv("LL_NON_INTERACTIVE", "1")
    else:
        monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)
    if skip == "missing_path":
        event.payload.pop("transcript_path")
    calls: list[object] = []
    monkeypatch.setattr(
        "little_loops.hooks.usage_stop.subprocess.Popen", lambda *a, **kw: calls.append(a)
    )
    assert handle(event).exit_code == 0
    assert calls == []


def test_dispatcher_does_not_open_hook_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text("{}")
    source = tmp_path / "session.jsonl"
    called: list[object] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["little_loops.hooks", "usage_stop"])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"transcript_path": str(source)})))
    monkeypatch.setattr(
        "little_loops.hooks._hooks_telemetry_enabled",
        lambda *_: pytest.fail("Stop trigger must not open hook telemetry"),
    )
    monkeypatch.setattr(
        "little_loops.hooks.usage_stop.subprocess.Popen", lambda *a, **kw: called.append(a)
    )
    monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)
    assert main_hooks() == 0
    assert len(called) == 1


def test_claude_stop_adapter_registered() -> None:
    root = Path(__file__).resolve().parents[2]
    hooks = json.loads((root / "hooks" / "hooks.json").read_text())
    commands = [hook["command"] for entry in hooks["hooks"]["Stop"] for hook in entry["hooks"]]
    assert any("adapters/claude-code/usage-stop.sh" in command for command in commands)


def test_captured_stop_has_completed_turn_usage_before_worker_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixtures = Path(__file__).parent / "fixtures" / "claude"
    payload = json.loads((fixtures / "stop-hook-v2.1.284.json").read_text())
    observation = json.loads((fixtures / "stop-observation-v2.1.284.json").read_text())
    source = tmp_path / "session.jsonl"
    source.write_bytes((fixtures / "stop-transcript-v2.1.284.jsonl").read_bytes())
    payload["transcript_path"] = str(source)
    records = [json.loads(line) for line in source.read_text().splitlines()]
    usage_records = [
        record
        for record in records
        if record.get("type") == "assistant"
        and isinstance(record.get("message", {}).get("usage"), dict)
    ]
    assert len(usage_records) == observation["complete_usage_records_at_stop"]
    assert usage_records[-1]["message"]["id"] == observation["last_usage"]["message_id"]
    assert usage_records[-1]["message"]["usage"] == observation["last_usage"]["usage"]

    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text("{}")
    launched: list[list[str]] = []
    monkeypatch.setattr(
        "little_loops.hooks.usage_stop.subprocess.Popen",
        lambda args, **kwargs: launched.append(args),
    )
    monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)
    event = LLHookEvent(host="claude-code", intent="usage_stop", cwd=str(tmp_path), payload=payload)
    assert handle(event).exit_code == 0
    assert len(launched) == 1
    assert str(source) in launched[0]

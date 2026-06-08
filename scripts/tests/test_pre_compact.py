"""Tests for the ``pre_compact`` hook handler (FEAT-1455).

Python-direct unit tests for ``little_loops.hooks.pre_compact.handle``. The
subprocess/adapter integration path is covered by
``test_hooks_integration.py::TestPrecompactState``; the CLI dispatcher
routing path is covered by
``test_hook_intents.py::TestHooksMainModule``. Together the three layers
cover handler logic, dispatcher routing, and end-to-end shell adapter
invocation without duplicating concerns.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from little_loops.hooks import pre_compact
from little_loops.hooks.types import LLHookEvent, LLHookResult


def _event(**payload: object) -> LLHookEvent:
    return LLHookEvent(host="claude-code", intent="pre_compact", payload=dict(payload))


class TestHandleHappyPath:
    """Baseline: handler writes the wire-visible state file with correct shape."""

    def test_writes_state_file_with_required_keys(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = pre_compact.handle(_event(transcript_path="/tmp/transcript.jsonl"))

        assert isinstance(result, LLHookResult)
        assert result.exit_code == 2
        assert result.feedback is not None
        assert "Task state preserved" in result.feedback

        state_file = tmp_path / ".ll" / "ll-precompact-state.json"
        assert state_file.is_file()

        state = json.loads(state_file.read_text())
        assert state["preserved"] is True
        assert state["transcript_path"] == "/tmp/transcript.jsonl"
        assert state["compacted_at"].endswith("Z")
        assert "T" in state["compacted_at"]
        assert state["recent_plan_files"] == []

    def test_creates_state_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """``.ll/`` is created when missing (matches shell ``mkdir -p``)."""
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / ".ll").exists()

        pre_compact.handle(_event())

        assert (tmp_path / ".ll").is_dir()

    def test_empty_transcript_path_defaults_to_empty_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact.handle(_event())

        state = json.loads((tmp_path / ".ll" / "ll-precompact-state.json").read_text())
        assert state["transcript_path"] == ""


class TestContextStateMerge:
    """``context_state_at_compact`` is merged in when ``.ll/ll-context-state.json`` exists."""

    def test_merges_existing_context_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        ctx = {"estimated_tokens": 42, "threshold_crossed_at": None}
        (ll_dir / "ll-context-state.json").write_text(json.dumps(ctx))

        pre_compact.handle(_event())

        state = json.loads((ll_dir / "ll-precompact-state.json").read_text())
        assert state["context_state_at_compact"] == ctx

    def test_omits_key_when_context_state_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact.handle(_event())

        state = json.loads((tmp_path / ".ll" / "ll-precompact-state.json").read_text())
        assert "context_state_at_compact" not in state


class TestRecentPlanFiles:
    """``recent_plan_files`` lists up to 5 plans modified in the last 24h."""

    def test_empty_when_plans_dir_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact.handle(_event())

        state = json.loads((tmp_path / ".ll" / "ll-precompact-state.json").read_text())
        assert state["recent_plan_files"] == []

    def test_collects_recent_plans(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        plans = tmp_path / "thoughts" / "shared" / "plans"
        plans.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            (plans / f"plan-{i}.md").write_text(f"# plan {i}")

        pre_compact.handle(_event())

        state = json.loads((tmp_path / ".ll" / "ll-precompact-state.json").read_text())
        assert len(state["recent_plan_files"]) == 3
        for p in state["recent_plan_files"]:
            assert p.startswith("thoughts/shared/plans/") or p.endswith(".md")

    def test_caps_at_five_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        plans = tmp_path / "thoughts" / "shared" / "plans"
        plans.mkdir(parents=True, exist_ok=True)
        for i in range(8):
            (plans / f"plan-{i:02d}.md").write_text("x")

        pre_compact.handle(_event())

        state = json.loads((tmp_path / ".ll" / "ll-precompact-state.json").read_text())
        assert len(state["recent_plan_files"]) == 5

    def test_excludes_old_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Files with mtime > 24h ago are filtered out."""
        import os
        import time

        monkeypatch.chdir(tmp_path)
        plans = tmp_path / "thoughts" / "shared" / "plans"
        plans.mkdir(parents=True, exist_ok=True)
        fresh = plans / "fresh.md"
        fresh.write_text("x")
        stale = plans / "stale.md"
        stale.write_text("x")
        old = time.time() - 86400 - 60
        os.utime(stale, (old, old))

        pre_compact.handle(_event())

        state = json.loads((tmp_path / ".ll" / "ll-precompact-state.json").read_text())
        names = [Path(p).name for p in state["recent_plan_files"]]
        assert "fresh.md" in names
        assert "stale.md" not in names


class TestContinuePromptKeyPresence:
    """``continue_prompt_exists`` key is absent unless the file exists; ``True`` when it does."""

    def test_key_absent_when_file_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact.handle(_event())

        state = json.loads((tmp_path / ".ll" / "ll-precompact-state.json").read_text())
        assert "continue_prompt_exists" not in state

    def test_key_true_when_file_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (ll_dir / "ll-continue-prompt.md").write_text("# resume me")

        pre_compact.handle(_event())

        state = json.loads((ll_dir / "ll-precompact-state.json").read_text())
        assert state["continue_prompt_exists"] is True


class TestResultContract:
    """The ``LLHookResult`` shape exactly matches the Claude Code feedback contract."""

    def test_returns_exit_two_with_feedback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = pre_compact.handle(_event(transcript_path="/tmp/t.jsonl"))

        assert result.exit_code == 2
        assert result.feedback == (
            "[ll] Task state preserved before context compaction. "
            "Check .ll/ll-precompact-state.json if resuming work."
        )
        assert result.decision is None


class TestNoopOnMalformedPayload:
    """Defensive: handler must not raise on degenerate payloads."""

    def test_non_string_transcript_path_does_not_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = pre_compact.handle(_event(transcript_path=12345))

        assert result.exit_code in (0, 2)


class TestConcurrentInvocation:
    """Lock + atomic-write keep the state file valid under contention."""

    def test_concurrent_handles_leave_valid_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        def call(i: int) -> LLHookResult:
            return pre_compact.handle(_event(transcript_path=f"/tmp/t-{i}.jsonl"))

        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(call, i) for i in range(5)]
            results = [f.result() for f in as_completed(futures)]

        assert all(r.exit_code == 2 for r in results)
        state = json.loads((tmp_path / ".ll" / "ll-precompact-state.json").read_text())
        assert state["preserved"] is True


class TestContextMonitorContract:
    """Byte-contract check: ``check_compaction()`` still reads ``.compacted_at``.

    Cheap grep-assert that the sole structural consumer (``context-monitor.sh``)
    has not silently grown a dependency on additional keys we may have changed.
    """

    def test_check_compaction_reads_compacted_at(self) -> None:
        monitor = Path(__file__).parent.parent.parent / "hooks/scripts/context-monitor.sh"
        text = monitor.read_text()
        assert "check_compaction" in text
        assert ".compacted_at" in text

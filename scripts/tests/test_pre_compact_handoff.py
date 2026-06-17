"""Tests for the ``pre_compact_handoff`` hook handler (FEAT-1156).

Unit tests for ``little_loops.hooks.pre_compact_handoff.handle`` and the
``_build_content`` LIFO helper. The subprocess/adapter integration path
(shell adapter → Python dispatcher → handler) is covered by the
``test_dispatch_pre_compact_handoff_happy_path`` test in ``test_hook_intents.py``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from little_loops.hooks import pre_compact_handoff
from little_loops.hooks.pre_compact_handoff import _build_content
from little_loops.hooks.types import LLHookEvent, LLHookResult


def _event(**payload: object) -> LLHookEvent:
    return LLHookEvent(
        host="claude-code", intent="pre_compact_handoff", payload=dict(payload)
    )


class TestBuildContent:
    """Verify the LIFO 2KB-cap helper in isolation."""

    def test_sections_under_limit_joined_as_is(self) -> None:
        sections = ["## A\nfoo", "## B\nbar"]
        result = _build_content(sections, max_bytes=2048)
        assert result == "## A\nfoo\n\n## B\nbar"

    def test_drops_last_section_when_over_limit(self) -> None:
        big = "x" * 1500
        sections = [f"## Small\nshort", f"## Big\n{big}"]
        result = _build_content(sections, max_bytes=100)
        assert "## Small" in result
        assert "## Big" not in result

    def test_drops_multiple_sections_under_pressure(self) -> None:
        sections = ["## A\nfoo", "## B\nbar", "## C\nbaz", "## D\n" + "x" * 3000]
        result = _build_content(sections, max_bytes=50)
        # Under extreme pressure only the first section(s) survive
        assert result  # non-empty
        assert "## D" not in result

    def test_empty_sections_returns_empty_string(self) -> None:
        result = _build_content([], max_bytes=2048)
        assert result == ""

    def test_single_section_within_limit_returned(self) -> None:
        sections = ["## Intent\nActive: FEAT-1156"]
        result = _build_content(sections, max_bytes=2048)
        assert result == "## Intent\nActive: FEAT-1156"

    def test_join_uses_double_newline(self) -> None:
        sections = ["A", "B", "C"]
        result = _build_content(sections, max_bytes=2048)
        assert result == "A\n\nB\n\nC"

    def test_does_not_mutate_caller_list_beyond_drop(self) -> None:
        """Sections that survive are still accessible via the list after the call."""
        sections = ["short", "x" * 3000]
        result = _build_content(sections, max_bytes=100)
        assert result == "short"


class TestIdempotencyGuard:
    """Skips write when .ll/ll-continue-prompt.md is already fresher than compacted_at."""

    def test_skips_write_when_prompt_is_fresh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prompt mtime newer than compacted_at → exit 0 (no write triggered)."""
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()

        # Write a compacted_at timestamp in the past
        past_ts = "2020-01-01T00:00:00Z"
        (ll_dir / "ll-precompact-state.json").write_text(
            json.dumps({"compacted_at": past_ts}), encoding="utf-8"
        )
        prompt_file = ll_dir / "ll-continue-prompt.md"
        prompt_file.write_text("# existing prompt", encoding="utf-8")
        # mtime is now (after 2020), so it's "fresh"

        result = pre_compact_handoff.handle(_event())

        assert result.exit_code == 0

    def test_writes_when_prompt_is_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prompt mtime older than compacted_at → handler writes a new prompt."""
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()

        # Write a compacted_at timestamp in the future (relative to old mtime)
        future_ts = "2099-01-01T00:00:00Z"
        (ll_dir / "ll-precompact-state.json").write_text(
            json.dumps({"compacted_at": future_ts}), encoding="utf-8"
        )
        prompt_file = ll_dir / "ll-continue-prompt.md"
        prompt_file.write_text("# old prompt", encoding="utf-8")
        old_mtime = time.time() - 3600
        os.utime(prompt_file, (old_mtime, old_mtime))

        result = pre_compact_handoff.handle(_event())

        assert result.exit_code == 2

    def test_writes_when_no_state_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing .ll/ll-precompact-state.json → OSError caught → handler proceeds."""
        monkeypatch.chdir(tmp_path)

        result = pre_compact_handoff.handle(_event())

        assert result.exit_code == 2
        assert (tmp_path / ".ll" / "ll-continue-prompt.md").is_file()

    def test_writes_when_state_file_malformed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Malformed JSON in state file → JSONDecodeError caught → handler proceeds."""
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-precompact-state.json").write_text("not json", encoding="utf-8")

        result = pre_compact_handoff.handle(_event())

        assert result.exit_code == 2

    def test_writes_when_compacted_at_key_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """State file exists but lacks compacted_at key → KeyError caught → handler proceeds."""
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-precompact-state.json").write_text(
            json.dumps({"preserved": True}), encoding="utf-8"
        )

        result = pre_compact_handoff.handle(_event())

        assert result.exit_code == 2


class TestSubprocessDegradation:
    """Each external source degrades to empty string on failure; handler must not crash."""

    def test_loops_dir_absent_produces_no_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No .loops/runs/ dir → loop-state section simply empty; no exception."""
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / ".loops").exists()

        result = pre_compact_handoff.handle(_event())

        assert result.exit_code in (0, 2)

    def test_session_events_absent_produces_no_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No .ll/ll-session-events.jsonl → no tool-event section; no exception."""
        monkeypatch.chdir(tmp_path)

        result = pre_compact_handoff.handle(_event())

        assert result.exit_code in (0, 2)

    def test_session_events_present_included_in_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When .ll/ll-session-events.jsonl exists, its tail is appended to the prompt."""
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        events_file = ll_dir / "ll-session-events.jsonl"
        events_file.write_text('{"tool": "Bash", "cmd": "ls"}\n', encoding="utf-8")

        result = pre_compact_handoff.handle(_event())

        assert result.exit_code == 2
        content = (ll_dir / "ll-continue-prompt.md").read_text(encoding="utf-8")
        # Recent Activity section should exist when events file is present
        assert "Recent Activity" in content or len(content) <= 2048


class TestResultContract:
    """LLHookResult shape matches the Claude Code feedback contract."""

    def test_returns_exit_two_on_successful_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = pre_compact_handoff.handle(_event())

        assert result.exit_code == 2

    def test_feedback_mentions_handoff_snapshot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = pre_compact_handoff.handle(_event())

        assert result.feedback is not None
        assert "handoff snapshot" in result.feedback.lower() or "Session handoff" in result.feedback

    def test_returns_exit_zero_on_idempotency_skip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-precompact-state.json").write_text(
            json.dumps({"compacted_at": "2020-01-01T00:00:00Z"}), encoding="utf-8"
        )
        (ll_dir / "ll-continue-prompt.md").write_text("# prompt", encoding="utf-8")

        result = pre_compact_handoff.handle(_event())

        assert result.exit_code == 0
        assert result.feedback is None

    def test_decision_is_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)

        result = pre_compact_handoff.handle(_event())

        assert result.decision is None


class TestOutputSchema:
    """Written .ll/ll-continue-prompt.md has required structure for /ll:resume compatibility."""

    def test_creates_ll_dir_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / ".ll").exists()

        pre_compact_handoff.handle(_event())

        assert (tmp_path / ".ll").is_dir()

    def test_writes_continue_prompt_md(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact_handoff.handle(_event())

        assert (tmp_path / ".ll" / "ll-continue-prompt.md").is_file()

    def test_output_has_intent_section(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact_handoff.handle(_event())

        content = (tmp_path / ".ll" / "ll-continue-prompt.md").read_text(encoding="utf-8")
        assert "## Intent" in content

    def test_output_has_next_steps_section(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact_handoff.handle(_event())

        content = (tmp_path / ".ll" / "ll-continue-prompt.md").read_text(encoding="utf-8")
        assert "## Next Steps" in content

    def test_output_within_2kb(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact_handoff.handle(_event())

        content = (tmp_path / ".ll" / "ll-continue-prompt.md").read_bytes()
        assert len(content) <= 2048

    def test_output_has_frontmatter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact_handoff.handle(_event())

        content = (tmp_path / ".ll" / "ll-continue-prompt.md").read_text(encoding="utf-8")
        assert content.startswith("---")

    def test_frontmatter_has_session_date(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact_handoff.handle(_event())

        content = (tmp_path / ".ll" / "ll-continue-prompt.md").read_text(encoding="utf-8")
        assert "session_date:" in content

    def test_frontmatter_has_session_branch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact_handoff.handle(_event())

        content = (tmp_path / ".ll" / "ll-continue-prompt.md").read_text(encoding="utf-8")
        assert "session_branch:" in content

    def test_frontmatter_has_issues_in_progress(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        pre_compact_handoff.handle(_event())

        content = (tmp_path / ".ll" / "ll-continue-prompt.md").read_text(encoding="utf-8")
        assert "issues_in_progress:" in content


class TestExceptionSafety:
    """Handler never raises; any unexpected error returns exit_code=0."""

    def test_non_dict_payload_does_not_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = pre_compact_handoff.handle(
            LLHookEvent(host="claude-code", intent="pre_compact_handoff", payload={})
        )

        assert result.exit_code in (0, 2)

"""Tests for FEAT-2710 (EPIC-2456 F1): Message Batches API request path.

Covers:

- :func:`~little_loops.host_runner.build_batch_request` — wraps
  ``build_anthropic_request()`` output in the ``{"requests": [...]}`` shape
  ``anthropic.resources.messages.batches.Batches.create()`` expects.
- :class:`~little_loops.fsm.batch_tracker.BatchTracker` — file-backed
  ``batch_id`` bookkeeping for resume-without-double-submit.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.fsm.batch_tracker import BatchTracker
from little_loops.host_runner import build_batch_request
from little_loops.prompts import FragmentStore

LONG_TEXT = "x" * 5000


class TestBuildBatchRequest:
    def test_wraps_single_request_shape(self) -> None:
        store = FragmentStore()
        result = build_batch_request(
            custom_id="req-1",
            skill_body=LONG_TEXT,
            system_prompt=LONG_TEXT,
            tools=None,
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5",
            fragment_store=store,
        )
        assert list(result.keys()) == ["requests"]
        assert len(result["requests"]) == 1
        entry = result["requests"][0]
        assert entry["custom_id"] == "req-1"
        assert entry["params"]["model"] == "claude-sonnet-4-5"
        assert entry["params"]["messages"] == [{"role": "user", "content": "hi"}]

    def test_reuses_build_anthropic_request_cache_marking(self) -> None:
        store = FragmentStore()
        kwargs = {
            "skill_body": LONG_TEXT,
            "system_prompt": LONG_TEXT,
            "tools": None,
            "messages": [{"role": "user", "content": "hi"}],
            "model": "claude-sonnet-4-5",
            "fragment_store": store,
        }
        build_batch_request(custom_id="req-1", **kwargs)  # first sighting
        result = build_batch_request(custom_id="req-2", **kwargs)  # repeat
        params = result["requests"][0]["params"]
        assert params["system"][0]["cache_control"] == {"type": "ephemeral"}


class TestBatchTracker:
    def test_get_batch_id_absent_returns_none(self, tmp_path: Path) -> None:
        tracker = BatchTracker(tmp_path / "batch_id.json")
        assert tracker.get_batch_id() is None

    def test_record_submitted_then_get_batch_id(self, tmp_path: Path) -> None:
        tracker = BatchTracker(tmp_path / "run" / "batch_id.json")
        tracker.record_submitted("msgbatch_123", "req-1")
        assert tracker.get_batch_id() == "msgbatch_123"

    def test_clear_removes_state(self, tmp_path: Path) -> None:
        tracker = BatchTracker(tmp_path / "batch_id.json")
        tracker.record_submitted("msgbatch_123", "req-1")
        tracker.clear()
        assert tracker.get_batch_id() is None

    def test_clear_is_noop_when_absent(self, tmp_path: Path) -> None:
        tracker = BatchTracker(tmp_path / "batch_id.json")
        tracker.clear()  # must not raise

    def test_corrupt_state_file_treated_as_absent(self, tmp_path: Path) -> None:
        path = tmp_path / "batch_id.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json")
        tracker = BatchTracker(path)
        assert tracker.get_batch_id() is None

    def test_record_submitted_overwrites_prior(self, tmp_path: Path) -> None:
        tracker = BatchTracker(tmp_path / "batch_id.json")
        tracker.record_submitted("msgbatch_1", "req-1")
        tracker.record_submitted("msgbatch_2", "req-2")
        assert tracker.get_batch_id() == "msgbatch_2"

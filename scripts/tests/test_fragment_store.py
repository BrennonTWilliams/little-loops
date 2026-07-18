"""Tests for the content-hash fragment store (FEAT-2671, EPIC-2456 F1-prereq a).

``fragment_key()`` regression tests plus the locked ``fragment_store_traces``
hit-rate gate. Fixture layout mirrors the ENH-2518 ``tier0_traces`` /
FEAT-2675 ``heuristic_traces`` precedent (``manifest.json`` + per-trace
JSON). Loaders use ``pytest.fail`` (not ``skip``) so a missing fixture is a
hard failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.prompts import FragmentStore, fragment_key

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fragment_store_traces"

MIN_HIT_RATE_PCT = 80.0


def _load_manifest() -> dict:
    path = FIXTURES_DIR / "manifest.json"
    if not path.is_file():
        pytest.fail(f"locked trace manifest missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_trace(trace_id: str) -> list[dict]:
    path = FIXTURES_DIR / f"{trace_id}.json"
    if not path.is_file():
        pytest.fail(f"locked trace missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list), f"{trace_id} is not a call list"
    return data


class TestFragmentKey:
    """SHA-256 key regression tests."""

    def test_stable_across_repeated_calls(self) -> None:
        a = fragment_key("skill body", "system prompt", ["Read", "Write"])
        b = fragment_key("skill body", "system prompt", ["Read", "Write"])
        assert a == b

    def test_is_64_char_hex(self) -> None:
        key = fragment_key("skill body", "system prompt", ["Read"])
        assert len(key) == 64
        int(key, 16)  # raises ValueError if not hex

    def test_changes_when_skill_body_changes(self) -> None:
        a = fragment_key("skill body", "system prompt", ["Read"])
        b = fragment_key("different skill body", "system prompt", ["Read"])
        assert a != b

    def test_changes_when_system_prompt_changes(self) -> None:
        a = fragment_key("skill body", "system prompt", ["Read"])
        b = fragment_key("skill body", "different system prompt", ["Read"])
        assert a != b

    def test_changes_when_tool_definitions_changes(self) -> None:
        a = fragment_key("skill body", "system prompt", ["Read"])
        b = fragment_key("skill body", "system prompt", ["Read", "Write"])
        assert a != b

    def test_handles_none_system_prompt_and_tools(self) -> None:
        key = fragment_key("skill body", None, None)
        assert len(key) == 64


class TestFragmentStore:
    """get/put + hit-counter behavior of the small keyed store."""

    def test_first_put_is_a_miss(self) -> None:
        store = FragmentStore()
        is_hit = store.put(fragment_key("a", "b", ["c"]))
        assert is_hit is False
        assert store.hits == 0
        assert store.misses == 1

    def test_repeated_put_is_a_hit(self) -> None:
        store = FragmentStore()
        key = fragment_key("a", "b", ["c"])
        store.put(key)
        is_hit = store.put(key)
        assert is_hit is True
        assert store.hits == 1
        assert store.misses == 1

    def test_get_reflects_prior_observation(self) -> None:
        store = FragmentStore()
        key = fragment_key("a", "b", ["c"])
        assert store.get(key) is False
        store.put(key)
        assert store.get(key) is True

    def test_hit_rate_pct(self) -> None:
        store = FragmentStore()
        key = fragment_key("a", "b", ["c"])
        store.put(key)  # miss
        store.put(key)  # hit
        store.put(key)  # hit
        assert store.hit_rate_pct == pytest.approx(200 / 3)

    def test_hit_rate_pct_empty_store_is_zero(self) -> None:
        assert FragmentStore().hit_rate_pct == 0.0


class TestLockedTraceHitRate:
    """Hit rate >= 80% over the purpose-built fragment_store_traces fixture set."""

    def test_manifest_traces_exist(self) -> None:
        manifest = _load_manifest()
        for entry in manifest["traces"]:
            assert (FIXTURES_DIR / entry["path"]).is_file()

    def test_hit_rate_meets_threshold(self) -> None:
        manifest = _load_manifest()
        store = FragmentStore()
        total_calls = 0
        for entry in manifest["traces"]:
            for call in _load_trace(entry["id"]):
                key = fragment_key(
                    call["skill_body"], call["system_prompt"], call["tool_definitions"]
                )
                store.put(key)
                total_calls += 1

        assert total_calls > 0
        assert store.hit_rate_pct >= MIN_HIT_RATE_PCT

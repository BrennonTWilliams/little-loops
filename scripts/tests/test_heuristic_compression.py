"""Tests for the heuristic prompt compressor (FEAT-2675).

Pure-function unit tests for the three passes plus ``compress()`` trigger
resolution, and the locked 10-trace ``general-task`` reduction-band gate. The
reduction is measured against the heuristic's own before/after token counts
(``len // 4`` convention) — no LLMLingua/transformers dependency.

Fixture layout mirrors the ENH-2518 ``tier0_traces`` precedent
(``scripts/tests/fixtures/<set>/manifest.json`` + per-trace JSON). Loaders use
``pytest.fail`` (not ``skip``) so a missing fixture is a hard failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.compression import (
    CompressedResult,
    compress,
    compress_action_text,
    dedupe_stable_system_blocks,
    drop_stale_tool_results,
    tail_truncate_assistant_turns,
)
from little_loops.compression.heuristic import _resolve_trigger

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "heuristic_traces"

# Locked IDs — mirrored at module scope so parametrized collection works even
# before fixtures exist (Red-phase safe).
LOCKED_TRACE_IDS = tuple(f"general-task-{i:02d}" for i in range(10))

REDUCTION_MIN = 3.0
REDUCTION_MAX = 6.0


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
    assert isinstance(data, list), f"{trace_id} is not a message list"
    return data


# --------------------------------------------------------------------------- #
# Manifest-level gates (existence / owner / count / id-set agreement)
# --------------------------------------------------------------------------- #


class TestLockedTraceManifest:
    def test_manifest_meta(self) -> None:
        meta = _load_manifest()["_meta"]
        assert meta["owner"] == "FEAT-2675"
        assert meta["epic"] == "EPIC-2456"
        assert meta["tier"] == "tier-3"

    def test_trace_count(self) -> None:
        traces = _load_manifest()["traces"]
        assert len(traces) == len(LOCKED_TRACE_IDS) == 10

    def test_id_set_agreement(self) -> None:
        manifest_ids = {t["id"] for t in _load_manifest()["traces"]}
        assert manifest_ids == set(LOCKED_TRACE_IDS)


# --------------------------------------------------------------------------- #
# Reduction-band gate — the core acceptance criterion (3-6x, len//4)
# --------------------------------------------------------------------------- #


class TestReductionBand:
    @pytest.mark.parametrize("trace_id", LOCKED_TRACE_IDS)
    def test_trace_in_band(self, trace_id: str) -> None:
        messages = _load_trace(trace_id)
        # context_window=None + trigger_tokens=None -> compress unconditionally.
        result = compress(messages, context_window=None)
        assert result.triggered
        assert result.compressed_tokens < result.original_tokens
        assert REDUCTION_MIN <= result.reduction_ratio <= REDUCTION_MAX, (
            f"{trace_id}: ratio {result.reduction_ratio:.2f} outside "
            f"[{REDUCTION_MIN}, {REDUCTION_MAX}]"
        )

    def test_mean_in_band(self) -> None:
        ratios = [compress(_load_trace(t), context_window=None).reduction_ratio for t in LOCKED_TRACE_IDS]
        mean = sum(ratios) / len(ratios)
        assert REDUCTION_MIN <= mean <= REDUCTION_MAX


# --------------------------------------------------------------------------- #
# Pass 1: drop_stale_tool_results
# --------------------------------------------------------------------------- #


class TestDropStaleToolResults:
    def _transcript(self) -> list[dict]:
        msgs: list[dict] = [{"role": "system", "content": "S"}]
        for turn in range(8):
            msgs.append({"role": "user", "content": f"u{turn}"})
            msgs.append({"role": "tool", "content": f"tool{turn}"})
            msgs.append({"role": "assistant", "content": f"a{turn}"})
        return msgs

    def test_drops_old_tool_results(self) -> None:
        out = drop_stale_tool_results(self._transcript(), max_age_turns=2)
        tool_contents = {m["content"] for m in out if m["role"] == "tool"}
        # 8 user turns; keep tools from the last 2 turns (turns 7 and 6).
        assert tool_contents == {"tool6", "tool7"}

    def test_preserves_system_and_nontool(self) -> None:
        out = drop_stale_tool_results(self._transcript(), max_age_turns=2)
        assert any(m["role"] == "system" for m in out)
        assert len([m for m in out if m["role"] == "assistant"]) == 8

    def test_noop_when_within_window(self) -> None:
        msgs = self._transcript()
        assert drop_stale_tool_results(msgs, max_age_turns=100) == msgs


# --------------------------------------------------------------------------- #
# Pass 2: dedupe_stable_system_blocks
# --------------------------------------------------------------------------- #


class TestDedupeStableSystemBlocks:
    def test_dedupes_exact_duplicates(self) -> None:
        msgs = [
            {"role": "system", "content": "BIG SYSTEM PROMPT"},
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "BIG SYSTEM PROMPT"},
            {"role": "assistant", "content": "yo"},
            {"role": "system", "content": "BIG SYSTEM PROMPT"},
        ]
        out, candidates = dedupe_stable_system_blocks(msgs)
        assert [m["content"] for m in out if m["role"] == "system"] == ["BIG SYSTEM PROMPT"]
        # The surviving repeated block is flagged as a cache_control candidate.
        assert candidates == [0]

    def test_keeps_distinct_system_blocks(self) -> None:
        msgs = [
            {"role": "system", "content": "A"},
            {"role": "system", "content": "B"},
        ]
        out, candidates = dedupe_stable_system_blocks(msgs)
        assert len(out) == 2
        assert candidates == []  # neither repeated


# --------------------------------------------------------------------------- #
# Pass 3: tail_truncate_assistant_turns
# --------------------------------------------------------------------------- #


class TestTailTruncateAssistantTurns:
    def _msgs(self, n: int) -> list[dict]:
        out: list[dict] = []
        for i in range(n):
            out.append({"role": "user", "content": f"u{i}"})
            out.append({"role": "assistant", "content": f"a{i}"})
        return out

    def test_keeps_last_n_assistant(self) -> None:
        out = tail_truncate_assistant_turns(self._msgs(10), max_n=3)
        assistants = [m["content"] for m in out if m["role"] == "assistant"]
        assert assistants == ["a7", "a8", "a9"]

    def test_preserves_nonassistant(self) -> None:
        out = tail_truncate_assistant_turns(self._msgs(10), max_n=3)
        assert len([m for m in out if m["role"] == "user"]) == 10

    def test_noop_when_under_limit(self) -> None:
        msgs = self._msgs(2)
        assert tail_truncate_assistant_turns(msgs, max_n=5) == msgs


# --------------------------------------------------------------------------- #
# compress() trigger resolution
# --------------------------------------------------------------------------- #


class TestCompressTrigger:
    def _big(self) -> list[dict]:
        # Duplicate system block is large enough that dedup registers token savings.
        return [
            {"role": "system", "content": "S" * 4000},
            {"role": "system", "content": "S" * 4000},
            {"role": "user", "content": "x" * 4000},
        ]

    def test_below_trigger_is_noop(self) -> None:
        result = compress(self._big(), context_window=1_000_000, trigger_pct=0.4)
        # 0.4 * 1M = 400k token trigger; ~1k-token input is far below.
        assert not result.triggered
        assert result.messages == self._big()
        assert result.reduction_ratio == 1.0

    def test_above_trigger_compresses(self) -> None:
        result = compress(self._big(), trigger_tokens=10)
        assert result.triggered
        assert result.compressed_tokens < result.original_tokens

    def test_lower_of_pct_and_tokens_wins(self) -> None:
        # pct trigger = 0.4 * 1M = 400k; trigger_tokens = 10 -> 10 wins -> fires.
        result = compress(self._big(), context_window=1_000_000, trigger_pct=0.4, trigger_tokens=10)
        assert result.triggered

    def test_no_trigger_compresses_unconditionally(self) -> None:
        result = compress(self._big(), context_window=None, trigger_tokens=None)
        assert result.triggered

    def test_resolve_trigger_helper(self) -> None:
        assert _resolve_trigger(1_000_000, 0.4, None) == 400_000
        assert _resolve_trigger(1_000_000, 0.4, 10) == 10
        assert _resolve_trigger(None, 0.4, 50) == 50
        assert _resolve_trigger(None, 0.4, None) is None

    def test_result_type(self) -> None:
        assert isinstance(compress(self._big(), context_window=None), CompressedResult)


# --------------------------------------------------------------------------- #
# compress_action_text — the executor string adapter (byte-safety)
# --------------------------------------------------------------------------- #


class TestCompressActionText:
    def test_short_prose_passes_through_identical(self) -> None:
        text = "short prompt"
        assert compress_action_text(text, model="claude-opus-4-8") == text

    def test_large_prose_passes_through_identical(self) -> None:
        # Above trigger but not a JSON message list -> never mangled.
        text = "x" * 2_000_000
        assert compress_action_text(text, trigger_tokens=10) == text

    def test_json_message_list_above_trigger_compressed(self) -> None:
        messages = [
            {"role": "system", "content": "S" * 400},
            {"role": "system", "content": "S" * 400},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
        ]
        text = json.dumps(messages)
        out = compress_action_text(text, trigger_tokens=1)
        assert out != text
        # Round-trips to a valid, smaller message list.
        out_msgs = json.loads(out)
        assert len([m for m in out_msgs if m["role"] == "system"]) == 1

    def test_json_message_list_below_trigger_identical(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        text = json.dumps(messages)
        assert compress_action_text(text, context_window=1_000_000, trigger_pct=0.4) == text

"""Tests for FEAT-2673 (EPIC-2456 F1): cache_control: ephemeral integration
and the cache-marking cost oracle.

Covers:

- :func:`~little_loops.cache_marking_oracle.decide_cache_marking` — the two
  independent gates (cacheable-prefix minimum, reuse-stability signal) and
  the regression AC that a block is never marked on first sight.
- :func:`~little_loops.host_runner.build_anthropic_request` — request-shape
  assembly, cache_control placement, and that the CLI shell path is
  unaffected by this new function's existence.
"""

from __future__ import annotations

from typing import Any

import pytest

from little_loops.cache_marking_oracle import (
    CACHEABLE_PREFIX_MINIMUMS,
    decide_cache_marking,
)
from little_loops.host_runner import build_anthropic_request
from little_loops.prompts import FragmentStore, fragment_key
from little_loops.tool_catalog import ToolDefinition

LONG_TEXT = "x" * 5000  # well above both known cacheable-prefix minimums
SHORT_TEXT = "x" * 40  # well below both known cacheable-prefix minimums


class TestDecideCacheMarking:
    """Both gates — cacheable-prefix minimum and reuse-stability — must pass."""

    def test_refuses_below_cacheable_minimum(self) -> None:
        store = FragmentStore()
        key = fragment_key(SHORT_TEXT, None, None)
        store.put(key)  # make it a repeat so only the size gate can block it
        decision = decide_cache_marking(
            block_text=SHORT_TEXT,
            fragment_key=key,
            fragment_store=store,
            model="sonnet",
        )
        assert decision.should_mark is False
        assert "cacheable-prefix minimum" in decision.reason

    def test_refuses_first_sight_even_above_minimum(self) -> None:
        """Regression AC: never logs a 1.25x write on a block not yet reused."""
        store = FragmentStore()
        key = fragment_key(LONG_TEXT, None, None)
        decision = decide_cache_marking(
            block_text=LONG_TEXT,
            fragment_key=key,
            fragment_store=store,
            model="sonnet",
        )
        assert decision.should_mark is False
        assert "not yet observed as a repeat" in decision.reason

    def test_marks_once_above_minimum_and_repeated(self) -> None:
        store = FragmentStore()
        key = fragment_key(LONG_TEXT, None, None)
        store.put(key)  # first observation
        decision = decide_cache_marking(
            block_text=LONG_TEXT,
            fragment_key=key,
            fragment_store=store,
            model="sonnet",
        )
        assert decision.should_mark is True

    def test_require_repeat_false_marks_on_first_sight(self) -> None:
        store = FragmentStore()
        key = fragment_key(LONG_TEXT, None, None)
        decision = decide_cache_marking(
            block_text=LONG_TEXT,
            fragment_key=key,
            fragment_store=store,
            model="sonnet",
            require_repeat=False,
        )
        assert decision.should_mark is True

    def test_opus_minimum_is_stricter_than_sonnet(self) -> None:
        assert CACHEABLE_PREFIX_MINIMUMS["opus"] > CACHEABLE_PREFIX_MINIMUMS["sonnet"]

    def test_sonnet_minimum_boundary_between_models(self) -> None:
        # Text sized between the two known minimums: passes for sonnet, fails for opus.
        boundary_text = "x" * (CACHEABLE_PREFIX_MINIMUMS["opus"] * 4 - 4)
        store = FragmentStore()
        key = fragment_key(boundary_text, None, None)
        store.put(key)

        sonnet_decision = decide_cache_marking(
            block_text=boundary_text,
            fragment_key=key,
            fragment_store=store,
            model="claude-sonnet-4-5",
        )
        opus_decision = decide_cache_marking(
            block_text=boundary_text,
            fragment_key=key,
            fragment_store=store,
            model="claude-opus-4-1",
        )
        assert sonnet_decision.should_mark is True
        assert opus_decision.should_mark is False

    def test_unknown_model_uses_conservative_opus_floor(self) -> None:
        # Above sonnet's floor but below opus's — unknown model name should refuse.
        text = "x" * (CACHEABLE_PREFIX_MINIMUMS["sonnet"] * 4 + 40)
        store = FragmentStore()
        key = fragment_key(text, None, None)
        store.put(key)
        decision = decide_cache_marking(
            block_text=text, fragment_key=key, fragment_store=store, model="some-future-model"
        )
        assert decision.should_mark is False

    def test_never_raises_on_empty_text(self) -> None:
        store = FragmentStore()
        key = fragment_key("", None, None)
        decision = decide_cache_marking(block_text="", fragment_key=key, fragment_store=store)
        assert decision.should_mark is False


class TestBuildAnthropicRequest:
    """Request-shape assembly and cache_control placement."""

    def _tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(name="Read", description="d" * 20, input_schema={"type": "object"}),
            ToolDefinition(name="Write", description="d" * 20, input_schema={"type": "object"}),
        ]

    def test_first_call_never_marks(self) -> None:
        store = FragmentStore()
        request = build_anthropic_request(
            skill_body=LONG_TEXT,
            system_prompt=LONG_TEXT,
            tools=self._tools(),
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5",
            fragment_store=store,
        )
        assert "cache_control" not in request["system"][0]
        assert all("cache_control" not in t for t in request["tools"])

    def test_second_identical_call_marks_system_and_last_tool(self) -> None:
        store = FragmentStore()
        kwargs = {
            "skill_body": LONG_TEXT,
            "system_prompt": LONG_TEXT,
            "tools": self._tools(),
            "messages": [{"role": "user", "content": "hi"}],
            "model": "claude-sonnet-4-5",
            "fragment_store": store,
        }
        build_anthropic_request(**kwargs)  # first sighting
        request = build_anthropic_request(**kwargs)  # repeat

        assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert request["tools"][-1]["cache_control"] == {"type": "ephemeral"}
        # Non-last tools are left unmarked (Anthropic breakpoint convention:
        # one mark covers everything up to and including it).
        assert "cache_control" not in request["tools"][0]

    def test_below_minimum_never_marks_even_on_repeat(self) -> None:
        store = FragmentStore()
        kwargs = {
            "skill_body": SHORT_TEXT,
            "system_prompt": SHORT_TEXT,
            "tools": None,
            "messages": [{"role": "user", "content": "hi"}],
            "model": "claude-sonnet-4-5",
            "fragment_store": store,
        }
        build_anthropic_request(**kwargs)
        request = build_anthropic_request(**kwargs)
        assert "cache_control" not in request["system"][0]

    def test_require_repeat_false_marks_first_call(self) -> None:
        store = FragmentStore()
        request = build_anthropic_request(
            skill_body=LONG_TEXT,
            system_prompt=LONG_TEXT,
            tools=self._tools(),
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5",
            fragment_store=store,
            require_repeat=False,
        )
        assert request["system"][0]["cache_control"] == {"type": "ephemeral"}

    def test_no_system_prompt_omits_system_key(self) -> None:
        store = FragmentStore()
        request = build_anthropic_request(
            skill_body="",
            system_prompt=None,
            tools=None,
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5",
            fragment_store=store,
        )
        assert "system" not in request
        assert "tools" not in request
        assert request["messages"] == [{"role": "user", "content": "hi"}]

    def test_fragment_store_records_every_call(self) -> None:
        store = FragmentStore()
        kwargs = {
            "skill_body": LONG_TEXT,
            "system_prompt": LONG_TEXT,
            "tools": None,
            "messages": [{"role": "user", "content": "hi"}],
            "model": "claude-sonnet-4-5",
            "fragment_store": store,
        }
        build_anthropic_request(**kwargs)
        build_anthropic_request(**kwargs)
        assert store.hits == 1
        assert store.misses == 1

    def _search_tool_entries(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        return [t for t in request["tools"] if t.get("type", "").startswith("tool_search_tool_")]

    def test_search_tool_injected_when_any_tool_deferred(self) -> None:
        store = FragmentStore()
        request = build_anthropic_request(
            skill_body=LONG_TEXT,
            system_prompt=LONG_TEXT,
            tools=self._tools(),
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5",
            fragment_store=store,
            defer_loading_threshold=0,
        )
        search_entries = self._search_tool_entries(request)
        assert len(search_entries) == 1
        assert search_entries[0]["type"] == "tool_search_tool_bm25_20251119"

    def test_no_search_tool_and_no_defer_when_below_threshold(self) -> None:
        store = FragmentStore()
        request = build_anthropic_request(
            skill_body=LONG_TEXT,
            system_prompt=LONG_TEXT,
            tools=self._tools(),
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5",
            fragment_store=store,
        )
        assert self._search_tool_entries(request) == []
        assert all("defer_loading" not in t for t in request["tools"])

    def test_search_tool_variant_regex(self) -> None:
        store = FragmentStore()
        request = build_anthropic_request(
            skill_body=LONG_TEXT,
            system_prompt=LONG_TEXT,
            tools=self._tools(),
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5",
            fragment_store=store,
            defer_loading_threshold=0,
            search_tool_variant="regex",
        )
        search_entries = self._search_tool_entries(request)
        assert search_entries[0]["type"] == "tool_search_tool_regex_20251119"

    def test_search_tool_param_validates_against_installed_sdk(self) -> None:
        import pydantic
        from anthropic.types.tool_search_tool_bm25_20251119_param import (
            ToolSearchToolBm25_20251119Param,
        )

        store = FragmentStore()
        request = build_anthropic_request(
            skill_body=LONG_TEXT,
            system_prompt=LONG_TEXT,
            tools=self._tools(),
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5",
            fragment_store=store,
            defer_loading_threshold=0,
        )
        search_entry = self._search_tool_entries(request)[0]
        pydantic.TypeAdapter(ToolSearchToolBm25_20251119Param).validate_python(search_entry)


class TestDefaultBehaviorUnchanged:
    """AC: CLI shell path remains default; SDK path is opt-in only."""

    def test_orchestration_config_defaults_to_cli(self) -> None:
        from little_loops.config.orchestration import OrchestrationConfig

        config = OrchestrationConfig.from_dict({})
        assert config.request_path == "cli"

    def test_explicit_sdk_opt_in(self) -> None:
        from little_loops.config.orchestration import OrchestrationConfig

        config = OrchestrationConfig.from_dict({"request_path": "sdk"})
        assert config.request_path == "sdk"

    def test_cache_config_defaults_require_repeat_true(self) -> None:
        from little_loops.config.features import CacheConfig

        config = CacheConfig.from_dict({})
        assert config.require_repeat is True


@pytest.mark.parametrize("model", ["sonnet", "opus"])
def test_cacheable_prefix_minimums_match_documented_values(model: str) -> None:
    # Anthropic documented minimums as of the FEAT-2673 issue (confirm at
    # upgrade time — these are vendor constants, not derived).
    expected = {"sonnet": 1024, "opus": 4096}
    assert CACHEABLE_PREFIX_MINIMUMS[model] == expected[model]

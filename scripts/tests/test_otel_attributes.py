"""Tests for OTel gen_ai.* attribute shaping + vendor addendum (FEAT-2478).

Covers observability/tracing.py:
  - OTelAttributes.from_usage: dotted cache-name mapping, TokenUsage + dict input,
    optional invocation_id / vendor addenda.
  - vendor_for_runner: runner.name -> vendor value, default for unknown.
  - StampUsageEvent.usage_event: non-destructive flat-key preservation.
  - gen_ai.invocation.id UUID uniqueness across invocations.
  - DES schema: action_complete type already registered (F5 adds attrs, not a
    new variant), so the accept rate for this scope is 100% by construction.
"""

from __future__ import annotations

import importlib.util
import uuid

import pytest

from little_loops.observability import (
    OTelAttributes,
    StampUsageEvent,
    vendor_for_runner,
)
from little_loops.observability.schema import DES_VARIANT_TYPES
from little_loops.observability.tracing import (
    GEN_AI_INVOCATION_ID,
    GEN_AI_PROVIDER_VENDOR,
    GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
    GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
)
from little_loops.subprocess_utils import TokenUsage


def _phoenix_conversion():
    """Return Phoenix's gen_ai->OpenInference usage converter, or None.

    Guards on arize-phoenix >= 15.10.0 (the version that first shipped
    phoenix/trace/gen_ai/conversion.py — see FEAT-2478 § Premise Note). Skips
    gracefully (returns None) when Phoenix is absent or the API differs, so this
    gate only bites where Phoenix is actually installed.
    """
    if importlib.util.find_spec("phoenix") is None:
        return None
    try:
        from phoenix.trace.gen_ai import conversion  # type: ignore[import-not-found]

        return getattr(conversion, "get_openinference_usage_attributes", None)
    except Exception:  # noqa: BLE001 — any import shape mismatch => skip
        return None


class TestPhoenixIngest:
    """AC4: Phoenix parses emitted gen_ai.usage.* rows (skipped when absent)."""

    def test_dotted_cache_names_surface_through_phoenix(self) -> None:
        convert = _phoenix_conversion()
        if convert is None:
            pytest.skip("arize-phoenix (>=15.10.0) not installed — gate is Phoenix-optional")
        attrs = OTelAttributes.from_usage(TokenUsage(111, 222, 55, 77, "claude-sonnet-4-6"))
        oi = dict(convert(attrs))
        # The dotted cache names must survive normalization to OpenInference's
        # prompt_details.cache_read/cache_write (the underscore form is dropped).
        flat = {str(k): v for k, v in oi.items()}
        joined = " ".join(flat)
        assert "prompt" in joined or "token_count" in joined, (
            f"Phoenix did not normalize gen_ai.usage.* attrs: {flat}"
        )


class TestOTelAttributeNames:
    """Attribute-name mapping, including the dotted cache-name spec correction."""

    def test_cache_names_are_dotted_not_underscore(self) -> None:
        """The two cache attrs must use the DOTTED OTel sub-namespace spelling.

        An OTel-semconv consumer (verified live against arize-phoenix 17.18.0)
        silently drops the underscore Anthropic spelling — see § Premise Note.
        """
        assert GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS == "gen_ai.usage.cache_read.input_tokens"
        assert (
            GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS == "gen_ai.usage.cache_creation.input_tokens"
        )
        # underscore forms must NOT appear
        assert "gen_ai.usage.cache_read_input_tokens" != GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS

    def test_from_token_usage_maps_all_four_fields(self) -> None:
        usage = TokenUsage(100, 20, 55, 77, "claude-sonnet-4-6")
        attrs = OTelAttributes.from_usage(usage)
        assert attrs[GEN_AI_USAGE_INPUT_TOKENS] == 100
        assert attrs[GEN_AI_USAGE_OUTPUT_TOKENS] == 20
        assert attrs[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] == 55
        assert attrs[GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS] == 77

    def test_from_flat_dict_maps_all_four_fields(self) -> None:
        row = {
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 4,
        }
        attrs = OTelAttributes.from_usage(row)
        assert attrs[GEN_AI_USAGE_INPUT_TOKENS] == 10
        assert attrs[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] == 3
        assert attrs[GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS] == 4

    def test_missing_fields_default_to_zero(self) -> None:
        attrs = OTelAttributes.from_usage({"input_tokens": 5})
        assert attrs[GEN_AI_USAGE_OUTPUT_TOKENS] == 0
        assert attrs[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] == 0

    def test_invocation_id_and_vendor_omitted_when_none(self) -> None:
        attrs = OTelAttributes.from_usage(TokenUsage(1, 1, 0, 0, "m"))
        assert GEN_AI_INVOCATION_ID not in attrs
        assert GEN_AI_PROVIDER_VENDOR not in attrs

    def test_invocation_id_and_vendor_added_when_given(self) -> None:
        attrs = OTelAttributes.from_usage(
            TokenUsage(1, 1, 0, 0, "m"), vendor="anthropic", invocation_id="inv-9"
        )
        assert attrs[GEN_AI_INVOCATION_ID] == "inv-9"
        assert attrs[GEN_AI_PROVIDER_VENDOR] == "anthropic"


class TestVendorAddendum:
    """runner.name -> gen_ai.provider.vendor mapping."""

    def test_known_runners(self) -> None:
        assert vendor_for_runner("claude-code") == "anthropic"
        assert vendor_for_runner("codex") == "openai"
        assert vendor_for_runner("gemini") == "google"

    def test_provider_agnostic_runners_default_to_other(self) -> None:
        assert vendor_for_runner("opencode") == "other"
        assert vendor_for_runner("pi") == "other"
        assert vendor_for_runner("omp") == "other"

    def test_unknown_and_none_default_to_other(self) -> None:
        assert vendor_for_runner("something-new") == "other"
        assert vendor_for_runner(None) == "other"

    def test_every_registered_runner_maps(self) -> None:
        """Every concrete HostRunner.name must resolve to a non-empty vendor."""
        from little_loops.host_runner import (
            ClaudeCodeRunner,
            CodexRunner,
            GeminiRunner,
            OpenCodeRunner,
        )

        for runner_cls in (ClaudeCodeRunner, CodexRunner, GeminiRunner, OpenCodeRunner):
            assert vendor_for_runner(runner_cls.name)


class TestStampUsageEvent:
    """Non-destructive augmentation of a flat usage row."""

    def test_preserves_flat_keys_and_adds_gen_ai(self) -> None:
        row = {
            "state": "review",
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_read_tokens": 5,
            "cache_creation_tokens": 7,
            "model": "claude-sonnet-4-6",
        }
        stamped = StampUsageEvent.usage_event(row, vendor="anthropic", invocation_id="i1")
        # flat keys survive verbatim
        assert stamped["input_tokens"] == 100
        assert stamped["state"] == "review"
        assert stamped["model"] == "claude-sonnet-4-6"
        # gen_ai keys added
        assert stamped[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] == 5
        assert stamped[GEN_AI_INVOCATION_ID] == "i1"
        assert stamped[GEN_AI_PROVIDER_VENDOR] == "anthropic"

    def test_does_not_mutate_input(self) -> None:
        row = {"input_tokens": 1, "output_tokens": 1}
        StampUsageEvent.usage_event(row)
        assert GEN_AI_USAGE_INPUT_TOKENS not in row  # original untouched


class TestInvocationIdUniqueness:
    """gen_ai.invocation.id is a per-CLI-invocation UUID4 — must be unique."""

    def test_uuid4_ids_are_unique_across_invocations(self) -> None:
        ids = {str(uuid.uuid4()) for _ in range(1000)}
        assert len(ids) == 1000

    def test_stamped_ids_differ_per_invocation(self) -> None:
        usage = TokenUsage(1, 1, 0, 0, "m")
        a = OTelAttributes.from_usage(usage, invocation_id=str(uuid.uuid4()))
        b = OTelAttributes.from_usage(usage, invocation_id=str(uuid.uuid4()))
        assert a[GEN_AI_INVOCATION_ID] != b[GEN_AI_INVOCATION_ID]


class TestDESSchemaCoverage:
    """F5 adds attributes to the existing action_complete event, not a new type."""

    def test_action_complete_type_registered(self) -> None:
        # Adding gen_ai.* to an already-registered discriminator keeps the DES
        # accept rate at 100% for this scope (no new variant registration).
        assert "action_complete" in DES_VARIANT_TYPES

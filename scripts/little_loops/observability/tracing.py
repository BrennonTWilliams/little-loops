"""OTel ``gen_ai.*`` attribute shaping + streaming-parity primitives (FEAT-2478).

This module is the F5 landing site named by ``observability/audit.py``. It emits
OpenTelemetry-semantic-convention-shaped ``gen_ai.usage.*`` attribute dicts from
little-loops' internal token-usage rows *without* an OTel SDK in-process — the
canonical names are produced as plain dicts that downstream consumers (Phoenix,
Langfuse, Grafana, or the local ``history.db`` reader) can index directly.

Three primitives:

``OTelAttributes.from_usage(usage, vendor=None, invocation_id=None)``
    Map a :class:`~little_loops.subprocess_utils.TokenUsage` (or an equivalent
    flat dict) to the canonical dotted ``gen_ai.*`` attribute dict.

``StampUsageEvent.usage_event(row, vendor=None, invocation_id=None)``
    Non-destructively augment an existing flat usage row (e.g. a ``usage.jsonl``
    entry) with the ``gen_ai.*`` keys, preserving the original flat keys.

``StreamingParityChecker.diff(blocking_usage, streaming_usage)``
    Per-field relative diff between a blocking (``messages.create``) and a
    streaming (``messages.stream``) usage snapshot; gates the ENH-2479 0.1%
    parity threshold.

Cache-token names are **dotted sub-namespaces**
(``gen_ai.usage.cache_read.input_tokens``), not the underscore Anthropic-API
spelling — an OTel-semconv consumer (verified live against ``arize-phoenix
17.18.0``) silently drops the underscore form. See FEAT-2478 § Premise Note.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- Canonical OTel semantic-convention attribute names (dotted) -------------
# The two cache names are DOTTED sub-namespaces per OTel semconv, NOT the
# underscore Anthropic-API spelling (which OTel consumers silently drop).
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = "gen_ai.usage.cache_creation.input_tokens"
GEN_AI_INVOCATION_ID = "gen_ai.invocation.id"
GEN_AI_PROVIDER_VENDOR = "gen_ai.provider.vendor"

# Internal flat field name -> canonical dotted OTel attribute name. ``input_tokens``
# / ``output_tokens`` happen to be identical in both conventions; only the two
# cache fields differ (underscore -> dotted). See FEAT-2478 § Premise Note.
_FIELD_TO_OTEL: dict[str, str] = {
    "input_tokens": GEN_AI_USAGE_INPUT_TOKENS,
    "output_tokens": GEN_AI_USAGE_OUTPUT_TOKENS,
    "cache_read_tokens": GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
    "cache_creation_tokens": GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
}

# The four internal numeric token fields, in canonical order.
_TOKEN_FIELDS: tuple[str, ...] = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
)

# --- Provider vendor addendum ------------------------------------------------
# ``HostRunner.name`` -> ``gen_ai.provider.vendor`` value. This is a non-OTel-enum
# addendum (OTel semconv has no closed vendor enum), so unknown runners map to
# ``other`` rather than raising. ``opencode``/``pi``/``omp`` are provider-agnostic
# at the runner level, so their vendor is not knowable here and defaults to
# ``other``; a future per-invocation writer may refine this from the resolved model.
DEFAULT_VENDOR = "other"
_VENDOR_BY_RUNNER: dict[str, str] = {
    "claude-code": "anthropic",
    "codex": "openai",
    "gemini": "google",
    "opencode": DEFAULT_VENDOR,
    "pi": DEFAULT_VENDOR,
    "omp": DEFAULT_VENDOR,
}


def vendor_for_runner(name: str | None) -> str:
    """Return the ``gen_ai.provider.vendor`` addendum for a ``HostRunner.name``.

    Unknown / ``None`` runner names map to :data:`DEFAULT_VENDOR` (``"other"``)
    rather than raising — the vendor addendum is best-effort metadata.
    """
    if not name:
        return DEFAULT_VENDOR
    return _VENDOR_BY_RUNNER.get(name, DEFAULT_VENDOR)


def _read_token(source: Any, field: str) -> int:
    """Read one internal token field from a TokenUsage-like object or a dict."""
    if isinstance(source, dict):
        value = source.get(field, 0)
    else:
        value = getattr(source, field, 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class OTelAttributes:
    """Shape internal token-usage rows into canonical OTel ``gen_ai.*`` dicts."""

    @staticmethod
    def from_usage(
        usage: Any,
        vendor: str | None = None,
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the canonical dotted ``gen_ai.*`` attribute dict for *usage*.

        *usage* may be a :class:`~little_loops.subprocess_utils.TokenUsage`
        (attribute access) or an equivalent flat dict (``input_tokens``,
        ``output_tokens``, ``cache_read_tokens``, ``cache_creation_tokens``).
        The two cache attributes use the **dotted** OTel sub-namespace spelling.

        *vendor* / *invocation_id*, when provided, add
        ``gen_ai.provider.vendor`` / ``gen_ai.invocation.id`` respectively.
        """
        attrs: dict[str, Any] = {
            _FIELD_TO_OTEL[field]: _read_token(usage, field) for field in _TOKEN_FIELDS
        }
        if invocation_id is not None:
            attrs[GEN_AI_INVOCATION_ID] = invocation_id
        if vendor is not None:
            attrs[GEN_AI_PROVIDER_VENDOR] = vendor
        return attrs


class StampUsageEvent:
    """Augment an existing flat usage row with ``gen_ai.*`` keys, non-destructively."""

    @staticmethod
    def usage_event(
        row: dict[str, Any],
        vendor: str | None = None,
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        """Return a new dict: *row*'s flat keys plus the ``gen_ai.*`` addenda.

        The original flat keys (``input_tokens`` etc.) are preserved so existing
        flat-key consumers (``fsm/cost_graph.py``, ``_print_usage_summary``) keep
        working; the dotted ``gen_ai.*`` keys are added alongside.
        """
        stamped = dict(row)
        stamped.update(OTelAttributes.from_usage(row, vendor=vendor, invocation_id=invocation_id))
        return stamped


@dataclass(frozen=True)
class ParityDiff:
    """One field's blocking-vs-streaming relative diff."""

    field: str
    blocking: float
    streaming: float
    diff_pct: float  # relative fraction: 0.001 == 0.1%
    within_threshold: bool


class StreamingParityChecker:
    """Compare blocking (``messages.create``) vs streaming (``messages.stream``) usage.

    Locks the ENH-2479 parity assertion: every token field must match within
    *threshold* (default 0.1% relative). Covers all four fields, not
    ``cache_read`` only — drift in any field would silently pass a
    single-field gate (see ENH-2479 Decision 1).
    """

    TOKEN_FIELDS: tuple[str, ...] = _TOKEN_FIELDS
    DEFAULT_THRESHOLD = 0.001  # 0.1% relative

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold

    @staticmethod
    def _relative_diff(blocking: float, streaming: float) -> float:
        """Relative diff floored-denominator at 1 to bound the all-zero case."""
        return abs(blocking - streaming) / max(abs(blocking), 1.0)

    def diff(
        self,
        blocking_usage: Any,
        streaming_usage: Any,
    ) -> list[ParityDiff]:
        """Return a :class:`ParityDiff` per token field (canonical order)."""
        diffs: list[ParityDiff] = []
        for field in self.TOKEN_FIELDS:
            b = float(_read_token(blocking_usage, field))
            s = float(_read_token(streaming_usage, field))
            rel = self._relative_diff(b, s)
            diffs.append(
                ParityDiff(
                    field=field,
                    blocking=b,
                    streaming=s,
                    diff_pct=rel,
                    within_threshold=rel <= self.threshold,
                )
            )
        return diffs

    def within_threshold(self, blocking_usage: Any, streaming_usage: Any) -> bool:
        """True iff every token field is within *threshold*."""
        return all(d.within_threshold for d in self.diff(blocking_usage, streaming_usage))

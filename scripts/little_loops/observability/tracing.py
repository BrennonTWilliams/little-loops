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
    "anthropic-api": "anthropic",  # ENH-3538: sdk/batch path (host_runner._usage_from_response)
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


def _read_token(source: Any, field: str) -> int | None:
    """Read one internal token field from a TokenUsage-like object or a dict.

    Returns ``None`` when the field is absent, ``None`` or non-numeric: an
    unknown component is never coerced to zero (ENH-3538). A reported ``0``
    stays ``0``.
    """
    if isinstance(source, dict):
        value = source.get(field)
    else:
        value = getattr(source, field, None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_partial(source: Any, field: str) -> bool:
    """True when *field* is a subtotal with contributors missing (``<field>_missing > 0``)."""
    key = f"{field}_missing"
    raw = source.get(key) if isinstance(source, dict) else getattr(source, key, None)
    if raw is None:
        return False
    try:
        return int(raw) > 0
    except (TypeError, ValueError):
        return False


def _complete_token(source: Any, field: str) -> int | None:
    """Return the token value only when it is known and not a partial subtotal."""
    if _is_partial(source, field):
        return None
    return _read_token(source, field)


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
        # ENH-3538: omit a component's attribute when it is None or a partial
        # subtotal; complete sibling components stay exportable.
        attrs: dict[str, Any] = {}
        for field in _TOKEN_FIELDS:
            value = _complete_token(usage, field)
            if value is not None:
                attrs[_FIELD_TO_OTEL[field]] = value
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
    blocking: float | None  # None: unknown or partial (ENH-3538)
    streaming: float | None
    diff_pct: float | None  # relative fraction: 0.001 == 0.1%; None when incomplete
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
            b_raw = _complete_token(blocking_usage, field)
            s_raw = _complete_token(streaming_usage, field)
            if b_raw is None or s_raw is None:
                # ENH-3538: an incomplete comparison is unavailable, never
                # equal — two unknowns are not two zeros.
                diffs.append(
                    ParityDiff(
                        field=field,
                        blocking=None if b_raw is None else float(b_raw),
                        streaming=None if s_raw is None else float(s_raw),
                        diff_pct=None,
                        within_threshold=False,
                    )
                )
                continue
            b, s = float(b_raw), float(s_raw)
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

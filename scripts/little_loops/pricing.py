"""Model pricing constants for token cost estimation.

Prices are in USD per million tokens ($/Mtok).
Source: Anthropic pricing page (as of 2026-09-24; BUG-3564 corrected stale
Sonnet 5, Opus 4.5-4.7 and Haiku 4.5 rates; ENH-2745 added
claude-sonnet-5/claude-opus-4-8/claude-fable-5). Sonnet 5's introductory
$2/$10 rate became its standard price, so it lives in `MODEL_PRICING`.
`INTRO_PRICING` (ENH-2835) stays as the mechanism for time-bounded launch
rates that override `MODEL_PRICING` while active. claude-opus-5 added
2026-08-29 (FEAT-3183): it was the largest source of null `cost_usd` rows in
`usage_events` (37,269 rows on this repo's own history.db at time of fix).
This closes the gap going forward only — already-written null rows are not
recomputed, so `ll-history quality`'s cost-coverage gate remains required.
"""

from __future__ import annotations

from datetime import date

# Per-model pricing: {model_id: {token_type: usd_per_million}}
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Claude 5.x / current-generation
    "claude-fable-5": {
        "input": 10.0,
        "output": 50.0,
        "cache_read": 1.0,
        "cache_creation": 12.50,
    },
    "claude-opus-4-8": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.50,
        "cache_creation": 6.25,
    },
    "claude-opus-5": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.50,
        "cache_creation": 6.25,
    },
    "claude-sonnet-5": {
        "input": 2.0,
        "output": 10.0,
        "cache_read": 0.20,
        "cache_creation": 2.50,
    },
    # Claude 4.x
    "claude-opus-4-7": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.50,
        "cache_creation": 6.25,
    },
    "claude-opus-4-6": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.50,
        "cache_creation": 6.25,
    },
    "claude-sonnet-4-6": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_creation": 3.75,
    },
    "claude-haiku-4-5-20251001": {
        "input": 1.0,
        "output": 5.0,
        "cache_read": 0.10,
        "cache_creation": 1.25,
    },
    "claude-opus-4-5": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.50,
        "cache_creation": 6.25,
    },
    # Claude 3.x (legacy, may still appear in logs)
    "claude-sonnet-3-7": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_creation": 3.75,
    },
    "claude-haiku-3-5": {
        "input": 0.80,
        "output": 4.0,
        "cache_read": 0.08,
        "cache_creation": 1.0,
    },
}


# Time-bounded introductory rates that override MODEL_PRICING while active.
# {model_id: {"expires": iso_date, token_type: usd_per_million, ...}}
INTRO_PRICING: dict[str, dict[str, float | str]] = {}


BATCH_DISCOUNT = 0.5
"""Flat discount applied to both input and output tokens under the Anthropic
Message Batches API (FEAT-2710, EPIC-2456). Stacks with prompt caching —
applied uniformly across all four token types since Anthropic's batch
discount is a flat 50% off the synchronous per-token rate, cache-adjusted
rates included."""


def estimate_cost_usd(
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None = 0,
    cache_creation_tokens: int | None = 0,
    is_batch: bool = False,
) -> float | None:
    """Estimate cost in USD for a token usage event.

    Returns None if the model is not in MODEL_PRICING, or if any token
    component is None (unknown): an incomplete observation is never priced
    (ENH-3538).

    ``is_batch`` applies the flat 50% Message Batches API discount
    (:data:`BATCH_DISCOUNT`) to the computed total. Appended at the end of
    the signature (not inserted) so existing positional callers
    (``fsm/cost_graph.py``, ``session_store.py``) are unaffected.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return None
    if (
        input_tokens is None
        or output_tokens is None
        or cache_read_tokens is None
        or cache_creation_tokens is None
    ):
        return None
    intro = INTRO_PRICING.get(model)
    if intro is not None and date.today() <= date.fromisoformat(str(intro["expires"])):
        input_rate, output_rate = float(intro["input"]), float(intro["output"])
        cache_read_rate = float(intro["cache_read"])
        cache_creation_rate = float(intro["cache_creation"])
    else:
        input_rate, output_rate = pricing["input"], pricing["output"]
        cache_read_rate, cache_creation_rate = pricing["cache_read"], pricing["cache_creation"]
    per_m = 1_000_000.0
    cost = (
        input_tokens * input_rate / per_m
        + output_tokens * output_rate / per_m
        + cache_read_tokens * cache_read_rate / per_m
        + cache_creation_tokens * cache_creation_rate / per_m
    )
    if is_batch:
        cost *= BATCH_DISCOUNT
    return cost

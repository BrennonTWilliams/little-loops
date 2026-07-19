"""Cache-marking cost oracle (FEAT-2673, EPIC-2456 F1 — Goal #3).

Decides which stable prompt blocks (system / tool / stable-skill) are safe
to mark with ``cache_control: {"type": "ephemeral", ...}`` without risking
the unamortized 1.25x write premium (Anthropic prompt caching: writes cost
1.25x, reads cost 0.1x — marking a block that's never reused is a pure
1.25x loss with the 0.1x discount unreachable).

Two independent gates must both pass before a block is marked:

1. **Cacheable-prefix minimum** — the provider ignores ``cache_control``
   below a per-model token floor (Anthropic: 1024 tokens for the Sonnet
   family, 4096 tokens for Opus; confirmed current as of the
   ``.ll/learning-tests/anthropic.md`` proof date). Unknown model names use
   the conservative (higher) Opus floor rather than guessing low.
2. **Reuse-stability signal** — sourced from FEAT-2671's
   :class:`~little_loops.prompts.fragment_store.FragmentStore`, which tracks
   only membership (has this exact fragment key been seen before?), not a
   per-key repeat count. A block is only marked once its content-hash key
   has already been observed at least once: marking on first sight risks
   paying the 1.25x write premium on a block that's never reused, so the
   oracle waits for one observed repeat before it will authorize a write.
   ``require_repeat=False`` disables this gate for callers with a stronger
   external stability signal. A richer reuse-*frequency* threshold
   (EPIC-2456 OQ #5, e.g. "mark only after N repeats") needs empirical
   derivation from ``history.db`` reuse distributions plus a per-key counter
   FragmentStore doesn't yet expose — left as a future extension, not
   implemented here.

Token estimation mirrors the project-wide ``len(text) // 4`` convention
(``session_store._estimate_tokens``, ``compression/heuristic.py``) — no BPE
tokenizer exists anywhere in the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass

from little_loops.prompts.fragment_store import FragmentStore

__all__ = ["CacheMarkingDecision", "CACHEABLE_PREFIX_MINIMUMS", "decide_cache_marking"]

# Anthropic's minimum cacheable-prefix length per model family, in tokens.
# Confirm current values at implementation/upgrade time — these are vendor
# constants, not derived from any codebase signal.
CACHEABLE_PREFIX_MINIMUMS: dict[str, int] = {
    "sonnet": 1024,
    "opus": 4096,
}

# Conservative fallback for unrecognized model names: the higher of the two
# known floors, so an unmatched model never gets marked too eagerly.
_DEFAULT_MINIMUM = max(CACHEABLE_PREFIX_MINIMUMS.values())


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: 4 characters per token (project convention)."""
    return len(text) // 4


@dataclass(frozen=True)
class CacheMarkingDecision:
    """Result of :func:`decide_cache_marking` for one candidate block."""

    should_mark: bool
    reason: str


def _prefix_minimum_for(model: str) -> int:
    for family, minimum in CACHEABLE_PREFIX_MINIMUMS.items():
        if family in model.lower():
            return minimum
    return _DEFAULT_MINIMUM


def decide_cache_marking(
    *,
    block_text: str,
    fragment_key: str,
    fragment_store: FragmentStore,
    model: str = "sonnet",
    require_repeat: bool = True,
) -> CacheMarkingDecision:
    """Decide whether a block should carry ``cache_control: ephemeral``.

    ``fragment_store`` is consulted read-only via ``.get()`` (does not record
    an observation) — callers own the ``put()`` lifecycle. Reuse is judged by
    whether ``fragment_key`` has already been observed at least once before
    this call.

    Returns a :class:`CacheMarkingDecision` — never raises.
    """
    minimum = _prefix_minimum_for(model)
    tokens = _estimate_tokens(block_text)
    if tokens < minimum:
        return CacheMarkingDecision(
            should_mark=False,
            reason=f"below cacheable-prefix minimum ({tokens} < {minimum} tokens for {model!r})",
        )

    if not require_repeat:
        return CacheMarkingDecision(
            should_mark=True, reason="reuse gate disabled (require_repeat=False)"
        )

    is_repeat = fragment_store.get(fragment_key)
    if not is_repeat:
        return CacheMarkingDecision(
            should_mark=False,
            reason="fragment not yet observed as a repeat — refusing first-sight write",
        )

    return CacheMarkingDecision(should_mark=True, reason="fragment stable across prior calls")

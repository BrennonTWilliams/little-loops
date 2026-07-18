"""Content-hash fragment store (FEAT-2671, EPIC-2456 F1-prereq a).

Computes a stable SHA-256 key over the three stable prompt fragments — skill
body, system prompt, and tool definitions — and tracks whether each observed
key repeats a prior invocation. This gives the F1 cache-marking oracle
(FEAT-2673) a cheap, deterministic stability signal: a hit means the fragment
triple was byte-identical to an earlier call, so marking it
``cache_control: ephemeral`` would amortize real reads instead of paying an
unamortized 1.25x write premium. Adapted from
``BerriAI/litellm/litellm/caching/caching.py``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def fragment_key(
    skill_body: str,
    system_prompt: str | None,
    tool_definitions: list[str] | None,
) -> str:
    """Return a 64-char SHA-256 hex digest over the three stable fragments."""
    payload: dict[str, Any] = {
        "skill_body": skill_body,
        "system_prompt": system_prompt,
        "tool_definitions": tool_definitions,
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class FragmentStore:
    """Small keyed store recording whether a fragment key repeats across calls."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> bool:
        """Return True if ``key`` has been observed before (a stability hit)."""
        return key in self._seen

    def put(self, key: str) -> bool:
        """Record an observation of ``key``. Return True if it was a repeat (hit)."""
        is_hit = key in self._seen
        if is_hit:
            self.hits += 1
        else:
            self.misses += 1
            self._seen.add(key)
        return is_hit

    @property
    def hit_rate_pct(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100) if total else 0.0

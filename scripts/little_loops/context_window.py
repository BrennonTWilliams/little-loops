"""Single source of truth for model → context-window size mapping.

Precedence (highest to lowest):
1. Explicit ``override`` argument (non-zero)
2. ``LL_CONTEXT_LIMIT`` environment variable (non-zero integer)
3. ``[1m]`` suffix on model id → 1_000_000
4. Exact model-id lookup in MODEL_CONTEXT_WINDOW
5. 200_000 conservative floor

# keep in sync with hooks/scripts/context-monitor.sh:get_context_limit()
"""

from __future__ import annotations

import os

# Known model context windows in tokens.
# Models not listed here fall back to the 200_000 floor.
MODEL_CONTEXT_WINDOW: dict[str, int] = {
    # Claude 4.x — 200k base context
    "claude-opus-4-8": 200_000,
    "claude-opus-4-7": 200_000,
    "claude-opus-4-6": 200_000,
    "claude-opus-4-5": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-haiku-4-5": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    # Claude 3.x (legacy)
    "claude-opus-3-7": 200_000,
    "claude-sonnet-3-7": 200_000,
    "claude-haiku-3-5": 200_000,
}

_DEFAULT_CONTEXT_WINDOW = 200_000
_1M_CONTEXT_WINDOW = 1_000_000


def context_window_for(model: str | None, override: int | None = None) -> int:
    """Resolve context-window size for a model id.

    Args:
        model: Model identifier string (e.g. ``"claude-opus-4-8[1m]"``),
               or ``None`` to use env-var / floor.
        override: Explicit token count; takes top precedence when non-zero.

    Returns:
        Context window size in tokens (always a positive int).
    """
    # 1. Explicit override argument
    if override:
        return int(override)

    # 2. LL_CONTEXT_LIMIT environment variable
    env_val = os.environ.get("LL_CONTEXT_LIMIT", "")
    if env_val:
        try:
            parsed = int(env_val)
            if parsed > 0:
                return parsed
        except ValueError:
            pass

    if model is None:
        return _DEFAULT_CONTEXT_WINDOW

    # 3. [1m] suffix → 1M context
    if model.endswith("[1m]"):
        return _1M_CONTEXT_WINDOW

    # 4. Exact model-id lookup
    window = MODEL_CONTEXT_WINDOW.get(model)
    if window is not None:
        return window

    # 5. Conservative floor
    return _DEFAULT_CONTEXT_WINDOW

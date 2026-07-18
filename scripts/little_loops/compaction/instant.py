"""Instant structural compaction: StreamingLLM eviction + 6-section semantic summary.

Two complementary passes over a live message list (FEAT-2598):

- ``evict_sink_and_window``: StreamingLLM-style sink+window structural eviction.
  Message-granularity (this project operates at message granularity, not
  KV-cache/token granularity), always-on, no LLM cost, preserves
  system/CLAUDE.md blocks unconditionally.
- ``summarize_6_section``: Letta-style sliding-window selection feeding a
  6-section cookbook-schema LLM summary, gated on the soft token threshold.
"""

from __future__ import annotations

from little_loops.context_window import context_window_for

# Soft threshold (tokens) at which background 6-section summarization fires.
SOFT_THRESHOLD_TOKENS = 7500

# Safety inflation applied to the byte/4 token-estimate heuristic
# (session_store._estimate_tokens convention) when computing sliding-window budgets.
APPROX_TOKEN_SAFETY_MARGIN = 1.3

SECTION_HEADERS = (
    "User Intent",
    "Completed Work",
    "Errors & Corrections",
    "Active Work",
    "Pending Tasks",
    "Key References",
)


def evict_sink_and_window(
    messages: list[dict],
    sink_n: int = 4,
    window_n: int = 20,
) -> list[dict]:
    """StreamingLLM-style eviction: keep the first ``sink_n`` + last ``window_n``
    messages, dropping the middle.

    ``system``-role messages (system prompt / CLAUDE.md blocks) are preserved
    unconditionally and excluded from the sink/window accounting. Returns the
    original list unchanged if there is nothing to prune.
    """
    system_indices = {i for i, m in enumerate(messages) if m.get("role") == "system"}
    prunable = [i for i in range(len(messages)) if i not in system_indices]

    if len(prunable) <= sink_n + window_n:
        return list(messages)

    keep = set(system_indices)
    keep.update(prunable[:sink_n])
    if window_n:
        keep.update(prunable[-window_n:])

    return [m for i, m in enumerate(messages) if i in keep]


def is_valid_cutoff(messages: list[dict], index: int) -> bool:
    """True when ``index`` sits at a user-turn boundary.

    A safe point to cut the sliding window without splitting an
    assistant/tool-call sequence. Boundary indices (0 or len(messages)) are
    always valid.
    """
    if index <= 0 or index >= len(messages):
        return True
    return messages[index].get("role") == "user"


def compute_goal_tokens(
    model: str | None = None,
    sliding_window_percentage: float = 0.3,
    override: int | None = None,
) -> int:
    """Letta-style goal token budget: ``(1 - sliding_window_percentage) * context_window``."""
    window = context_window_for(model, override)
    return int((1 - sliding_window_percentage) * window)


def select_sliding_window(
    messages: list[dict],
    model: str | None = None,
    sliding_window_percentage: float = 0.3,
    override: int | None = None,
) -> list[dict]:
    """Select the most recent messages fitting within the goal-token budget,
    snapped to a valid (user-turn) cutoff boundary.

    Uses the project's byte/4 token-estimate heuristic inflated by
    ``APPROX_TOKEN_SAFETY_MARGIN``.
    """
    goal_tokens = compute_goal_tokens(model, sliding_window_percentage, override)
    budget = int(goal_tokens / APPROX_TOKEN_SAFETY_MARGIN)

    kept_tokens = 0
    cutoff = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        tok = len(str(messages[i].get("content", ""))) // 4
        if kept_tokens + tok > budget and kept_tokens > 0:
            cutoff = i + 1
            break
        kept_tokens += tok
        cutoff = i

    while cutoff < len(messages) and not is_valid_cutoff(messages, cutoff):
        cutoff += 1

    return messages[cutoff:]


def summarize_6_section(
    messages: list[str] | list[dict],
    *,
    model: str | None = None,
    timeout: int = 60,
) -> str:
    """Produce a 6-section cookbook-style summary via the sanctioned host-CLI path.

    Sections (verbatim headers): User Intent / Completed Work / Errors &
    Corrections / Active Work / Pending Tasks / Key References. Reuses
    ``session_store._call_llm_for_summary`` for the host invocation (same
    abstraction ``_summarize_block`` uses — see ``.claude/CLAUDE.md`` § Host
    CLI Abstraction). Falls back to a deterministic empty-section skeleton if
    the LLM call fails, so a well-shaped summary is always produced.
    """
    from little_loops.session_store import _call_llm_for_summary

    texts = [m if isinstance(m, str) else str(m.get("content", "")) for m in messages]
    block_text = "\n---\n".join(texts)

    prompt = (
        "Summarize these session messages into exactly six markdown sections, "
        "using these headers verbatim (## prefixed): "
        + ", ".join(SECTION_HEADERS)
        + ". Be concise; keep a section's header even if its body is empty.\n\n"
        + block_text
    )
    result = _call_llm_for_summary(prompt, model=model, timeout=timeout)
    if result:
        return result

    return "\n\n".join(f"## {header}\n" for header in SECTION_HEADERS)

"""Session-memory compaction: StreamingLLM eviction + 6-section schema (FEAT-2598).

Extends the existing LCM compaction surface in ``session_store`` with two
complementary passes:
- Instant structural eviction (StreamingLLM-style sink+window) — no LLM cost.
- 6-section semantic summarization (User Intent / Completed Work / Errors &
  Corrections / Active Work / Pending Tasks / Key References) — fires in a
  background thread once the soft token threshold is crossed.

Public exports:
    # Instant pass
    evict_sink_and_window: StreamingLLM-style sink+window structural eviction
    is_valid_cutoff: chunk-grouping-boundary predicate for the sliding window
    compute_goal_tokens: Letta-style goal_tokens = (1 - pct) * context_window
    select_sliding_window: recent-messages selector snapped to a valid cutoff
    summarize_6_section: 6-section cookbook-schema summarizer
    SOFT_THRESHOLD_TOKENS: token count that triggers background summarization
    APPROX_TOKEN_SAFETY_MARGIN: byte/4 heuristic safety inflation factor

    # Result wrapper
    CompactResult: dataclass wrapper over existing summary_nodes/summary_spans rows
    compact_result_for_session: build a CompactResult for one session
"""

from __future__ import annotations

from little_loops.compaction.instant import (
    APPROX_TOKEN_SAFETY_MARGIN,
    SECTION_HEADERS,
    SOFT_THRESHOLD_TOKENS,
    compute_goal_tokens,
    evict_sink_and_window,
    is_valid_cutoff,
    select_sliding_window,
    summarize_6_section,
)
from little_loops.compaction.result import CompactResult, compact_result_for_session

__all__ = [
    "APPROX_TOKEN_SAFETY_MARGIN",
    "SECTION_HEADERS",
    "SOFT_THRESHOLD_TOKENS",
    "CompactResult",
    "compact_result_for_session",
    "compute_goal_tokens",
    "evict_sink_and_window",
    "is_valid_cutoff",
    "select_sliding_window",
    "summarize_6_section",
]

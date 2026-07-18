"""Heuristic prompt compression (FEAT-2675, EPIC-2456 Tier 3).

Zero-dependency, extractive prompt compression for large-context FSM loops.
See ``heuristic.py`` for the three compression passes and the ``compress()``
entry point. No ML/pip dependency; the LLMLingua-gated benchmark comparator is
tracked separately under FEAT-2676.
"""

from __future__ import annotations

from little_loops.compression.heuristic import (
    CompressedResult,
    compress,
    compress_action_text,
    dedupe_stable_system_blocks,
    drop_stale_tool_results,
    tail_truncate_assistant_turns,
)

__all__ = [
    "CompressedResult",
    "compress",
    "compress_action_text",
    "dedupe_stable_system_blocks",
    "drop_stale_tool_results",
    "tail_truncate_assistant_turns",
]

"""Output-parsing helpers for constraining LLM output token cost (FEAT-2470).

The :mod:`little_loops.output.parse` submodule ships stop-sequence / prefill
recipes (``extract_between_tags`` and ``parse_prefilled_json``) that let callers
bound the output tokens an LLM spends emitting structured data — the pass-2 #7
technique from EPIC-2456's Tier 0. It is a sibling namespace to the top-level
:mod:`little_loops.output_parsing` module (verdict/section parsing); the two do
not overlap.
"""

from __future__ import annotations

from little_loops.output.parse import extract_between_tags, parse_prefilled_json

__all__ = ["extract_between_tags", "parse_prefilled_json"]

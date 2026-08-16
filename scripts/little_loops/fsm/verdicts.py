"""Shared LLM-judge verdict vocabulary (ENH-3185).

Single source of truth for the verdict enums declared by ``DEFAULT_LLM_SCHEMA``,
``BLIND_COMPARATOR_SCHEMA``, and the ``contract`` evaluator's inline schema
(``fsm/evaluators.py``) — the three previously each declared an independent
``enum`` list that disagreed on how many verdict values existed.
"""

from __future__ import annotations

CANNOT_JUDGE = "cannot_judge"
CANNOT_JUDGE_DISPLAY = "CANNOT JUDGE"

# Full grammar: consumed only by DEFAULT_LLM_SCHEMA, the FSM predicate path.
DEFAULT_VERDICT_ENUM: tuple[str, ...] = ("yes", "no", "blocked", "partial", CANNOT_JUDGE)

# Binary subset: consumed by BLIND_COMPARATOR_SCHEMA and the `contract`
# evaluator's inline schema. Neither is an abstention consumer (AC8) — their
# aggregation logic folds any non-"yes" verdict to "no"/"not aligned", so
# admitting cannot_judge here would silently coerce an abstention into a
# failure rather than surfacing it.
BINARY_VERDICT_ENUM: tuple[str, ...] = ("yes", "no")


def is_abstention_verdict(verdict: str) -> bool:
    """True for ``cannot_judge`` and its ``_uncertain``-suffixed form (AC12)."""
    return verdict == CANNOT_JUDGE or verdict.startswith(f"{CANNOT_JUDGE}_")

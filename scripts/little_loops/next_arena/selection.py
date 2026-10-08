"""Stateless cross-type fill for ``ll-next`` (FEAT-3561 phase D).

Rank within a verb is decided by :func:`~little_loops.next_arena.candidates.assess_candidates`
(``bucket_rank``); this module only interleaves the per-verb buckets. Utility is **never**
compared across verbs, ``bucket_order`` is an input (a later slice may substitute an order),
and ``pressure`` stays ``None``.

* ``top is None``: exactly one pass over the buckets in ``bucket_order``; each bucket
  contributes its best remaining non-duplicate target (continuing past duplicates inside the
  bucket) or nothing. There is no second round to pad a dedup-exhausted bucket.
* explicit ``top=N``: round-robin rounds in ``bucket_order`` until N picks or exhaustion,
  each bucket limited by its cap (default 2).
* a ``target_key`` is selected at most once (first by round-robin order); a duplicate neither
  consumes a slot nor its bucket's cap, and the selected candidate's ``alternates`` are
  refreshed with the other candidates for the same target so deduplication hides nothing.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import Any

from little_loops.next_arena.actions import SprintActionSpec
from little_loops.next_arena.candidates import Alternate, Candidate, alternates_for
from little_loops.next_arena.graph import TERMINAL_STATUSES
from little_loops.next_arena.registry import (
    CANONICAL_VERB_ORDER,
    DEFAULT_VERB_CAP,
    registered_verbs,
)

__all__ = ["bucket_order_for", "select_candidates", "selection_policy"]


def bucket_order_for(types: Sequence[str] | None = None) -> tuple[str, ...]:
    """Registered verbs in canonical order, restricted to *types* when given.

    Unknown names raise ``ValueError`` (the CLI validates ``--type`` against the registry
    before calling this).
    """
    registered = registered_verbs()
    if types is None:
        return registered
    unknown = [t for t in types if t not in registered]
    if unknown:
        raise ValueError(f"unknown or unregistered verb(s): {', '.join(unknown)}")
    wanted = set(types)
    return tuple(v for v in registered if v in wanted)


def _cap_for(caps: Mapping[str, int], verb: str) -> int:
    cap = caps.get(verb, DEFAULT_VERB_CAP)
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise ValueError(f"cap for {verb!r} must be a positive integer, got {cap!r}")
    return cap


def _validate_top(top: int | None) -> None:
    if top is not None and (isinstance(top, bool) or not isinstance(top, int) or top < 1):
        raise ValueError(f"top must be a positive integer or None, got {top!r}")


def selection_policy(
    *, top: int | None, bucket_order: Sequence[str], caps: Mapping[str, int]
) -> dict[str, Any]:
    """Describe the fill policy for the output envelope (``selection_policy``)."""
    order = tuple(dict.fromkeys(bucket_order))
    return {
        "mode": "single_pass" if top is None else "round_robin",
        "top": top,
        "bucket_order": list(order),
        "caps": {verb: _cap_for(caps, verb) for verb in order},
        "dedup": "target_key at most once; duplicates consume neither a slot nor a cap",
        "cross_verb_utility_comparison": False,
        "pressure": None,
    }


def _annotated(chosen: Candidate, by_target: Mapping[str, Sequence[Candidate]]) -> Candidate:
    """Refresh *chosen*'s alternates with the other candidates for the same target."""
    merged: dict[str, Alternate] = {a.action_type: a for a in chosen.alternates}
    others = [
        c for c in by_target.get(chosen.target_key, ()) if c.action_type != chosen.action_type
    ]
    for alt in alternates_for(others):
        merged[alt.action_type] = alt
    ordered = tuple(merged[v] for v in CANONICAL_VERB_ORDER if v in merged) + tuple(
        merged[v] for v in sorted(merged) if v not in CANONICAL_VERB_ORDER
    )
    return replace(chosen, alternates=ordered)


def _overlap_entry(counterpart: Candidate) -> dict[str, str]:
    return {
        "target_key": counterpart.target_key,
        "action_type": counterpart.action_type,
        "display_command": counterpart.display_command,
    }


def _with_selected_overlap(picked: list[Candidate]) -> list[Candidate]:
    """Annotate selected sprint/issue-target pairs as **alternative choices**, not a bundle.

    A selected ``run-sprint`` candidate and a selected issue-target action (``issue:ID`` for any
    issue verb) overlap when the issue is a *remaining* (nonterminal) member of the sprint's
    offered snapshot. Both sides get ``evidence.selected_overlap`` -- a list of
    ``{target_key, action_type, display_command}`` of the selected counterparts, sorted by target
    key -- rendered as one text line. ``Alternate`` is not used (it links same-target candidates,
    is merged by ``action_type`` and has no target field); ``evidence`` is an open object, so no
    schema changes and nothing is persisted from it. The set depends on the selected set
    (``--top``/``--type``) and is deterministic for it. There is no suppression or scheduling.
    """
    remaining: dict[str, set[str]] = {}
    for cand in picked:
        spec = cand.action_spec
        if isinstance(spec, SprintActionSpec):
            remaining[cand.target_key] = {
                m.issue_id for m in spec.members if m.status not in TERMINAL_STATUSES
            }
    if not remaining:
        return picked
    issue_picks = {c.target: c for c in picked if c.target_key.startswith("issue:")}
    found: dict[str, list[dict[str, str]]] = defaultdict(list)
    for cand in picked:
        for issue_id in sorted(remaining.get(cand.target_key, set()) & set(issue_picks)):
            other = issue_picks[issue_id]
            found[cand.target_key].append(_overlap_entry(other))
            found[other.target_key].append(_overlap_entry(cand))
    if not found:
        return picked
    out: list[Candidate] = []
    for cand in picked:
        entries = found.get(cand.target_key)
        if entries:
            merged = {
                **cand.evidence,
                "selected_overlap": sorted(entries, key=lambda e: e["target_key"]),
            }
            cand = replace(cand, evidence=MappingProxyType(merged))
        out.append(cand)
    return out


def select_candidates(
    candidates: Sequence[Candidate],
    *,
    top: int | None,
    bucket_order: Sequence[str],
    caps: Mapping[str, int],
) -> list[Candidate]:
    """Fill recommendations from per-verb buckets without comparing utility across verbs.

    Args:
        candidates: Runnable candidates (``generate_candidates`` output, possibly filtered).
        top: ``None`` for exactly one pass over the buckets; a positive N for multi-round fill.
        bucket_order: Verbs in fill order; verbs absent from it are not selected.
        caps: Per-verb maximum picks for explicit-N fill (missing verbs default to 2).

    Raises:
        ValueError: *top* or a cap is not a positive integer.
    """
    _validate_top(top)
    order = tuple(dict.fromkeys(bucket_order))
    buckets: dict[str, list[Candidate]] = {verb: [] for verb in order}
    by_target: dict[str, list[Candidate]] = {}
    for cand in candidates:
        by_target.setdefault(cand.target_key, []).append(cand)
        if cand.action_type in buckets:
            buckets[cand.action_type].append(cand)
    for items in buckets.values():
        items.sort(key=lambda c: (c.bucket_rank, c.target_key))

    taken: set[str] = set()
    picked: list[Candidate] = []

    def take_next(verb: str, cursor: dict[str, int]) -> Candidate | None:
        items = buckets[verb]
        position = cursor[verb]
        while position < len(items) and items[position].target_key in taken:
            position += 1
        if position >= len(items):
            cursor[verb] = position
            return None
        cursor[verb] = position + 1
        chosen = items[position]
        taken.add(chosen.target_key)
        return chosen

    cursor = dict.fromkeys(order, 0)
    if top is None:
        for verb in order:
            chosen = take_next(verb, cursor)
            if chosen is not None:
                picked.append(chosen)
    else:
        counts = dict.fromkeys(order, 0)
        limits = {verb: _cap_for(caps, verb) for verb in order}
        while len(picked) < top:
            progressed = False
            for verb in order:
                if len(picked) >= top:
                    break
                if counts[verb] >= limits[verb]:
                    continue
                chosen = take_next(verb, cursor)
                if chosen is None:
                    continue
                counts[verb] += 1
                picked.append(chosen)
                progressed = True
            if not progressed:
                break
    return _with_selected_overlap([_annotated(c, by_target) for c in picked])

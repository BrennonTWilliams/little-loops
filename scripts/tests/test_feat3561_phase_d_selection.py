"""select_candidates: one-pass vs explicit-N fill, caps, dedup, alternates (FEAT-3561 D)."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from little_loops.next_arena.candidates import generate_candidates
from little_loops.next_arena.registry import registered_verbs
from little_loops.next_arena.selection import (
    bucket_order_for,
    select_candidates,
    selection_policy,
)
from tests.next_arena_candidates_support import (
    FORMAT_ENTRY,
    VERIFY_ENTRY,
    fake_candidate,
    issue,
    project,
    ready_issue,
)

IMPL = "implement-issue"
REFINE = "refine-issue"
ORDER = (IMPL, REFINE)
NO_CAPS: dict[str, int] = {}


def _ids(selected: list) -> list[tuple[str, str]]:
    return [(c.action_type, c.target) for c in selected]


def _pool() -> list:
    return [
        fake_candidate(IMPL, "BUG-001", 1),
        fake_candidate(IMPL, "BUG-002", 2),
        fake_candidate(IMPL, "BUG-003", 3),
        fake_candidate(REFINE, "BUG-001", 1),
        fake_candidate(REFINE, "BUG-004", 2),
        fake_candidate(REFINE, "BUG-005", 3),
    ]


# -------------------------------------------------------------------------- one pass


def test_omitted_top_is_exactly_one_pass_over_buckets() -> None:
    selected = select_candidates(_pool(), top=None, bucket_order=ORDER, caps=NO_CAPS)
    # refine's best (BUG-001) duplicates the implement pick, so refine continues to BUG-004;
    # no second round pads the result with BUG-002/BUG-005
    assert _ids(selected) == [(IMPL, "BUG-001"), (REFINE, "BUG-004")]


def test_one_pass_gives_each_available_bucket_its_first_round_slot() -> None:
    pool = [fake_candidate(IMPL, f"BUG-{n:03d}", n) for n in range(1, 8)]
    pool.append(fake_candidate(REFINE, "BUG-100", 1))
    selected = select_candidates(pool, top=None, bucket_order=ORDER, caps=NO_CAPS)
    assert _ids(selected) == [(IMPL, "BUG-001"), (REFINE, "BUG-100")]


def test_one_pass_bucket_exhausted_by_duplicates_contributes_nothing() -> None:
    pool = [
        fake_candidate(IMPL, "BUG-001", 1),
        fake_candidate(REFINE, "BUG-001", 1),
    ]
    selected = select_candidates(pool, top=None, bucket_order=ORDER, caps=NO_CAPS)
    assert _ids(selected) == [(IMPL, "BUG-001")]


def test_one_pass_empty_input_is_empty() -> None:
    assert select_candidates([], top=None, bucket_order=ORDER, caps=NO_CAPS) == []


def test_one_pass_ignores_caps() -> None:
    selected = select_candidates(_pool(), top=None, bucket_order=ORDER, caps={IMPL: 1, REFINE: 1})
    assert len(selected) == 2


# --------------------------------------------------------------------- explicit top N


def test_explicit_top_round_robin_in_bucket_order() -> None:
    selected = select_candidates(_pool(), top=4, bucket_order=ORDER, caps=NO_CAPS)
    assert _ids(selected) == [
        (IMPL, "BUG-001"),
        (REFINE, "BUG-004"),  # BUG-001 duplicate skipped without spending the cap
        (IMPL, "BUG-002"),
        (REFINE, "BUG-005"),
    ]


def test_explicit_top_stops_at_n_mid_round() -> None:
    selected = select_candidates(_pool(), top=3, bucket_order=ORDER, caps=NO_CAPS)
    assert _ids(selected) == [(IMPL, "BUG-001"), (REFINE, "BUG-004"), (IMPL, "BUG-002")]
    assert len(select_candidates(_pool(), top=1, bucket_order=ORDER, caps=NO_CAPS)) == 1


def test_default_cap_is_two_per_verb() -> None:
    pool = [fake_candidate(IMPL, f"BUG-{n:03d}", n) for n in range(1, 8)]
    selected = select_candidates(pool, top=10, bucket_order=ORDER, caps=NO_CAPS)
    assert _ids(selected) == [(IMPL, "BUG-001"), (IMPL, "BUG-002")]


def test_configured_caps_apply_per_verb() -> None:
    pool = [fake_candidate(IMPL, f"BUG-{n:03d}", n) for n in range(1, 8)]
    pool += [fake_candidate(REFINE, f"ENH-{n:03d}", n) for n in range(1, 8)]
    selected = select_candidates(pool, top=20, bucket_order=ORDER, caps={IMPL: 3, REFINE: 1})
    counts = {v: sum(1 for c in selected if c.action_type == v) for v in ORDER}
    assert counts == {IMPL: 3, REFINE: 1}


def test_duplicates_consume_neither_a_slot_nor_a_cap() -> None:
    pool = [
        fake_candidate(v, t, n)
        for v in ORDER
        for n, t in enumerate(("BUG-001", "BUG-002", "BUG-003"), 1)
    ]
    selected = select_candidates(pool, top=4, bucket_order=ORDER, caps={IMPL: 2, REFINE: 2})
    # round 1: impl 001, refine (001 dup -> 002); round 2: impl (002 dup -> 003), refine (003 dup)
    assert _ids(selected) == [(IMPL, "BUG-001"), (REFINE, "BUG-002"), (IMPL, "BUG-003")]
    assert len({c.target_key for c in selected}) == len(selected)


def test_target_key_appears_at_most_once_first_by_bucket_order() -> None:
    pool = _pool()
    selected = select_candidates(
        pool, top=10, bucket_order=(REFINE, IMPL), caps={IMPL: 5, REFINE: 5}
    )
    keys = [c.target_key for c in selected]
    assert len(keys) == len(set(keys)) == 5
    first = next(c for c in selected if c.target == "BUG-001")
    assert first.action_type == REFINE  # first by (substituted) round-robin order


def test_exhaustion_ends_the_fill_before_n() -> None:
    selected = select_candidates(_pool(), top=50, bucket_order=ORDER, caps={IMPL: 9, REFINE: 9})
    assert len(selected) == 5  # six candidates, one duplicate target


def test_bucket_order_is_an_input_and_does_not_change_ranks() -> None:
    pool = _pool()
    forward = select_candidates(pool, top=None, bucket_order=ORDER, caps=NO_CAPS)
    reverse = select_candidates(pool, top=None, bucket_order=(REFINE, IMPL), caps=NO_CAPS)
    assert _ids(reverse)[0][0] == REFINE
    ranks = {(c.action_type, c.target): c.bucket_rank for c in pool}
    for c in [*forward, *reverse]:
        assert c.bucket_rank == ranks[(c.action_type, c.target)]


def test_verbs_outside_bucket_order_are_not_selected() -> None:
    selected = select_candidates(_pool(), top=10, bucket_order=(REFINE,), caps={REFINE: 9})
    assert {c.action_type for c in selected} == {REFINE}


def test_input_order_does_not_matter() -> None:
    pool = _pool()
    expected = _ids(select_candidates(pool, top=5, bucket_order=ORDER, caps={IMPL: 3, REFINE: 3}))
    rng = random.Random(7)
    for _ in range(10):
        shuffled = pool[:]
        rng.shuffle(shuffled)
        got = select_candidates(shuffled, top=5, bucket_order=ORDER, caps={IMPL: 3, REFINE: 3})
        assert _ids(got) == expected


def test_selection_does_not_compare_utility_across_verbs() -> None:
    pool = [fake_candidate(IMPL, "BUG-001", 5), fake_candidate(REFINE, "BUG-002", 1)]
    # refine has far higher utility but implement is first in the canonical bucket order
    selected = select_candidates(pool, top=None, bucket_order=ORDER, caps=NO_CAPS)
    assert _ids(selected) == [(IMPL, "BUG-001"), (REFINE, "BUG-002")]


# -------------------------------------------------------------------- validation


@pytest.mark.parametrize("top", [0, -1, True])
def test_invalid_top_is_rejected(top: object) -> None:
    with pytest.raises(ValueError, match="top"):
        select_candidates(_pool(), top=top, bucket_order=ORDER, caps=NO_CAPS)  # type: ignore[arg-type]


@pytest.mark.parametrize("cap", [0, -2, True, 1.5])
def test_invalid_cap_is_rejected_for_explicit_top(cap: object) -> None:
    with pytest.raises(ValueError, match="cap"):
        select_candidates(_pool(), top=3, bucket_order=ORDER, caps={IMPL: cap})  # type: ignore[dict-item]


# ----------------------------------------------------------------------- alternates


def test_selected_candidate_keeps_alternates_for_deduplicated_target() -> None:
    selected = select_candidates(_pool(), top=None, bucket_order=ORDER, caps=NO_CAPS)
    impl = selected[0]
    assert (impl.action_type, impl.target) == (IMPL, "BUG-001")
    assert [a.action_type for a in impl.alternates] == [REFINE]
    alt = impl.alternates[0]
    assert alt.eligible is True
    assert alt.action_key == "refine-issue"
    assert alt.display_command == "/ll:refine-issue BUG-001"
    assert alt.bucket_rank == 1
    # target without a second verb has none
    assert selected[1].alternates == ()


def test_alternates_do_not_mutate_the_input_candidates() -> None:
    pool = _pool()
    before = [c.alternates for c in pool]
    select_candidates(pool, top=None, bucket_order=ORDER, caps=NO_CAPS)
    assert [c.alternates for c in pool] == before


# ----------------------------------------------------------------- policy & helpers


def test_selection_policy_describes_the_fill() -> None:
    one = selection_policy(top=None, bucket_order=ORDER, caps={IMPL: 4})
    assert one == {
        "mode": "single_pass",
        "top": None,
        "bucket_order": [IMPL, REFINE],
        "caps": {IMPL: 4, REFINE: 2},
        "dedup": "target_key at most once; duplicates consume neither a slot nor a cap",
        "cross_verb_utility_comparison": False,
        "pressure": None,
    }
    many = selection_policy(top=7, bucket_order=ORDER, caps=NO_CAPS)
    assert many["mode"] == "round_robin" and many["top"] == 7


def test_bucket_order_for_follows_registry_order() -> None:
    assert bucket_order_for() == registered_verbs()
    assert bucket_order_for([REFINE, IMPL]) == (IMPL, REFINE)
    assert bucket_order_for([REFINE]) == (REFINE,)
    with pytest.raises(ValueError, match="run-loop"):
        bucket_order_for(["run-loop"])


# ----------------------------------------------------------------------- end to end


def test_end_to_end_selection_over_a_real_snapshot(tmp_path: Path) -> None:
    files = {
        "bugs/P1-BUG-001-ready.md": issue(
            {"confidence_score": 90, "outcome_confidence": 80},
            sessions=[FORMAT_ENTRY, VERIFY_ENTRY],
        ),
        "bugs/P2-BUG-002-unformatted.md": ready_issue(),
        "bugs/P3-BUG-003-also.md": ready_issue(),
        "bugs/P2-BUG-004-gated.md": issue({"confidence_score": 20, "outcome_confidence": 20}),
    }
    state = project(tmp_path, files)
    candidates = generate_candidates(state)
    one_pass = select_candidates(candidates, top=None, bucket_order=ORDER, caps=NO_CAPS)
    assert [c.action_type for c in one_pass] == [IMPL, REFINE]
    assert len({c.target_key for c in one_pass}) == 2
    # BUG-001 is formatted+verified+ready: it has no refine action at all
    assert "BUG-001" not in {c.target for c in candidates if c.action_type == REFINE}
    explicit = select_candidates(candidates, top=6, bucket_order=ORDER, caps=NO_CAPS)
    keys = [c.target_key for c in explicit]
    assert len(keys) == len(set(keys))
    by_verb = {v: sum(1 for c in explicit if c.action_type == v) for v in ORDER}
    assert max(by_verb.values()) <= 2
    for c in explicit:
        assert c.display_command.startswith("/ll:")

"""Downstream leverage over the SCC-condensed dependency DAG (FEAT-3561 phase B)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from little_loops.next_arena.graph import OpCounter, build_leverage_index, tarjan_sccs
from little_loops.next_arena.state import ProjectState, downstream_leverage
from tests.next_arena_support import issue_text, memory_state


def _state(tmp_path: Path, issues: dict[str, dict[str, Any] | None]) -> ProjectState:
    """Build an in-memory state from ``{ID: frontmatter}`` (type from the ID prefix)."""
    dirs = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements", "EPIC": "epics"}
    files: dict[str, str] = {}
    for issue_id, fm in issues.items():
        kind, number = issue_id.split("-", 1)
        files[f"{dirs[kind]}/P3-{issue_id}-x.md"] = issue_text(fm or {})
        assert number
    return memory_state(tmp_path, files)


def test_zero_dependents_is_valid_exact_zero(tmp_path: Path) -> None:
    state = _state(tmp_path, {"FEAT-001": {}})
    lev = downstream_leverage(state, "FEAT-001")
    assert (lev.status, lev.count, lev.saturated, lev.sample) == ("exact", 0, False, ())
    assert lev.missing_reason is None and lev.in_cycle is False


def test_counts_through_blocked_by_blocks_and_depends_on_once_each(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        {
            "FEAT-001": {"blocks": ["FEAT-002"]},  # one-sided blocks
            "FEAT-002": {},
            "FEAT-003": {"blocked_by": ["FEAT-001"]},  # blocked_by
            "FEAT-004": {"depends_on": ["FEAT-001"]},  # depends_on
            "FEAT-005": {"blocked_by": ["FEAT-003", "FEAT-004"]},  # diamond: counted once
            "FEAT-006": {"blocked_by": ["FEAT-002"], "blocks": ["FEAT-005"]},
        },
    )
    lev = downstream_leverage(state, "FEAT-001")
    assert lev.status == "exact" and lev.count == 5
    assert lev.sample == ("FEAT-002", "FEAT-003", "FEAT-004", "FEAT-005", "FEAT-006")


def test_only_open_or_blocked_nonepic_leaves_are_counted(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        {
            "FEAT-001": {},
            "FEAT-002": {"blocked_by": ["FEAT-001"], "status": "blocked"},
            "FEAT-003": {"blocked_by": ["FEAT-001"], "status": "in_progress"},
            "FEAT-004": {"blocked_by": ["FEAT-003"]},  # reached THROUGH in_progress
            "FEAT-005": {"blocked_by": ["FEAT-001"], "status": "deferred"},
            "FEAT-006": {"blocked_by": ["FEAT-005"]},  # reached through deferred
            "FEAT-007": {"blocked_by": ["FEAT-001"], "status": "done"},
            "FEAT-008": {"blocked_by": ["FEAT-007"]},  # behind a terminal node: not traversed
            "EPIC-009": {"blocked_by": ["FEAT-001"]},  # EPIC containers are never counted
            "FEAT-010": {"blocked_by": ["EPIC-009"]},  # but are traversed
        },
    )
    lev = downstream_leverage(state, "FEAT-001")
    assert lev.sample == ("FEAT-002", "FEAT-004", "FEAT-006", "FEAT-010")
    assert lev.count == 4


def test_exact_below_cap_then_saturates_with_bounded_sample(tmp_path: Path) -> None:
    def fan(n: int) -> ProjectState:
        issues: dict[str, dict[str, Any] | None] = {"FEAT-001": {}}
        for i in range(n):
            issues[f"FEAT-{100 + i}"] = {"blocked_by": ["FEAT-001"]}
        return _state(tmp_path, issues)

    nine = downstream_leverage(fan(9), "FEAT-001")
    assert (nine.status, nine.count, nine.saturated, nine.count_lower_bound) == (
        "exact",
        9,
        False,
        None,
    )
    ten = downstream_leverage(fan(10), "FEAT-001")
    assert (ten.status, ten.count, ten.saturated, ten.count_lower_bound) == (
        "saturated",
        None,
        True,
        10,
    )
    assert len(ten.sample) == 10
    many = downstream_leverage(fan(40), "FEAT-001")
    assert many.saturated and many.count_lower_bound == 10 and len(many.sample) == 10
    assert many.sample == tuple(sorted(many.sample))
    # a smaller cap saturates earlier
    assert downstream_leverage(fan(9), "FEAT-001", 5).saturated


def test_cap_is_validated(tmp_path: Path) -> None:
    state = _state(tmp_path, {"FEAT-001": {}})
    with pytest.raises(ValueError, match="cap"):
        downstream_leverage(state, "FEAT-001", 0)


def test_cycle_excludes_source_and_is_reported_separately(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        {
            "FEAT-001": {"blocked_by": ["FEAT-003"]},
            "FEAT-002": {"blocked_by": ["FEAT-001"]},
            "FEAT-003": {"blocked_by": ["FEAT-002"]},
            "FEAT-004": {"blocked_by": ["FEAT-003"]},  # downstream of the cycle
        },
    )
    lev = downstream_leverage(state, "FEAT-001")
    assert lev.status == "exact" and "FEAT-001" not in lev.sample
    assert lev.sample == ("FEAT-002", "FEAT-003", "FEAT-004") and lev.count == 3
    assert lev.in_cycle and lev.cycle_ids == ("FEAT-001", "FEAT-002", "FEAT-003")
    after = downstream_leverage(state, "FEAT-004")
    assert after.count == 0 and not after.in_cycle
    # an upstream node reaching the cycle reports it without being in it
    state2 = _state(
        tmp_path,
        {
            "FEAT-000": {},
            "FEAT-001": {"blocked_by": ["FEAT-000", "FEAT-002"]},
            "FEAT-002": {"blocked_by": ["FEAT-001"]},
        },
    )
    up = downstream_leverage(state2, "FEAT-000")
    assert up.count == 2 and not up.in_cycle and up.cycle_ids == ("FEAT-001", "FEAT-002")


def test_self_loop_is_a_cycle_and_not_counted(tmp_path: Path) -> None:
    state = _state(tmp_path, {"FEAT-001": {"blocked_by": ["FEAT-001"]}})
    lev = downstream_leverage(state, "FEAT-001")
    assert lev.count == 0 and lev.in_cycle and lev.cycle_ids == ("FEAT-001",)


def test_dangling_blocks_target_is_missing_evidence_not_a_count(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        {"FEAT-001": {"blocks": ["FEAT-777"]}, "FEAT-002": {"blocked_by": ["FEAT-001"]}},
    )
    lev = downstream_leverage(state, "FEAT-001")
    assert lev.status == "exact" and lev.count == 1
    assert lev.missing_ids == ("FEAT-777",)


def test_unknown_and_terminal_sources_are_missing(tmp_path: Path) -> None:
    state = _state(tmp_path, {"FEAT-001": {"status": "done"}})
    assert downstream_leverage(state, "FEAT-404").missing_reason == "unknown_issue"
    lev = downstream_leverage(state, "FEAT-001")
    assert lev.status == "missing" and lev.missing_reason == "terminal_source"


def test_ambiguous_downstream_node_is_missing_unless_saturation_is_proven(
    tmp_path: Path,
) -> None:
    files = {
        "features/P3-FEAT-001-x.md": issue_text({}),
        "features/P3-FEAT-002-x.md": issue_text({"blocked_by": ["FEAT-001"]}),
        "features/P3-FEAT-005-x.md": issue_text({"blocked_by": ["FEAT-001"]}),
        # FEAT-009 is ambiguous (two sources) and waits on FEAT-002
        "bugs/P3-FEAT-009-a.md": issue_text({"blocked_by": ["FEAT-002"]}),
        "enhancements/P3-FEAT-009-b.md": issue_text({}),
        # reachable only through the ambiguous node: must not be trusted
        "features/P3-FEAT-010-x.md": issue_text({"blocked_by": ["FEAT-009"]}),
    }
    state = memory_state(tmp_path, files)
    lev = downstream_leverage(state, "FEAT-001")
    assert lev.status == "missing" and lev.missing_reason == "ambiguous_downstream"
    assert lev.ambiguous_ids == ("FEAT-009",)
    assert lev.partial_count == 2 and lev.count is None
    # the ambiguous node itself has no trusted fan-out
    assert downstream_leverage(state, "FEAT-009").missing_reason == "ambiguous_issue_id"

    # with enough unambiguous dependents, saturation is proven despite the ambiguity
    many = dict(files)
    for i in range(12):
        many[f"features/P3-FEAT-{200 + i}-x.md"] = issue_text({"blocked_by": ["FEAT-001"]})
    sat = downstream_leverage(memory_state(tmp_path, many), "FEAT-001")
    assert sat.status == "saturated" and sat.count_lower_bound == 10 and sat.saturated
    assert "FEAT-009" not in sat.sample and "FEAT-010" not in sat.sample


def test_index_is_cached_per_cap_and_matches_brute_force(tmp_path: Path) -> None:
    # a small random-ish DAG with cycles; compare to a naive reachability count
    edges = {
        "FEAT-001": ["FEAT-002", "FEAT-003"],
        "FEAT-002": ["FEAT-004"],
        "FEAT-003": ["FEAT-004", "FEAT-005"],
        "FEAT-004": ["FEAT-006"],
        "FEAT-005": ["FEAT-003"],  # cycle 003 <-> 005
        "FEAT-006": [],
    }
    issues: dict[str, dict[str, Any] | None] = {k: {} for k in edges}
    for src, dsts in edges.items():
        for dst in dsts:
            fm = dict(issues[dst] or {})
            fm.setdefault("blocked_by", [])
            fm["blocked_by"].append(src)
            issues[dst] = fm
    state = _state(tmp_path, issues)
    for start in edges:
        seen: set[str] = set()
        stack = list(edges[start])
        while stack:
            node = stack.pop()
            if node not in seen:
                seen.add(node)
                stack.extend(edges[node])
        seen.discard(start)
        lev = downstream_leverage(state, start)
        assert lev.count == len(seen) and set(lev.sample) == seen, start
    assert state.graph.leverage_index(10) is state.graph.leverage_index(10)
    assert state.graph.leverage_index(3) is not state.graph.leverage_index(10)


# ------------------------------------------------------------- work stays linear


def _chain(tmp_path: Path, n: int, counter: OpCounter) -> ProjectState:
    files = {
        f"features/P3-FEAT-{i:05d}-x.md": issue_text(
            {"blocked_by": [f"FEAT-{i - 1:05d}"]} if i else {}
        )
        for i in range(n)
    }
    state = memory_state(tmp_path, files)
    state.graph.leverage_index(10, counter)  # builds and caches the index once
    return state


def test_leverage_index_work_scales_linearly_on_chains(tmp_path: Path) -> None:
    small, large = OpCounter(), OpCounter()
    _chain(tmp_path, 300, small)
    state = _chain(tmp_path, 3000, large)
    assert 8 <= large.operations / small.operations <= 12  # ~10x nodes -> ~10x work
    # saturated at the head of a long chain; no per-query traversal needed
    q = OpCounter()
    lev = downstream_leverage(state, "FEAT-00000", counter=q)
    assert lev.saturated and q.operations <= 2


def test_leverage_index_work_scales_linearly_on_shared_descendants(tmp_path: Path) -> None:
    def layered(layers: int, width: int, counter: OpCounter) -> None:
        files: dict[str, str] = {}
        for layer in range(layers):
            for w in range(width):
                fm = (
                    {"blocked_by": [f"FEAT-{(layer - 1) * width + k:05d}" for k in range(width)]}
                    if layer
                    else {}
                )
                files[f"features/P3-FEAT-{layer * width + w:05d}-x.md"] = issue_text(fm)
        state = memory_state(tmp_path, files)
        build_leverage_index(state.graph, 10, counter=counter)

    small, large = OpCounter(), OpCounter()
    layered(20, 5, small)  # 100 nodes, 400 edges
    layered(200, 5, large)  # 1000 nodes, 4000 edges
    assert 8 <= large.operations / small.operations <= 12


def test_tarjan_is_iterative_on_deep_graphs() -> None:
    n = 20000  # far past the recursion limit
    nodes = [f"N{i:06d}" for i in range(n)]
    succ = {nodes[i]: [nodes[i + 1]] for i in range(n - 1)}
    succ[nodes[-1]] = [nodes[0]]  # one giant cycle
    comps = tarjan_sccs(nodes, succ)
    assert len(comps) == 1 and len(comps[0]) == n
    chain_succ = {nodes[i]: [nodes[i + 1]] for i in range(n - 1)}
    chain = tarjan_sccs(nodes, chain_succ)
    assert len(chain) == n
    assert chain[0] == (nodes[-1],)  # sinks first: reverse topological order

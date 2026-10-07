"""Identity inventory, ambiguity, unsupported filenames and prerequisite resolution (FEAT-3561 B)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from little_loops.next_arena.state import (
    Diagnostic,
    ProjectState,
    ambiguous_targets,
    build_identity_inventory,
    build_project_state,
    identity_diagnostics,
    identity_issues_for,
    supported_source,
    unique_source,
    unsupported_sources,
)
from tests.next_arena_support import (
    assert_resolver_parity,
    collect,
    make_project,
    record,
    write_issue,
)


def _codes(state: ProjectState, code: str) -> list[Diagnostic]:
    return [d for d in state.diagnostics if d.code == code]


# --------------------------------------------------------------- duplicate full IDs


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ({"status": "open"}, {"status": "open"}),  # active / active
        ({"status": "open"}, {"status": "done"}),  # active / terminal
        ({"status": "done"}, {"status": "cancelled"}),  # terminal / terminal
        (  # matching metadata
            {"id": "BUG-010", "status": "open", "priority": "P2"},
            {"id": "BUG-010", "status": "open", "priority": "P2"},
        ),
    ],
)
def test_duplicate_full_id_is_ambiguous_and_never_satisfies_an_edge(
    tmp_path: Path, first: dict[str, Any], second: dict[str, Any]
) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-010-a.md", first)
    write_issue(tmp_path, "features/P2-BUG-010-b.md", second)
    write_issue(tmp_path, "features/P3-FEAT-020-dep.md", {"blocked_by": ["BUG-010"]})
    write_issue(tmp_path, "features/P3-FEAT-021-free.md", {})
    state = collect(tmp_path)

    amb = ambiguous_targets(state)
    assert set(amb) == {"BUG-010"}
    assert amb["BUG-010"].paths == (
        ".issues/bugs/P3-BUG-010-a.md",
        ".issues/features/P2-BUG-010-b.md",
    )
    assert "duplicate_full_id" in amb["BUG-010"].reasons
    diags = _codes(state, "ambiguous_issue_id")
    assert len(diags) == 1 and diags[0].paths == amb["BUG-010"].paths
    # the dependent stays unresolved even when every conflicting source is terminal
    pending = state.graph.unresolved_for("FEAT-020")
    assert [(p.prerequisite_id, p.reason) for p in pending] == [("BUG-010", "ambiguous_issue_id")]
    assert pending[0].source_paths == amb["BUG-010"].paths
    # unaffected targets stay clean and usable
    assert identity_issues_for(state, "FEAT-021") == ()
    assert supported_source(state, "FEAT-021") is not None
    assert supported_source(state, "BUG-010") is None
    assert unique_source(state, "BUG-010") is None
    assert [d.code for d in identity_issues_for(state, "BUG-010")] == ["ambiguous_issue_id"]


def test_legacy_directory_collision_is_ambiguous(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-010-a.md", {"status": "open"})
    write_issue(tmp_path, "completed/P3-BUG-010-a.md", {"status": "done"})
    write_issue(tmp_path, "features/P3-FEAT-020-dep.md", {"blocked_by": ["BUG-010"]})
    state = collect(tmp_path)
    assert ambiguous_targets(state)["BUG-010"].paths == (
        ".issues/bugs/P3-BUG-010-a.md",
        ".issues/completed/P3-BUG-010-a.md",
    )
    assert not state.graph.prerequisites_satisfied("FEAT-020")


def test_ambiguity_is_independent_of_record_order(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-010-a.md", {"status": "open", "blocks": ["FEAT-030"]})
    write_issue(tmp_path, "features/P2-BUG-010-b.md", {"status": "done", "blocks": ["FEAT-031"]})
    write_issue(tmp_path, "bugs/P3-BUG-050-a.md", {})
    write_issue(tmp_path, "features/P3-FEAT-050-b.md", {})
    write_issue(tmp_path, "features/P3-FEAT-030-t.md", {})
    write_issue(tmp_path, "features/P3-FEAT-031-t.md", {})
    state = collect(tmp_path)
    forward = build_identity_inventory(state.records)
    backward = build_identity_inventory(list(reversed(state.records)))
    assert forward == backward == state.identity
    rebuilt = build_project_state(
        list(reversed(state.records)),
        project_root=state.project_root,
        as_of=state.as_of,
        config=state.config,
        formatting_policy=state.formatting_policy,
        thresholds=state.thresholds,
    )
    assert rebuilt.identity == state.identity
    assert rebuilt.graph == state.graph
    assert rebuilt.diagnostics == state.diagnostics


def test_one_sided_blocks_from_every_conflicting_source_are_retained(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-010-a.md", {"status": "open", "blocks": ["FEAT-030"]})
    write_issue(tmp_path, "features/P2-BUG-010-b.md", {"status": "done", "blocks": ["FEAT-031"]})
    write_issue(tmp_path, "features/P3-FEAT-030-t.md", {})
    write_issue(tmp_path, "features/P3-FEAT-031-t.md", {})
    write_issue(tmp_path, "features/P3-FEAT-032-t.md", {})
    state = collect(tmp_path)
    for target in ("FEAT-030", "FEAT-031"):
        pending = state.graph.unresolved_for(target)
        assert [(p.kind, p.prerequisite_id, p.reason) for p in pending] == [
            ("blocks", "BUG-010", "ambiguous_issue_id")
        ]
    assert state.graph.prerequisites_satisfied("FEAT-032")


# ----------------------------------------------------------------- shared anchored number


@pytest.mark.parametrize(
    ("bug_fm", "feat_fm"),
    [
        ({}, {}),
        ({"id": "FEAT-050"}, {"id": "BUG-050"}),  # stale/conflicting
        ({"id": "BUG-050"}, {"id": "FEAT-050"}),  # apparently disambiguating
        ({"id": "050", "type": "BUG"}, {"id": "050", "type": "FEAT"}),
    ],
)
def test_shared_number_with_distinct_full_ids_is_ambiguous_for_both(
    tmp_path: Path, bug_fm: dict[str, Any], feat_fm: dict[str, Any]
) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-050-a.md", bug_fm)
    write_issue(tmp_path, "features/P3-FEAT-050-b.md", feat_fm)
    state = collect(tmp_path)
    amb = ambiguous_targets(state)
    assert set(amb) == {"BUG-050", "FEAT-050"}
    for issue_id in amb:
        assert amb[issue_id].numbers == ("050",)
        assert "shared_number" in amb[issue_id].reasons
        assert amb[issue_id].paths == (
            ".issues/bugs/P3-BUG-050-a.md",
            ".issues/features/P3-FEAT-050-b.md",
        )
        assert supported_source(state, issue_id) is None


def test_unique_number_with_stale_frontmatter_remains_usable_with_exact_digits(
    tmp_path: Path,
) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-001-a.md", {"id": "BUG-999", "type": "FEAT"})
    write_issue(tmp_path, "features/P3-FEAT-002-b.md", {"id": "BUG-001"})  # claims another's id
    write_issue(tmp_path, "bugs/P3-BUG-1-short.md", {})  # "1" is a different spelling of 001
    state = collect(tmp_path)
    assert ambiguous_targets(state) == {}
    rec = supported_source(state, "BUG-001")
    assert rec is not None and rec.issue_id == "BUG-001"  # digits preserved, not BUG-1
    assert supported_source(state, "BUG-1") is not None
    assert supported_source(state, "BUG-1") is not rec
    for issue_id in ("BUG-001", "FEAT-002", "BUG-1"):
        assert_resolver_parity(state, issue_id)


def test_numbers_are_grouped_by_exact_digit_string(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-007-a.md", {})
    write_issue(tmp_path, "features/P3-FEAT-007-b.md", {})
    write_issue(tmp_path, "enhancements/P3-ENH-0007-c.md", {})
    state = collect(tmp_path)
    assert set(ambiguous_targets(state)) == {"BUG-007", "FEAT-007"}
    assert supported_source(state, "ENH-0007") is not None
    assert state.identity.by_number["007"] == (
        ".issues/bugs/P3-BUG-007-a.md",
        ".issues/features/P3-FEAT-007-b.md",
    )


def test_ambiguous_issue_is_both_duplicate_and_shared(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-060-a.md", {})
    write_issue(tmp_path, "features/P2-BUG-060-b.md", {})
    write_issue(tmp_path, "features/P3-FEAT-060-c.md", {})
    amb = ambiguous_targets(collect(tmp_path))
    assert set(amb) == {"BUG-060", "FEAT-060"}
    assert amb["BUG-060"].reasons == ("duplicate_full_id", "shared_number")
    assert amb["FEAT-060"].reasons == ("shared_number",)
    assert len(amb["BUG-060"].paths) == 3 == len(amb["FEAT-060"].paths)


# -------------------------------------------------------- unnormalized / unsupported names


def test_unnormalized_name_beside_canonical_source_is_unsupported_not_ambiguous(
    tmp_path: Path,
) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-001-old.md", {"status": "open"})
    write_issue(tmp_path, "bugs/P3-BUG-001-new.md", {"status": "open"})
    state = collect(tmp_path)

    old = record(state, "bugs/P3-001-old.md")
    assert (old.issue_id, old.inferred_id, old.filename_issue) == (
        None,
        "BUG-001",
        "inferred_unanchored",
    )
    unsupported = unsupported_sources(state)
    assert unsupported[old.rel_path].reason == "inferred_id_collision"
    diags = _codes(state, "unsupported_issue_filename")
    assert [d.paths for d in diags] == [(old.rel_path,)]
    assert old.rel_path not in state.identity.node_ids  # the canonical source owns BUG-001
    # the canonical source stays unambiguous, supported, and the real resolver agrees
    assert ambiguous_targets(state) == {}
    assert supported_source(state, "BUG-001") is not None
    resolved = assert_resolver_parity(state, "BUG-001")
    assert resolved.name == "P3-BUG-001-new.md"


def test_unnormalized_name_keeps_numbered_graph_evidence_but_cannot_act(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-002-solo.md", {"status": "done"})
    write_issue(tmp_path, "bugs/P3-003-solo.md", {"status": "open"})
    write_issue(tmp_path, "features/P3-FEAT-010-a.md", {"blocked_by": ["BUG-002"]})
    write_issue(tmp_path, "features/P3-FEAT-011-b.md", {"blocked_by": ["BUG-003"]})
    state = collect(tmp_path)
    for rel in ("bugs/P3-002-solo.md", "bugs/P3-003-solo.md"):
        assert unsupported_sources(state)[f".issues/{rel}"].reason == "inferred_unanchored"
    assert supported_source(state, "BUG-002") is None
    assert state.graph.node_status["BUG-002"] == "done"
    assert state.graph.prerequisites_satisfied("FEAT-010")  # done legacy-named prerequisite
    assert not state.graph.prerequisites_satisfied("FEAT-011")


def test_anchored_name_whose_type_disagrees_with_parser_is_unsupported(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "features/P2-FEAT-100-fix-BUG-5-thing.md", {})
    state = collect(tmp_path)
    rec = record(state, "features/P2-FEAT-100-fix-BUG-5-thing.md")
    assert rec.issue_id == "FEAT-100" and rec.filename_issue == "parser_id_disagrees"
    assert unsupported_sources(state)[rec.rel_path].reason == "parser_id_disagrees"
    assert supported_source(state, "FEAT-100") is None
    assert "FEAT-100" in state.graph.node_status  # still graph evidence


def test_canonical_filenames_in_legacy_directories_remain_supported(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "completed/P3-BUG-300-x.md", {"status": "done"})
    write_issue(tmp_path, "deferred/P3-BUG-301-x.md", {"status": "deferred"})
    write_issue(tmp_path, "features/P3-FEAT-010-a.md", {"blocked_by": ["BUG-300", "BUG-301"]})
    state = collect(tmp_path)
    assert supported_source(state, "BUG-300") is not None
    assert supported_source(state, "BUG-301") is not None
    assert state.identity.unsupported == {}
    assert_resolver_parity(state, "BUG-300")
    assert_resolver_parity(state, "BUG-301")
    pending = state.graph.unresolved_for("FEAT-010")
    assert [(p.prerequisite_id, p.reason) for p in pending] == [("BUG-301", "not_terminal")]


def test_identity_diagnostics_are_sorted_and_stable(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/notes.md", {})
    write_issue(tmp_path, "bugs/P3-BUG-010-a.md", {})
    write_issue(tmp_path, "features/P3-BUG-010-b.md", {})
    write_issue(tmp_path, "bugs/P3-004-solo.md", {})
    state = collect(tmp_path)
    diags = identity_diagnostics(state)
    assert list(diags) == sorted(diags, key=lambda d: d.sort_key())
    assert {d.code for d in diags} == {"ambiguous_issue_id", "unsupported_issue_filename"}


# ------------------------------------------------------------- prerequisite resolution


def test_edges_resolve_only_against_known_unique_terminal_sources(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-001-done.md", {"status": "done"})
    write_issue(tmp_path, "bugs/P3-BUG-002-cancelled.md", {"status": "cancelled"})
    write_issue(tmp_path, "bugs/P3-BUG-003-legacy.md", {"completed_at": "2026-01-01"})
    write_issue(tmp_path, "bugs/P3-BUG-004-deferred.md", {"status": "deferred"})
    write_issue(tmp_path, "bugs/P3-BUG-005-reopened.md", {"status": "open", "completed_at": "x"})
    write_issue(tmp_path, "bugs/P3-BUG-006-invalid.md", {"status": "weird", "completed_at": "x"})
    write_issue(tmp_path, "bugs/P3-BUG-007-progress.md", {"status": "in_progress"})
    write_issue(
        tmp_path,
        "features/P3-FEAT-010-a.md",
        {
            "blocked_by": ["BUG-001", "BUG-002", "BUG-003"],
            "depends_on": ["BUG-004", "BUG-005", "BUG-006", "BUG-007", "BUG-999", "bug-001"],
        },
    )
    state = collect(tmp_path)
    got = {p.prerequisite_id: (p.kind, p.reason) for p in state.graph.unresolved_for("FEAT-010")}
    assert got == {
        "BUG-004": ("depends_on", "not_terminal"),
        "BUG-005": ("depends_on", "not_terminal"),
        "BUG-006": ("depends_on", "invalid_status"),
        "BUG-007": ("depends_on", "not_terminal"),
        "BUG-999": ("depends_on", "unknown_issue"),
        "bug-001": ("depends_on", "unknown_issue"),
    }
    assert state.graph.node_status["BUG-003"] == "done"


def test_one_sided_blocks_resolves_with_the_declaring_source(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-001-a.md", {"status": "open", "blocks": ["FEAT-010"]})
    write_issue(tmp_path, "bugs/P3-BUG-002-b.md", {"status": "done", "blocks": ["FEAT-011"]})
    write_issue(tmp_path, "features/P3-FEAT-010-a.md", {})
    write_issue(tmp_path, "features/P3-FEAT-011-b.md", {})
    state = collect(tmp_path)
    assert [(p.kind, p.prerequisite_id) for p in state.graph.unresolved_for("FEAT-010")] == [
        ("blocks", "BUG-001")
    ]
    assert state.graph.prerequisites_satisfied("FEAT-011")
    assert state.graph.blocked_by["FEAT-010"] == ("BUG-001",)
    assert state.graph.blocks["BUG-001"] == ("FEAT-010",)


def test_deferred_nodes_participate_in_the_graph(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-001-a.md", {"status": "deferred", "blocks": ["FEAT-010"]})
    write_issue(tmp_path, "features/P3-FEAT-010-a.md", {})
    state = collect(tmp_path)
    assert state.graph.node_status["BUG-001"] == "deferred"
    assert not state.graph.prerequisites_satisfied("FEAT-010")


def test_dangling_blocks_target_is_recorded_not_a_node(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-001-a.md", {"blocks": ["FEAT-777"]})
    state = collect(tmp_path)
    assert state.graph.dangling_blocks == {"BUG-001": ("FEAT-777",)}
    assert "FEAT-777" not in state.graph.node_status


def test_cycles_yield_diagnostics_not_roots(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-001-a.md", {"blocked_by": ["BUG-002"]})
    write_issue(tmp_path, "bugs/P3-BUG-002-b.md", {"blocked_by": ["BUG-003"]})
    write_issue(tmp_path, "bugs/P3-BUG-003-c.md", {"depends_on": ["BUG-001"]})
    write_issue(tmp_path, "bugs/P3-BUG-004-self.md", {"blocked_by": ["BUG-004"]})
    write_issue(tmp_path, "bugs/P3-BUG-005-ok.md", {"blocked_by": ["BUG-006"]})
    write_issue(tmp_path, "bugs/P3-BUG-006-ok.md", {})
    # a cycle through only terminal sources is not an active cycle
    write_issue(tmp_path, "bugs/P3-BUG-007-d.md", {"status": "done", "blocked_by": ["BUG-008"]})
    write_issue(tmp_path, "bugs/P3-BUG-008-d.md", {"status": "done", "blocked_by": ["BUG-007"]})
    state = collect(tmp_path)
    assert state.graph.cycles == (("BUG-001", "BUG-002", "BUG-003"), ("BUG-004",))
    cycle_diags = _codes(state, "dependency_cycle")
    assert [d.subject for d in cycle_diags] == ["BUG-001", "BUG-004"]
    assert cycle_diags[0].paths == (
        ".issues/bugs/P3-BUG-001-a.md",
        ".issues/bugs/P3-BUG-002-b.md",
        ".issues/bugs/P3-BUG-003-c.md",
    )
    for issue_id in ("BUG-001", "BUG-002", "BUG-003", "BUG-004"):
        assert not state.graph.prerequisites_satisfied(issue_id)

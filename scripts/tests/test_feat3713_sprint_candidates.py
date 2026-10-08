"""``assess_run_sprints``: eligibility, executor parity, identity and scoring (FEAT-3713 step 3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.issue_parser import resolve_issue_path
from little_loops.next_arena.actions import FINGERPRINT_SCOPE_V1, action_fingerprint, spec_to_dict
from little_loops.next_arena.candidates import assess_candidates, assessments_for_target
from tests.next_arena_support import make_project, write_issue
from tests.sprint_support import (
    SETTINGS,
    assess_sprints,
    bug,
    build,
    feat,
    plain,
    ready,
    run_for,
    sprint_of,
    sprint_state,
    write_sprint,
)


def raw(fm: str = "", body: str = "", *, scores: bool = True) -> str:
    """An issue with hand-written frontmatter lines (ready scores unless *scores* is False)."""
    head = "confidence_score: 90\noutcome_confidence: 80\n" if scores else ""
    return f"---\n{head}{fm}\n---\n\n# Title\n\n## Summary\n\nText.\n\n{body}\n"


def codes(item: Any) -> set[str]:
    return set(item.exclusion_reasons)


# ------------------------------------------------------------------------- eligibility


def test_ready_sprint_is_offered_with_pinned_identity_and_member_snapshot(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {feat(1): ready(), bug(2): ready(), feat(3, prio="P1"): ready({"status": "done"})},
        {"alpha": ["FEAT-001", "BUG-002", "FEAT-003"]},
    )
    item = run_for(root, "alpha")
    assert item.eligible and item.fully_resolved
    assert item.display_command == "ll-sprint run -- alpha"
    assert item.action_key == "run-sprint"
    assert item.target == "alpha" and item.target_key == "sprint:alpha"
    spec = item.action_spec
    assert spec.variant == "sprint" and spec.target == "alpha"
    assert spec.definition_source == ".sprints/alpha.yaml"
    assert spec.definition_digest.startswith("sha256:") and len(spec.definition_digest) == 71
    assert spec.fingerprint_scope == FINGERPRINT_SCOPE_V1
    assert spec.working_directory == str(root.resolve())
    # every distinct declared member, in file order, terminal ones included
    assert spec_to_dict(spec)["members"] == [
        {"issue_id": "FEAT-001", "status": "open"},
        {"issue_id": "BUG-002", "status": "open"},
        {"issue_id": "FEAT-003", "status": "done"},
    ]
    assert action_fingerprint(spec) == item.action_fingerprint
    ev = item.evidence["sprint"]
    assert ev["remaining"] == ["FEAT-001", "BUG-002"] and ev["terminal_removed"] == ["FEAT-003"]
    assert ev["waves"] == [["BUG-002", "FEAT-001"]] or ev["waves"] == [["FEAT-001", "BUG-002"]]
    assert ev["digest_label"] == "sprint definition bytes"
    assert "loads the definition current when it runs" in ev["command_note"]
    assert "learning-test preflight" in ev["unmodeled_preflights"]
    assert "cannot prevent concurrent duplicate sprint work" in ev["concurrency"]
    assert ev["history"]["labels"] == ["name-based-definition-unknown"]


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        ("-dash", "ll-sprint run -- -dash"),
        ("--only", "ll-sprint run -- --only"),
        ("my sprint", "ll-sprint run -- 'my sprint'"),
        ("it's", "ll-sprint run -- 'it'\"'\"'s'"),
        ("q$uote", "ll-sprint run -- 'q$uote'"),
    ],
)
def test_option_like_and_quoted_names_recover_the_runtime_operand(
    tmp_path: Path, name: str, shown: str
) -> None:
    import shlex

    root = build(tmp_path / "p", {feat(1): ready()}, {})
    write_sprint(root, name, ["FEAT-001"])
    item = run_for(root, name)
    assert item.eligible and item.display_command == shown
    assert shlex.split(item.display_command)[-1] == name  # the literal operand round-trips
    assert shlex.split(item.display_command)[:3] == ["ll-sprint", "run", "--"]


def test_member_status_change_alters_members_not_the_fingerprint(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {feat(1): ready(), bug(2): ready()},
        {"alpha": ["FEAT-001", "BUG-002"]},
    )
    before = run_for(root, "alpha")
    write_issue(root, bug(2), text=ready({"status": "done"}))
    after = run_for(root, "alpha")
    assert before.action_fingerprint == after.action_fingerprint
    assert [m.status for m in before.action_spec.members] == ["open", "open"]
    assert [m.status for m in after.action_spec.members] == ["open", "done"]


def test_editing_the_definition_changes_the_fingerprint(tmp_path: Path) -> None:
    root = build(tmp_path / "p", {feat(1): ready()}, {"alpha": ["FEAT-001"]})
    before = run_for(root, "alpha")
    path = root / ".sprints" / "alpha.yaml"
    path.write_text(path.read_text() + "\n# cosmetic\n")
    after = run_for(root, "alpha")
    assert before.action_fingerprint != after.action_fingerprint


def test_every_remaining_member_resolves_to_its_assessed_source(tmp_path: Path) -> None:
    from tests.next_arena_support import assert_resolver_parity

    root = build(
        tmp_path / "p", {feat(1): ready(), bug(2): ready()}, {"alpha": ["FEAT-001", "BUG-002"]}
    )
    state = sprint_state(root)
    item = sprint_of(state, "alpha")
    assert item.eligible
    for member in item.action_spec.members:
        assert_resolver_parity(state, member.issue_id)


def test_no_remaining_work_yields_no_candidate_but_stays_explainable(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {feat(1): ready({"status": "done"}), bug(2): ready({"status": "cancelled"})},
        {"alpha": ["FEAT-001", "BUG-002"]},
    )
    item = run_for(root, "alpha")
    assert not item.eligible and "no_remaining_work" in codes(item)
    named, _ = assessments_for_target(
        assess_candidates(sprint_state(root), settings=SETTINGS), "sprint:alpha", "run-sprint"
    )
    assert named is not None


def test_empty_member_list_has_no_candidate(tmp_path: Path) -> None:
    root = build(tmp_path / "p", {feat(1): ready()}, {"alpha": []})
    assert "no_remaining_work" in codes(run_for(root, "alpha"))


def test_uncollected_sprint_domain_yields_no_assessments(tmp_path: Path) -> None:
    from tests.next_arena_support import collect

    root = build(tmp_path / "p", {feat(1): ready()}, {"alpha": ["FEAT-001"]})
    state = collect(root)  # include_sprints=False: sprint_definitions is None
    assert state.sprint_definitions is None and assess_sprints(state) == []


def test_repeated_members_are_normalized_once(tmp_path: Path) -> None:
    root = build(tmp_path / "p", {feat(1): ready(), bug(2): ready()}, {})
    write_sprint(root, "alpha", ["BUG-002", "FEAT-001", "BUG-002"])
    item = run_for(root, "alpha")
    assert item.eligible
    assert [m.issue_id for m in item.action_spec.members] == ["BUG-002", "FEAT-001"]
    assert item.evidence["sprint"]["normalized_repeats"] == ["BUG-002"]
    assert item.evidence["sprint"]["ready_now"] and item.axes["ready_share"].raw["remaining"] == 2


# ---------------------------------------------------------------- definition exclusions


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"text": "issues: [FEAT-001]\n"}, "name_mismatch"),
        ({"declared_name": "other", "issues": ["FEAT-001"]}, "name_mismatch"),
        ({"text": "name: alpha\nissues: nope\n"}, "invalid_issues"),
        ({"text": "name: alpha\nissues: [FEAT-001]\noptions: {timeout: 0}\n"}, "invalid_options"),
        ({"text": "{ unclosed"}, "invalid_yaml"),
        ({"suffix": ".yml", "issues": ["FEAT-001"]}, "unsupported_extension"),
    ],
)
def test_invalid_definitions_are_excluded_but_explainable(
    tmp_path: Path, kwargs: dict[str, Any], code: str
) -> None:
    root = build(tmp_path / "p", {feat(1): ready()}, {})
    write_sprint(root, "alpha", kwargs.pop("issues", None), **kwargs)
    item = run_for(root, "alpha")
    assert not item.eligible and code in codes(item)
    assert item.gates["definition"].status == "fail"
    assert item.evidence["sprint"]["definition_digest"].startswith("sha256:")
    assert item.action_spec is None and item.display_command is None


def test_reserved_epic_name_is_rejected_before_any_yaml_is_trusted(tmp_path: Path) -> None:
    root = build(tmp_path / "p", {feat(1): ready()}, {})
    write_sprint(root, "EPIC-007", ["FEAT-001"])
    item = run_for(root, "EPIC-007")
    assert not item.eligible and "reserved_epic_name" in codes(item)


def test_malformed_sibling_does_not_disturb_valid_sprints(tmp_path: Path) -> None:
    root = build(tmp_path / "p", {feat(1): ready()}, {"good": ["FEAT-001"]})
    write_sprint(root, "bad", text="name: bad\nissues: 3\n")
    state = sprint_state(root)
    assert sprint_of(state, "good").eligible and not sprint_of(state, "bad").eligible


def test_option_values_do_not_affect_eligibility_and_unknown_keys_are_only_diagnosed(
    tmp_path: Path,
) -> None:
    root = build(tmp_path / "p", {feat(1): ready()}, {})
    write_sprint(root, "alpha", ["FEAT-001"], extra={"options": {"max_workers": 4, "colour": 1}})
    item = run_for(root, "alpha")
    assert item.eligible
    assert "sprint_option_ignored" in {d.code for d in item.diagnostics}
    assert item.evidence["sprint"]["options"]["max_workers"] == 4


def test_sprint_directory_outside_the_project_keeps_an_identity_exclusion(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    root = make_project(tmp_path / "p", config={"sprints": {"sprints_dir": str(outside)}})
    write_issue(root, feat(1), text=ready())
    write_sprint(root, "alpha", ["FEAT-001"], directory=str(outside))
    item = run_for(root, "alpha")
    assert not item.eligible and "definition_source_outside_project" in codes(item)


# ------------------------------------------------------------------ member identity/status


def test_missing_epic_and_nonrunnable_status_members_veto_the_whole_sprint(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready(),
            feat(2): ready({"status": "deferred"}),
            feat(3): ready({"status": "in_progress"}),
            "epics/P2-EPIC-004-container.md": ready(),
        },
        {
            "gone": ["FEAT-001", "BUG-099"],
            "epic": ["FEAT-001", "EPIC-004"],
            "deferred": ["FEAT-001", "FEAT-002"],
            "wip": ["FEAT-001", "FEAT-003"],
        },
    )
    state = sprint_state(root)
    assert "missing_issue" in codes(sprint_of(state, "gone"))
    assert "epic_member" in codes(sprint_of(state, "epic"))
    for name in ("deferred", "wip"):
        item = sprint_of(state, name)
        assert not item.eligible and "status_not_actionable" in codes(item)
        assert item.display_command is None  # never a subset-run command


def test_status_blocked_member_is_vetoed_even_with_only_internal_edges(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready(),
            feat(2): ready({"blocked_by": ["FEAT-001"], "status": "blocked"}),
            feat(3): ready({"blocked_by": ["FEAT-001"]}),
        },
        {"blocked": ["FEAT-001", "FEAT-002"], "later": ["FEAT-001", "FEAT-003"]},
    )
    state = sprint_state(root)
    assert "status_blocked" in codes(sprint_of(state, "blocked"))
    later = sprint_of(state, "later")
    assert later.eligible and later.evidence["sprint"]["waves"] == [["FEAT-001"], ["FEAT-003"]]


def test_every_remaining_member_must_pass_not_only_the_first_wave(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready(),
            feat(2): plain({"blocked_by": ["FEAT-001"]}),  # later wave, no scores
            feat(3): ready({"blocked_by": ["FEAT-001"], "confidence_score": 10}),
            feat(4): ready({"blocked_by": ["FEAT-001"], "decision_needed": "true"}),
            feat(5): ready({"blocked_by": ["FEAT-001"], "outcome_confidence": 5}),
        },
        {
            "missing": ["FEAT-001", "FEAT-002"],
            "low": ["FEAT-001", "FEAT-003"],
            "decision": ["FEAT-001", "FEAT-004"],
            "outcome": ["FEAT-001", "FEAT-005"],
        },
    )
    state = sprint_state(root)
    got = {n: codes(sprint_of(state, n)) for n in ("missing", "low", "decision", "outcome")}
    assert "member_gates_failed" in got["missing"]
    assert any("score_absent" in c for c in got["missing"])
    assert "readiness_below_threshold" in got["low"]
    assert "decision_unresolved" in got["decision"]
    assert "outcome_below_threshold" in got["outcome"]
    detail = sprint_of(state, "missing").gates["member_gates"].reason
    assert "FEAT-002" in detail and "not only the first wave" in detail


def test_waived_outcome_passes_the_member_gate(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {feat(1): ready({"outcome_confidence": 5, "outcome_gate_waived": "true"})},
        {"alpha": ["FEAT-001"]},
    )
    assert run_for(root, "alpha").eligible


# ---------------------------------------------------------------- prerequisites and waves


def test_internal_edges_sequence_waves_and_set_the_ready_share(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready(),
            feat(2): ready({"blocked_by": ["FEAT-001"]}),
            feat(3): ready({"depends_on": ["FEAT-002"]}),
            feat(4): ready(),
        },
        {"alpha": ["FEAT-001", "FEAT-002", "FEAT-003", "FEAT-004"]},
    )
    item = run_for(root, "alpha")
    assert item.eligible
    waves = item.evidence["sprint"]["waves"]
    assert [sorted(w) for w in waves] == [["FEAT-001", "FEAT-004"], ["FEAT-002"], ["FEAT-003"]]
    ready_axis = item.axes["ready_share"]
    assert ready_axis.raw == {"ready": 2, "remaining": 4, "share": 0.5}
    assert ready_axis.score == pytest.approx(0.4 + 0.6 * 0.5)


def test_one_sided_blocks_declaration_orders_internal_members(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {feat(1): ready({"blocks": ["FEAT-002"]}), feat(2): ready()},
        {"alpha": ["FEAT-001", "FEAT-002"]},
    )
    assert run_for(root, "alpha").evidence["sprint"]["waves"] == [["FEAT-001"], ["FEAT-002"]]


@pytest.mark.parametrize("which", ["first", "later"])
def test_outside_nonterminal_prerequisite_vetoes_the_whole_sprint(
    tmp_path: Path, which: str
) -> None:
    outside = {"blocked_by": ["FEAT-009"]}
    issues = {
        feat(1): ready(outside if which == "first" else None),
        feat(2): ready({"blocked_by": ["FEAT-001"], **(outside if which == "later" else {})}),
        feat(9): ready(),
    }
    root = build(tmp_path / "p", issues, {"alpha": ["FEAT-001", "FEAT-002"]})
    item = run_for(root, "alpha")
    assert not item.eligible and "outside_prerequisite_unresolved" in codes(item)
    assert "FEAT-009" in item.gates["prerequisites"].reason
    assert item.gates["prerequisites"].status == "fail"


@pytest.mark.parametrize(
    ("extra", "blocked"),
    [
        ({"blocked_by": ["FEAT-777"]}, True),  # unknown
        ({"depends_on": ["FEAT-009"]}, True),  # soft prerequisite is still a prerequisite
        ({"blocked_by": ["FEAT-008"]}, False),  # done outside
        ({"blocked_by": ["FEAT-007"]}, False),  # cancelled outside
    ],
)
def test_outside_prerequisites_unknown_nonterminal_or_terminal(
    tmp_path: Path, extra: dict[str, Any], blocked: bool
) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready(extra),
            feat(9): ready(),
            feat(8): ready({"status": "done"}),
            feat(7): ready({"status": "cancelled"}),
        },
        {"alpha": ["FEAT-001"]},
    )
    assert run_for(root, "alpha").eligible is (not blocked)


def test_reopened_outside_prerequisite_with_stale_marker_is_unresolved(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready({"blocked_by": ["FEAT-005"]}),
            feat(5): ready({"status": "open", "completed_at": "2026-01-01T00:00:00Z"}),
        },
        {"alpha": ["FEAT-001"]},
    )
    assert "outside_prerequisite_unresolved" in codes(run_for(root, "alpha"))


def test_reopened_member_with_stale_completion_marker_stays_remaining(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready({"status": "open", "completed_at": "2026-01-01T00:00:00Z"}),
            feat(2): ready(),
        },
        {"alpha": ["FEAT-001", "FEAT-002"]},
    )
    item = run_for(root, "alpha")
    assert item.eligible and item.evidence["sprint"]["remaining"] == ["FEAT-001", "FEAT-002"]
    assert [m.status for m in item.action_spec.members] == ["open", "open"]


def test_member_cycle_vetoes_but_an_unrelated_cycle_does_not(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready({"blocked_by": ["FEAT-002"]}),
            feat(2): ready({"blocked_by": ["FEAT-001"]}),
            feat(3): ready(),
            feat(8): ready({"blocked_by": ["FEAT-9"]}),
            "features/P2-FEAT-009-y.md": ready({"blocked_by": ["FEAT-008"]}),
        },
        {"cyclic": ["FEAT-001", "FEAT-002"], "fine": ["FEAT-003"]},
    )
    state = sprint_state(root)
    assert "dependency_cycle" in codes(sprint_of(state, "cyclic"))
    assert sprint_of(state, "fine").eligible
    assert any(d.code == "dependency_cycle" for d in state.diagnostics)  # reported separately


def test_outside_prerequisite_in_another_sprint_is_still_outside(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {feat(1): ready(), feat(2): ready({"blocked_by": ["FEAT-001"]})},
        {"first": ["FEAT-001"], "second": ["FEAT-002"]},
    )
    state = sprint_state(root)
    assert sprint_of(state, "first").eligible
    assert "outside_prerequisite_unresolved" in codes(sprint_of(state, "second"))


# --------------------------------------------------------------------- identity collisions


def test_duplicate_full_id_vetoes_independent_of_file_order(tmp_path: Path) -> None:
    for order in (("a", "b"), ("b", "a")):
        root = tmp_path / "-".join(order)
        files = {
            "features/P2-FEAT-001-a.md": ready(),
            "features/P3-FEAT-001-b.md": ready(),
            feat(2): ready(),
        }
        build(root, {k: files[k] for k in sorted(files, reverse=order[0] == "b")}, {})
        write_sprint(root, "dup", ["FEAT-001"])
        write_sprint(root, "clean", ["FEAT-002"])
        state = sprint_state(root)
        assert "ambiguous_issue_id" in codes(sprint_of(state, "dup"))
        assert sprint_of(state, "clean").eligible  # unrelated sprints remain eligible


def test_active_and_terminal_collision_cannot_be_removed_as_completed(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            "features/P2-FEAT-001-active.md": ready(),
            "features/P2-FEAT-001-old.md": ready({"status": "done"}),
            feat(2): ready(),
        },
        {"alpha": ["FEAT-001", "FEAT-002"]},
    )
    assert "ambiguous_issue_id" in codes(run_for(root, "alpha"))


def test_numeric_collision_across_types_vetoes_even_for_a_terminal_member(tmp_path: Path) -> None:
    # FEAT-001 and BUG-001 are individually unique full IDs that share a filename number;
    # the runtime's frontmatter-first numeric selection could dispatch the wrong file.
    files = {
        "features/P2-FEAT-001-x.md": ready({"status": "done"}),
        "bugs/P2-BUG-001-y.md": ready(),
        feat(2): ready(),
    }
    root = build(tmp_path / "p", files, {"alpha": ["FEAT-001", "FEAT-002"]})
    item = run_for(root, "alpha")
    assert "ambiguous_issue_id" in codes(item)
    gate = item.gates["members"].reason
    assert "shared number 001" in gate
    assert "features/P2-FEAT-001-x.md" in gate.replace(".issues/", "") or "FEAT-001-x" in gate
    assert "BUG-001-y" in gate  # every source path is retained in explain


def test_frontmatter_biased_resolver_selection_is_why_numeric_collisions_veto(
    tmp_path: Path,
) -> None:
    # The real resolver sends FEAT-001 to the BUG-001 file when its frontmatter claims that ID:
    # a "terminal" FEAT-001 could be dispatched as an active BUG. Both IDs veto the offer.
    root = build(
        tmp_path / "p",
        {
            "features/P2-FEAT-001-x.md": ready({"status": "done"}),
            "bugs/P2-BUG-001-y.md": ready({"id": "FEAT-001"}),
            feat(2): ready(),
        },
        {"alpha": ["FEAT-001", "FEAT-002"], "beta": ["BUG-001", "FEAT-002"]},
    )
    state = sprint_state(root)
    resolved = resolve_issue_path(state.config, "FEAT-001")
    assert resolved is not None and resolved.name == "P2-BUG-001-y.md"
    for name in ("alpha", "beta"):
        assert "ambiguous_issue_id" in codes(sprint_of(state, name))


def test_unnormalized_inferred_member_vetoes_before_terminal_filtering(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            "features/notes-FEAT-007-draft.md": ready({"status": "done"}),
            "bugs/P2-BUG-007-real.md": ready(),
            feat(2): ready(),
        },
        {"alpha": ["FEAT-007", "FEAT-002"]},
    )
    item = run_for(root, "alpha")
    assert "unsupported_issue_filename" in codes(item)
    assert not item.eligible


def test_legacy_directory_members_remain_supported(tmp_path: Path) -> None:
    root = build(tmp_path / "p", {feat(2): ready()}, {})
    write_issue(root, "completed/P2-FEAT-001-old.md", text=ready({"status": "done"}))
    write_sprint(root, "alpha", ["FEAT-001", "FEAT-002"])
    item = run_for(root, "alpha")
    assert item.eligible and [m.status for m in item.action_spec.members] == ["done", "open"]


def test_resolver_parity_for_unique_numbers(tmp_path: Path) -> None:
    root = build(tmp_path / "p", {feat(1): ready(), bug(2): ready()}, {"alpha": ["FEAT-001"]})
    state = sprint_state(root)
    resolved = resolve_issue_path(state.config, "FEAT-001")
    assert resolved is not None and resolved.name == "P2-FEAT-001-x.md"


# ------------------------------------------------------------- executor membership parity


def test_legacy_completed_at_member_is_removed_by_the_arena_but_kept_by_the_command(
    tmp_path: Path,
) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready(),
            feat(2): raw("completed_at: 2026-01-01T00:00:00Z"),  # absent status + marker
        },
        {"alpha": ["FEAT-001", "FEAT-002"]},
    )
    item = run_for(root, "alpha")
    assert not item.eligible and "executor_membership_mismatch" in codes(item)
    mismatch = item.evidence["executor_membership_mismatches"][0]
    assert mismatch["issue_id"] == "FEAT-002"
    assert mismatch["raw_status"] == "<absent>"
    assert mismatch["lifecycle_status"] == "done"
    assert mismatch["lifecycle_provenance"] == "legacy_completed_at"
    assert "status: done" in mismatch["remedy"]


@pytest.mark.parametrize("padded", ["' done '", "' cancelled '", '" done"'])
def test_padded_terminal_status_is_an_executor_membership_mismatch(
    tmp_path: Path, padded: str
) -> None:
    root = build(
        tmp_path / "p",
        {feat(1): ready(), feat(2): raw(f"status: {padded}")},
        {"alpha": ["FEAT-001", "FEAT-002"]},
    )
    item = run_for(root, "alpha")
    assert "executor_membership_mismatch" in codes(item)
    assert (
        item.evidence["executor_membership_mismatches"][0]["lifecycle_provenance"] == "frontmatter"
    )


def test_exact_terminal_status_restores_eligibility(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {feat(1): ready(), feat(2): ready({"status": "done"})},
        {"alpha": ["FEAT-001", "FEAT-002"]},
    )
    assert run_for(root, "alpha").eligible


# ------------------------------------------------------ executor dependency-shape parity


def shape(tmp_path: Path, a_fm: str, b_fm: str = "", a_body: str = "", **extra: str) -> Any:
    files = {feat(1): raw(a_fm, a_body), feat(2): raw(b_fm), **extra}
    root = build(tmp_path / "p", files, {"alpha": ["FEAT-001", "FEAT-002"]})
    return run_for(root, "alpha")


@pytest.mark.parametrize(
    "a_fm",
    [
        "blocked_by: ['FEAT-002 ']",
        "blocked_by: [' FEAT-002']",
        "depends_on: [' FEAT-002 ']",
        "blocks: ['FEAT-002 ']",
    ],
)
def test_padded_list_entries_naming_a_member_veto(tmp_path: Path, a_fm: str) -> None:
    item = shape(tmp_path, a_fm)
    assert not item.eligible and "executor_dependency_mismatch" in codes(item)
    finding = item.evidence["executor_dependency_findings"][0]
    assert finding["problem"] == "padded_entry" and finding["target"] == "FEAT-002"
    assert finding["source"] == "FEAT-001" and finding["kind"] in {
        "blocked_by",
        "depends_on",
        "blocks",
    }


def test_padded_entry_naming_an_outside_issue_does_not_veto(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {feat(1): raw("depends_on: [' FEAT-008 ']"), feat(8): raw("status: done")},
        {"alpha": ["FEAT-001"]},
    )
    assert run_for(root, "alpha").eligible


@pytest.mark.parametrize(
    "a_fm",
    [
        "blocked_by: ['']",
        "blocked_by: ['  ']",
        "blocked_by: ' , '",
        "blocked_by: ''\nblocks: [' ']",
    ],
)
def test_blank_entries_that_hide_a_body_edge_veto(tmp_path: Path, a_fm: str) -> None:
    body = "## Blocked By\n\n- FEAT-002\n"
    item = shape(tmp_path, a_fm, a_body=body)
    if a_fm == "blocked_by: ''\nblocks: [' ']":
        # an empty string is falsy in both paths: the body fallback stays valid
        assert "executor_dependency_mismatch" not in codes(item)
        return
    assert "executor_dependency_mismatch" in codes(item)
    assert item.evidence["executor_dependency_findings"][0]["problem"] == (
        "blank_entries_hide_body_edge"
    )


def test_blank_entries_without_a_body_edge_do_not_veto(tmp_path: Path) -> None:
    assert shape(tmp_path, "blocked_by: ['']").eligible


@pytest.mark.parametrize(
    "a_fm",
    ["blocked_by: {FEAT-002: reason}", "depends_on: {FEAT-002: x}", "blocks: {FEAT-002: y}"],
)
def test_nonempty_mapping_valued_relationships_veto(tmp_path: Path, a_fm: str) -> None:
    item = shape(tmp_path, a_fm)
    assert "executor_dependency_mismatch" in codes(item)
    finding = item.evidence["executor_dependency_findings"][0]
    assert finding["problem"] == "mapping_value" and "FEAT-002" in finding["raw"]


def test_two_member_mapping_key_cycle_that_the_runtime_rejects_vetoes(tmp_path: Path) -> None:
    item = shape(tmp_path, "blocked_by: {FEAT-002: x}", "blocked_by: {FEAT-001: y}")
    assert not item.eligible and "executor_dependency_mismatch" in codes(item)


def test_mapping_naming_an_outside_prerequisite_vetoes(tmp_path: Path) -> None:
    item = shape(tmp_path, "blocked_by: {FEAT-009: x}", **{feat(9): ready()})
    assert "executor_dependency_mismatch" in codes(item)


def test_empty_mapping_preserves_the_body_fallback(tmp_path: Path) -> None:
    item = shape(tmp_path, "blocked_by: {}", a_body="## Blocked By\n\n- FEAT-002\n")
    assert item.eligible
    assert item.evidence["sprint"]["waves"] == [["FEAT-002"], ["FEAT-001"]]


def test_valid_shapes_keep_body_fallback_and_later_waves(tmp_path: Path) -> None:
    for fm in (
        "blocked_by: [FEAT-002]",
        "blocked_by: []",
        "blocked_by: FEAT-002, FEAT-008",
        "blocked_by: ''",
    ):
        item = shape(
            tmp_path / fm.replace(" ", "_").replace(":", "")[:12],
            fm,
            a_body="## Blocked By\n\n- FEAT-002\n",
            **{feat(8): raw("status: done")},
        )
        assert item.eligible, fm
        assert item.evidence["sprint"]["waves"] == [["FEAT-002"], ["FEAT-001"]], fm


@pytest.mark.parametrize(
    "a_fm",
    [
        "blocks: [[FEAT-002]]",
        "blocks: [{FEAT-002: reason}]",
        "blocks: [[]]",
        "blocks: [{}]",
        "blocked_by: [[FEAT-002]]",
        "depends_on: [{FEAT-002: x}]",
    ],
)
def test_nested_entries_crash_the_runtime_graph_so_they_veto(tmp_path: Path, a_fm: str) -> None:
    item = shape(tmp_path, a_fm)
    assert not item.eligible and "executor_dependency_mismatch" in codes(item)
    assert item.evidence["executor_dependency_findings"][0]["problem"] == "nested_entry"


def test_nested_entries_on_removed_terminal_or_unrelated_outside_sources_do_not_veto(
    tmp_path: Path,
) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready(),
            feat(2): raw("status: done\nblocks: [[FEAT-001]]"),  # removed terminal member
            feat(9): raw("blocks: [[FEAT-003]]"),  # unrelated outside source
        },
        {"alpha": ["FEAT-001", "FEAT-002"]},
    )
    assert run_for(root, "alpha").eligible


def test_outside_blocks_mapping_naming_a_member_vetoes_unless_proven_satisfied(
    tmp_path: Path,
) -> None:
    for status, vetoed in (
        ("open", True),
        ("done", False),
        ("cancelled", False),
        ("deferred", True),
    ):
        root = tmp_path / status
        build(
            root,
            {feat(1): ready(), feat(9): raw(f"status: {status}\nblocks: {{FEAT-001: why}}")},
            {"alpha": ["FEAT-001"]},
        )
        item = run_for(root, "alpha")
        assert item.eligible is (not vetoed), status
        if vetoed:
            finding = item.evidence["executor_dependency_findings"][0]
            assert finding["problem"] == "outside_blocks_mapping"
            assert finding["target"] == "FEAT-001" and finding["source"] == "FEAT-009"


def test_ambiguous_outside_blocks_mapping_source_wins_over_terminal_satisfaction(
    tmp_path: Path,
) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready(),
            "features/P2-FEAT-009-a.md": raw("status: done\nblocks: {FEAT-001: why}"),
            "features/P3-FEAT-009-b.md": raw("status: done"),
        },
        {"alpha": ["FEAT-001"]},
    )
    assert "executor_dependency_mismatch" in codes(run_for(root, "alpha"))


def test_unrelated_outside_mappings_and_outside_blocked_by_do_not_veto(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready(),
            feat(9): raw("blocks: {FEAT-003: why}\nblocked_by: {FEAT-004: x}"),
        },
        {"alpha": ["FEAT-001"]},
    )
    assert run_for(root, "alpha").eligible


# ------------------------------------------------------------------ active-state evidence


def test_state_file_and_unfinished_runs_are_diagnostics_never_vetoes(tmp_path: Path) -> None:
    root = build(tmp_path / "p", {feat(1): ready()}, {"alpha": ["FEAT-001"]})
    (root / ".sprint-state.json").write_text(
        json.dumps({"sprint_name": "beta", "completed_issues": []})
    )
    item = run_for(root, "alpha")
    assert item.eligible
    notes = [d for d in item.diagnostics if d.code == "active_state_unknown"]
    assert notes and "deletes any old state" in notes[0].message
    assert item.evidence["state"]["sprint_name"] == "beta"
    assert str(root.resolve() / ".sprint-state.json") in notes[0].message


# ---------------------------------------------------------------------------- scoring


def test_priority_axis_is_the_mean_of_bounded_member_priorities(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {feat(1, prio="P0"): ready(), feat(2, prio="P4"): ready(), feat(3, prio="P2"): ready()},
        {"alpha": ["FEAT-001", "FEAT-002"], "beta": ["FEAT-001", "FEAT-003"]},
    )
    state = sprint_state(root)
    alpha = sprint_of(state, "alpha")
    # priority scores: P0 -> 1.0, P4 -> 0.36; mean 0.68 (no second lower-bound mapping)
    assert alpha.axes["priority"].score == pytest.approx((1.0 + 0.36) / 2)
    assert sprint_of(state, "beta").axes["priority"].score == pytest.approx((1.0 + 0.68) / 2)


def test_missing_member_priority_leaves_the_priority_axis_missing(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {feat(1): ready(), "features/FEAT-002-nopriority.md": ready()},
        {"alpha": ["FEAT-001", "FEAT-002"]},
    )
    item = run_for(root, "alpha")
    assert item.eligible
    assert item.axes["priority"].score is None
    assert item.axes["priority"].missing_reason == "member_priority_missing_or_invalid"


def test_ready_sprint_without_history_still_scores_on_two_axes(tmp_path: Path) -> None:
    root = build(tmp_path / "p", {feat(1): ready()}, {"alpha": ["FEAT-001"]})
    item = run_for(root, "alpha")
    assert item.axes["since_last_run"].score is None
    assert item.axes["since_last_run"].missing_reason == "history_not_collected"
    assert (item.resolved_axes, item.applicable_axes) == (2, 3)
    assert item.utility is not None and item.evidence["scoring"]["mode"] == "scored"


def test_all_positive_weight_axes_missing_uses_the_cold_start_fallback(tmp_path: Path) -> None:
    from dataclasses import replace

    from little_loops.config import NextConfig

    root = build(tmp_path / "p", {feat(1): ready()}, {"alpha": ["FEAT-001"]})
    settings = NextConfig(
        present=True,
        raw={"verbs": {"run-sprint": {"weights": {"ready_share": 0, "priority": 0}}}},
    ).resolve_arena_settings()
    state = sprint_state(root)
    item = [
        a for a in assess_candidates(state, settings=settings) if a.action_type == "run-sprint"
    ][0]
    # only since_last_run carries weight and it is missing without history
    assert (
        item.eligible and item.utility is None and item.evidence["scoring"]["mode"] == "cold_start"
    )
    ranked = [a for a in assess_candidates(state, settings=settings) if a.bucket_rank]
    assert replace(item).selection_score is None and ranked


def test_candidates_rank_by_utility_then_target(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1, prio="P0"): ready(),
            feat(2, prio="P5"): ready(),
            feat(3, prio="P5"): ready({"blocked_by": ["FEAT-002"]}),
        },
        {"good": ["FEAT-001"], "weak": ["FEAT-002", "FEAT-003"]},
    )
    items = {a.target: a for a in assess_sprints(sprint_state(root))}
    assert items["good"].bucket_rank == 1 and items["weak"].bucket_rank == 2
    assert items["good"].utility > items["weak"].utility
    assert "Rank 1 of 2 eligible run-sprint candidates" in items["good"].selection_reason


def test_assessment_is_deterministic_and_json_clean(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {feat(1): ready(), feat(2): plain()},
        {"a": ["FEAT-001"], "b": ["FEAT-002"], "c": ["FEAT-001", "FEAT-777"]},
    )
    state = sprint_state(root)
    first = [a.to_dict() for a in assess_sprints(state)]
    second = [a.to_dict() for a in assess_sprints(state)]
    assert first == second
    assert json.dumps(first, allow_nan=False)


def test_ambiguous_outside_prerequisite_vetoes_the_dependent_sprint_only(tmp_path: Path) -> None:
    root = build(
        tmp_path / "p",
        {
            feat(1): ready({"blocked_by": ["FEAT-009"]}),
            "features/P2-FEAT-009-a.md": ready({"status": "done"}),
            "features/P3-FEAT-009-b.md": ready({"status": "done"}),
            feat(2): ready(),
        },
        {"dependent": ["FEAT-001"], "independent": ["FEAT-002"]},
    )
    state = sprint_state(root)
    dependent = sprint_of(state, "dependent")
    assert {"outside_prerequisite_unresolved", "ambiguous_issue_id"} <= codes(dependent)
    assert "ambiguous_issue" in dependent.gates["prerequisites"].reason
    assert sprint_of(state, "independent").eligible  # unrelated sprints remain eligible


def test_sprint_issue_and_loop_names_never_share_identity_or_diagnostics(tmp_path: Path) -> None:
    from little_loops.next_arena.candidates import assessments_for_target

    root = build(tmp_path / "p", {feat(1): ready(), bug(2): ready()}, {"FEAT-001": ["BUG-002"]})
    state = sprint_state(root)
    assessments = assess_candidates(state, settings=SETTINGS)
    keys = {(a.action_type, a.target_key) for a in assessments if a.target == "FEAT-001"}
    assert ("run-sprint", "sprint:FEAT-001") in keys
    assert ("implement-issue", "issue:FEAT-001") in keys
    sprint, alternates = assessments_for_target(assessments, "sprint:FEAT-001", "run-sprint")
    assert sprint is not None and alternates == ()  # no phantom issue assessment on a sprint
    issue_side, issue_alternates = assessments_for_target(
        assessments, "issue:FEAT-001", "implement-issue"
    )
    assert issue_side is not None
    assert all(a.action_type != "run-sprint" for a in issue_alternates)

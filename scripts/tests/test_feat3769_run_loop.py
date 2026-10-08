"""``run-loop`` generator: gates, cold start, axes, joins, identity, scope, CLI (FEAT-3769)."""

from __future__ import annotations

import json
import math
import shutil
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import little_loops.next_arena.loop_state as loop_state_module
import little_loops.next_arena.state as state_module
from little_loops.cli import main_next
from little_loops.cli.loop import next_loop as legacy
from little_loops.next_arena import render
from little_loops.next_arena.axes import (
    loop_frequency_axis,
    loop_recency_axis,
    loop_success_axis,
)
from little_loops.next_arena.candidates import (
    CandidateAssessment,
    assess_candidates,
    candidates_from_assessments,
)
from little_loops.next_arena.selection import bucket_order_for, select_candidates
from tests.next_arena_candidates_support import issue, ready_issue
from tests.next_arena_loop_support import (
    completed_run,
    isolate_builtins,
    loop_project,
    loop_state,
    loop_yaml,
    run_loop_assessments,
    write_loop,
    write_run,
)
from tests.next_arena_support import AS_OF, collect, schema_errors, write_issue

RUN = "run-loop"
NOW = "2026-10-07T11:00:00+00:00"


@pytest.fixture
def builtin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return isolate_builtins(monkeypatch, tmp_path / "builtin-loops")


@pytest.fixture
def root(tmp_path: Path, builtin: Path) -> Path:
    return loop_project(tmp_path / "proj")


def assess(root: Path, **kwargs: Any) -> dict[str, CandidateAssessment]:
    return run_loop_assessments(loop_state(root, **kwargs))


# ------------------------------------------------------------------------- cold start


def test_never_run_project_local_public_is_a_fallback_after_scored_loops(root: Path) -> None:
    write_loop(root, "fresh.yaml", loop_yaml("fresh"))
    write_loop(root, "veteran.yaml", loop_yaml("veteran"))
    write_loop(root, "another.yaml", loop_yaml("another"))
    write_run(root, "2026-10-06T100000", "veteran", completed_run("2026-10-06T10:00:00Z"))
    items = assess(root)
    assert items["veteran"].utility is not None and items["veteran"].bucket_rank == 1
    for name in ("another", "fresh"):  # utility=null fallback, ordered by target
        assert items[name].eligible and items[name].utility is None
        assert items[name].gates["cold_start_scope"].code == "local_public_fallback"
    assert (items["another"].bucket_rank, items["fresh"].bucket_rank) == (2, 3)
    assert "cold start" in items["fresh"].selection_reason
    assert "ordered by target" in items["fresh"].selection_reason
    assert "priority" not in items["fresh"].selection_reason
    assert all(items["fresh"].axes[a].score is None for a in ("frequency", "recency", "success"))


def test_builtin_draft_and_non_public_without_a_run_fail_cold_start_scope(
    root: Path, builtin: Path
) -> None:
    (builtin / "bi.yaml").write_text(loop_yaml("bi"))
    write_loop(root, "runs/d1/workflow.yaml", loop_yaml("drafty"))
    write_loop(root, "internal.yaml", loop_yaml("internal", extra="visibility: internal"))
    write_loop(root, "example.yaml", loop_yaml("example", extra="visibility: example"))
    write_loop(root, "base.yaml", loop_yaml("base", extra="visibility: internal"))
    write_loop(root, "kid.yaml", "name: kid\nfrom: base\n")  # inherits internal
    write_loop(root, "public.yaml", loop_yaml("public"))
    items = assess(root)
    for name in ("bi", "d1", "internal", "example", "kid", "base"):
        item = items[name]
        assert not item.eligible, name
        assert item.exclusion_reasons == ("cold_start_scope",), name
        assert item.gates["cold_start_scope"].status == "fail"
        assert item.fully_resolved is False
    assert items["public"].eligible
    assert items["public"].evidence["loop"]["visibility"] == "public"


def test_cold_start_scope_is_lifted_by_a_qualifying_run(root: Path, builtin: Path) -> None:
    (builtin / "bi.yaml").write_text(loop_yaml("bi"))
    write_loop(root, "internal.yaml", loop_yaml("internal", extra="visibility: internal"))
    write_loop(root, "runs/d1/workflow.yaml", loop_yaml("drafty"))
    for name in ("bi", "internal", "drafty"):
        write_run(root, "2026-10-06T100000", name, completed_run("2026-10-06T10:00:00Z"))
    items = assess(root)
    for name in ("bi", "internal", "d1"):
        assert items[name].eligible and items[name].utility is not None, name
        assert items[name].gates["cold_start_scope"].code == "has_qualifying_run"


def test_a_future_or_malformed_run_does_not_lift_the_scope(root: Path, builtin: Path) -> None:
    (builtin / "bi.yaml").write_text(loop_yaml("bi"))
    write_run(root, "2026-10-09T100000", "bi", completed_run("2026-10-09T10:00:00Z"))
    write_run(root, "2026-10-01T100000", "bi", "{broken")
    item = assess(root)["bi"]
    assert not item.eligible and item.exclusion_reasons == ("cold_start_scope",)


def test_project_without_local_loops_or_history_has_an_explained_empty_bucket(
    root: Path, builtin: Path
) -> None:
    (builtin / "zzz-first.yaml").write_text(loop_yaml("zzz-first"))
    (builtin / "adopt.yaml").write_text(loop_yaml("adopt"))
    state = loop_state(root)
    assessments = assess_candidates(state)
    assert not any(a.fully_resolved for a in assessments if a.action_type == RUN)
    notes = render.bucket_diagnostics(assessments, (RUN,))
    assert [d.code for d in notes] == ["gate_failed"] and "cold_start_scope" in notes[0].message


def test_no_definitions_at_all_is_an_empty_source(root: Path) -> None:
    notes = render.bucket_diagnostics(assess_candidates(loop_state(root)), (RUN,))
    assert [d.code for d in notes] == ["empty_source"]
    assert "valid loop definition" in notes[0].message


# --------------------------------------------------------------------------------- axes


def test_axis_curves_use_the_lower_bounded_mapping(root: Path) -> None:
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    for i, status in enumerate(["completed", "completed", "failed", "timed_out", "interrupted"]):
        write_run(
            root,
            f"2026-10-0{i + 1}T100000",
            "alpha",
            completed_run(f"2026-10-0{i + 1}T10:00:00Z", status),
        )
    axes = assess(root)["alpha"].axes
    # frequency: lerp(0.4, 1, log1p(5)/log1p(50)); the interrupted run counts toward frequency.
    x = math.log1p(5) / math.log1p(50)
    assert axes["frequency"].score == pytest.approx(0.4 + 0.6 * x)
    # recency: latest start 2026-10-05T10:00Z is 2 days before as_of (12:00 on 10-07) minus 2h.
    age_days = (AS_OF - (AS_OF.replace(day=5, hour=10))).total_seconds() / 86400
    assert axes["recency"].score == pytest.approx(0.2 + 0.8 * math.exp(-math.log(2) * age_days / 7))
    # success: 2 completed of 4 recognized terminal runs (interrupted is not a failure).
    assert axes["success"].score == pytest.approx(0.2 + 0.8 * 0.5)
    assert axes["success"].raw["terminal_runs"] == 4
    assert [a.configured_weight for a in axes.values()] == [0.5, 0.3, 0.2]


def test_curve_primitives_are_bounded_and_missing_is_never_a_present_zero() -> None:
    assert loop_frequency_axis(0).score is None
    assert loop_frequency_axis(1).score > 0.4
    assert loop_frequency_axis(10_000).score == pytest.approx(1.0)  # capped at the reference
    assert loop_recency_axis(None, AS_OF).score is None
    assert loop_recency_axis(AS_OF, AS_OF).score == pytest.approx(1.0)
    assert loop_recency_axis(AS_OF - timedelta(days=3650), AS_OF).score == pytest.approx(
        0.2, abs=1e-3
    )
    assert loop_success_axis(0, 0).score is None
    assert loop_success_axis(0, 3).score == pytest.approx(0.2)
    assert loop_success_axis(3, 3).score == pytest.approx(1.0)


def test_nonterminal_statuses_supply_frequency_and_recency_but_not_success(root: Path) -> None:
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    for i, status in enumerate(["interrupted", "awaiting_continuation", "running"]):
        write_run(
            root,
            f"2026-10-0{i + 1}T100000",
            "alpha",
            completed_run(f"2026-10-0{i + 1}T10:00:00Z", status),
        )
    write_run(root, "2026-10-04T100000", "alpha", {"started_at": "2026-10-04T10:00:00Z"})
    item = assess(root)["alpha"]
    assert item.axes["frequency"].score is not None and item.axes["recency"].score is not None
    assert item.axes["success"].score is None
    assert item.axes["success"].missing_reason == "no_terminal_runs"
    assert item.utility is not None and item.eligible


def test_no_valid_run_records_means_all_three_axes_missing(root: Path) -> None:
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    write_run(root, "2026-10-01T100000", "alpha", "{broken")
    write_run(root, "2026-10-02T100000", "alpha", ["x"])
    write_run(root, "2026-10-03T100000", "alpha", None)
    item = assess(root)["alpha"]
    assert all(a.score is None for a in item.axes.values())
    assert {a.missing_reason for a in item.axes.values()} == {"no_qualifying_runs"}
    assert item.eligible and item.utility is None  # local-public fallback
    assert item.evidence["loop"]["history"]["excluded_runs"] == 3


def test_unavailable_history_keeps_the_local_public_fallback_without_claiming_never_ran(
    root: Path,
) -> None:
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    (root / ".loops" / ".history").write_text("not a directory")
    state = loop_state(root)
    item = run_loop_assessments(state)["alpha"]
    assert item.eligible and item.utility is None
    assert {a.missing_reason for a in item.axes.values()} == {"history_unavailable"}
    assert item.evidence["loop"]["history"]["available"] is False
    assert any(d.code == "loop_history_unavailable" for d in state.loop_diagnostics)
    # Issue recommendations are unaffected by the unavailable loop history.
    assert state.records == ()


def test_unavailable_history_does_not_resurrect_a_builtin(root: Path, builtin: Path) -> None:
    (builtin / "bi.yaml").write_text(loop_yaml("bi"))
    (root / ".loops").mkdir(exist_ok=True)
    (root / ".loops" / ".history").write_text("x")
    assert not assess(root)["bi"].eligible


def test_minimum_evidence_requires_a_positive_weight_resolved_axis(
    tmp_path: Path, builtin: Path
) -> None:
    config = {
        "project": {"name": "t"},
        "next": {"verbs": {"run-loop": {"weights": {"frequency": 0, "recency": 0, "success": 1}}}},
    }
    root = loop_project(tmp_path / "w", config=config)
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    write_run(root, "2026-10-01T100000", "alpha", {"started_at": "2026-10-01T10:00:00Z"})
    item = assess(root)["alpha"]
    # frequency/recency resolved but have zero weight; success (positive) has no terminal run.
    assert item.eligible and item.utility is None
    assert item.evidence["scoring"] == {"mode": "cold_start", "minimum_evidence": False}


def test_weight_overrides_through_next_verbs_change_the_effective_weights(
    tmp_path: Path, builtin: Path
) -> None:
    config = {
        "project": {"name": "t"},
        "next": {"verbs": {"run-loop": {"weights": {"success": 4}}}},
    }
    root = loop_project(tmp_path / "w", config=config)
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    write_run(root, "2026-10-01T100000", "alpha", completed_run("2026-10-01T10:00:00Z", "failed"))
    item = assess(root)["alpha"]
    assert item.axes["success"].configured_weight == 4.0
    assert item.axes["success"].effective_weight == pytest.approx(4 / 4.8)


def test_legacy_next_loop_weights_do_not_affect_the_arena_verb(
    tmp_path: Path, builtin: Path
) -> None:
    def utility(config: dict[str, Any], sub: str) -> float | None:
        root = loop_project(tmp_path / sub, config={"project": {"name": "t"}, **config})
        write_loop(root, "alpha.yaml", loop_yaml("alpha"))
        write_run(
            root, "2026-10-01T100000", "alpha", completed_run("2026-10-01T10:00:00Z", "failed")
        )
        return assess(root)["alpha"].utility

    base = utility({}, "a")
    legacy_tuned = utility({"next": {"loop_history": {"weights": {"success": 9}}}}, "b")
    assert base is not None and base == legacy_tuned


def test_arena_history_policy_differs_from_the_legacy_scorer_side_by_side(root: Path) -> None:
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    states = ["completed", "completed", "interrupted", "failed"]
    for i, status in enumerate(states):
        write_run(
            root,
            f"2026-10-0{i + 1}T100000",
            "alpha",
            completed_run(f"2026-10-0{i + 1}T10:00:00Z", status),
        )
    legacy_runs = legacy._scan_history(root / ".loops")["alpha"]
    _score, legacy_success, _last = legacy._score_loop(
        legacy_runs, as_of=AS_OF, weights={"frequency": 0.5, "recency": 0.3, "success": 0.2}
    )
    assert legacy_success == pytest.approx(0.5)  # 2 of 4: interrupted counts as a failure
    arena = assess(root)["alpha"].axes["success"]
    assert arena.raw["success_fraction"] == pytest.approx(2 / 3)  # recognized terminal only
    # Legacy next-loop output is unchanged (the arena adds nothing to it).
    assert legacy._scan_history(root / ".loops")["alpha"] == legacy_runs


# --------------------------------------------------------------- joins on the logical name


def test_history_joins_on_the_persisted_logical_name_not_the_command_target(root: Path) -> None:
    write_loop(root, "file-stem.yaml", loop_yaml("persisted-name"))
    write_run(root, "2026-10-06T100000", "persisted-name", completed_run("2026-10-06T10:00:00Z"))
    write_run(
        root, "2026-10-06T110000", "file-stem", completed_run("2026-10-06T11:00:00Z", "failed")
    )
    item = assess(root)["file-stem"]
    loop = item.evidence["loop"]
    assert loop["history_join_key"] == "persisted-name"
    assert loop["history"]["qualified_runs"] == 1  # the stem-named folder is another loop's
    assert item.axes["success"].raw["completed"] == 1
    assert item.display_command == "ll-loop run -- file-stem"
    assert "persisted FSMLoop.name" in loop["history_join"]


def test_draft_folder_alias_joins_on_the_draft_internal_name(root: Path) -> None:
    write_loop(root, "runs/inst-9/workflow.yaml", loop_yaml("generated-logical"))
    write_run(root, "2026-10-06T100000", "generated-logical", completed_run("2026-10-06T10:00:00Z"))
    item = assess(root)["inst-9"]
    assert item.eligible  # a qualifying run lifts the draft scope
    assert item.evidence["loop"]["history_join_key"] == "generated-logical"
    assert item.evidence["loop"]["draft"] == {
        "folder": "inst-9",
        "internal_name": "generated-logical",
    }


def test_shared_logical_names_disclose_unknown_source_attribution(root: Path) -> None:
    write_loop(root, "one.yaml", loop_yaml("same"))
    write_loop(root, "two.yaml", loop_yaml("same"))
    write_run(root, "2026-10-06T100000", "same", completed_run("2026-10-06T10:00:00Z"))
    items = assess(root)
    for name, other in (("one", "two"), ("two", "one")):
        loop = items[name].evidence["loop"]
        assert loop["history_attribution"] == "shared_logical_name"
        assert loop["shared_logical_name_targets"] == [other]
        assert loop["history"]["qualified_runs"] == 1
    write_loop(root, "solo.yaml", loop_yaml("alone"))
    assert assess(root)["solo"].evidence["loop"]["history_attribution"] == "logical_name_only"


def test_filename_name_mismatch_alone_is_valid(root: Path) -> None:
    write_loop(root, "stem.yaml", loop_yaml("totally-different"))
    item = assess(root)["stem"]
    assert item.eligible and item.gates["definition"].status == "pass"


# ------------------------------------------------------------- resolution and shadowing


def test_one_assessment_represents_the_effective_resolution_with_shadow_evidence(
    root: Path, builtin: Path
) -> None:
    (builtin / "shared.yaml").write_text(loop_yaml("shared-builtin"))
    write_loop(root, "shared.yaml", loop_yaml("shared-project"))
    write_loop(root, "pair.yaml", loop_yaml("pair-yaml"))
    write_loop(root, "pair.fsm.yaml", loop_yaml("pair-compiled"))
    assessments = [a for a in assess_candidates(loop_state(root)) if a.action_type == RUN]
    keys = [a.target_key for a in assessments]
    assert len(keys) == len(set(keys))  # never one per competing source
    items = {a.target: a for a in assessments}
    shared = items["shared"].evidence["loop"]
    assert items["shared"].gates["resolution"].status == "pass"
    assert shared["definition_source"] == ".loops/shared.yaml"
    assert [s["source"] for s in shared["shadowed"]] == ["builtin:shared.yaml"]
    assert items["pair"].evidence["loop"]["definition_source"] == ".loops/pair.fsm.yaml"
    assert [s["source"] for s in items["pair"].evidence["loop"]["shadowed"]] == [".loops/pair.yaml"]


def test_direct_path_collision_does_not_fall_through_to_the_definition(root: Path) -> None:
    write_loop(root, "clash.yaml", loop_yaml("clash"))
    (root / "clash").write_text("a file at the project root")
    item = assess(root)["clash"]
    assert not item.eligible and item.exclusion_reasons == ("shadowed_source",)
    assert item.gates["resolution"].status == "fail"
    assert item.evidence["loop"]["resolution"]["kind"] == "direct"
    assert item.action_spec is None


def test_unrunnable_project_file_shadows_a_builtin_of_the_same_name(
    root: Path, builtin: Path
) -> None:
    (builtin / "frag.yaml").write_text(loop_yaml("frag"))
    write_loop(root, "frag.yaml", "fragments:\n  f:\n    action: echo\n")
    item = assess(root)["frag"]
    assert not item.eligible and "shadowed_source" in item.exclusion_reasons


def test_duplicate_draft_logical_names_are_distinct_targets(root: Path) -> None:
    write_loop(root, "runs/a/workflow.yaml", loop_yaml("dup"))
    write_loop(root, "runs/b/workflow.yaml", loop_yaml("dup"))
    write_run(root, "2026-10-06T100000", "dup", completed_run("2026-10-06T10:00:00Z"))
    items = assess(root)
    assert set(items) == {"a", "b"}
    assert items["a"].eligible and items["b"].eligible
    assert items["a"].evidence["loop"]["shared_logical_name_targets"] == ["b"]


# --------------------------------------------------------------------- inputs and identity


def test_unresolved_input_is_an_explained_exclusion(root: Path) -> None:
    write_loop(root, "needy.yaml", loop_yaml("needy", action="echo ${context.input}"))
    item = assess(root)["needy"]
    assert not item.eligible and item.exclusion_reasons == ("unresolved_input",)
    assert item.gates["inputs"].status == "fail"
    assert item.evidence["loop"]["inputs"]["missing_keys"] == ["input"]
    assert item.action_spec is None and item.display_command is None


def test_invalid_definition_remains_explainable(root: Path) -> None:
    write_loop(
        root,
        "bad.yaml",
        "name: bad\ninitial: nowhere\nscope: ['.']\nstates:\n  go:\n    terminal: true\n",
    )
    item = assess(root)["bad"]
    assert not item.eligible and "validation_error" in item.exclusion_reasons
    assert "inputs" not in item.gates  # not evaluated for an invalid definition
    assert item.evidence["loop"]["errors"]


def test_eligible_candidate_carries_the_six_field_spec_and_run_loop_key(root: Path) -> None:
    path = write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    item = assess(root)["alpha"]
    spec = item.action_spec
    assert item.action_key == "run-loop"
    assert spec.variant == "loop" and spec.target == "alpha"
    assert spec.definition_source == ".loops/alpha.yaml"
    assert spec.definition_digest.startswith("sha256:") and len(spec.definition_digest) == 71
    assert spec.fingerprint_scope == "v1/top-level-bytes"
    assert spec.working_directory == str(root)
    assert item.display_command == "ll-loop run -- alpha"
    assert item.evidence["loop"]["definition_path"] == str(path)
    assert item.evidence["loop"]["digest_label"] == "top-level definition bytes"


def test_changing_parent_or_steering_changes_assessment_but_not_the_limited_fingerprint(
    root: Path,
) -> None:
    write_loop(root, "base.yaml", loop_yaml("base", action="echo one"))
    write_loop(root, "kid.yaml", "name: kid\nfrom: base\n")
    first = assess(root)["kid"]
    # Same top-level bytes, but the parent now requires an input -> a fresh assessment says no.
    write_loop(root, "base.yaml", loop_yaml("base", action="echo ${context.input}"))
    second = assess(root)["kid"]
    assert first.eligible and not second.eligible
    assert (
        first.evidence["loop"]["definition_digest"] == second.evidence["loop"]["definition_digest"]
    )
    # Steering can make an input-requiring loop eligible while the fingerprint is unchanged.
    (root / ".ll").mkdir(exist_ok=True)
    (root / ".ll" / "program.md").write_text("## Directive\nsteer\n")
    write_loop(root, "base.yaml", loop_yaml("base", action="echo ${context.directive}"))
    third = assess(root)["kid"]
    assert third.eligible and third.action_fingerprint is not None
    write_loop(root, "base.yaml", loop_yaml("base", action="echo ${context.directive} two"))
    fourth = assess(root)["kid"]
    assert fourth.action_fingerprint == third.action_fingerprint  # parent bytes are out of scope


def test_relocating_the_project_keeps_the_fingerprint(tmp_path: Path, builtin: Path) -> None:
    first = loop_project(tmp_path / "one")
    write_loop(first, "alpha.yaml", loop_yaml("alpha"))
    write_run(first, "2026-10-06T100000", "alpha", completed_run("2026-10-06T10:00:00Z"))
    second = tmp_path / "moved" / "two"
    shutil.copytree(first, second)
    a, b = assess(first)["alpha"], assess(second)["alpha"]
    assert a.action_fingerprint == b.action_fingerprint
    assert a.action_spec.working_directory != b.action_spec.working_directory
    assert str(first) not in json.dumps(
        {"source": a.action_spec.definition_source, "digest": a.action_spec.definition_digest}
    )


def test_changing_the_top_level_bytes_changes_the_fingerprint(root: Path) -> None:
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    before = assess(root)["alpha"].action_fingerprint
    write_loop(root, "alpha.yaml", loop_yaml("alpha", action="echo changed"))
    assert assess(root)["alpha"].action_fingerprint != before


# ----------------------------------------------------------------- scope-aware collection


def test_issue_only_scope_performs_no_loop_reads_validations_or_history_reads(
    tmp_path: Path, builtin: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = loop_project(tmp_path / "proj")
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    write_run(root, "2026-10-06T100000", "alpha", completed_run("2026-10-06T10:00:00Z"))
    write_issue(root, "features/P2-FEAT-001-a.md", text=ready_issue())

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("loop domain touched in an issue-only scope")

    monkeypatch.setattr(loop_state_module, "_read_bytes", boom)
    monkeypatch.setattr(loop_state_module, "_scandir", boom)
    monkeypatch.setattr(loop_state_module, "_read_state_bytes", boom)
    monkeypatch.setattr("little_loops.fsm.validation.load_and_validate", boom)
    state = collect(root)  # issue-only collection (the default)
    assert state.loop_definitions is None and state.loop_history is None
    assessments = assess_candidates(state)
    assert {a.action_type for a in assessments} == {
        "implement-issue",
        "refine-issue",
        "resolve-blocker",
    }


def test_issue_domain_results_are_invariant_to_loop_capture(tmp_path: Path, builtin: Path) -> None:
    root = loop_project(tmp_path / "proj")
    write_issue(root, "features/P2-FEAT-001-a.md", text=ready_issue())
    write_issue(root, "bugs/P1-BUG-002-b.md", text=issue())
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    write_run(root, "2026-10-06T100000", "alpha", completed_run("2026-10-06T10:00:00Z"))
    write_run(root, "2026-10-06T110000", "alpha", "{malformed")
    order = bucket_order_for(["implement-issue", "refine-issue", "resolve-blocker"])

    def issue_view(include_loops: bool) -> tuple[Any, ...]:
        state = collect(root, include_loops=include_loops)
        assessments = [a for a in assess_candidates(state) if a.action_type != RUN]
        picked = select_candidates(
            candidates_from_assessments(assessments), top=5, bucket_order=order, caps={}
        )
        return (
            [a.to_dict() for a in assessments],
            [c.to_dict() for c in picked],
            [d.to_dict() for d in state.diagnostics],
        )

    assert issue_view(False) == issue_view(True)


def test_full_pass_can_spend_a_global_top_slot_on_a_loop(root: Path) -> None:
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    state = loop_state(root)
    chosen = select_candidates(
        candidates_from_assessments(assess_candidates(state)),
        top=3,
        bucket_order=bucket_order_for(None),
        caps={},
    )
    assert [(c.action_type, c.target) for c in chosen] == [(RUN, "alpha")]


# -------------------------------------------------------------------------------- CLI


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state_module, "_normalize_as_of", lambda _as_of: AS_OF)


@pytest.fixture
def cli(capfd: pytest.CaptureFixture[str], clock: None) -> Callable[..., tuple[int, str, str]]:
    def _run(*argv: str) -> tuple[int, str, str]:
        with patch("sys.argv", ["ll-next", *argv]):
            code = main_next()
        captured = capfd.readouterr()
        return code, captured.out, captured.err

    return _run


@pytest.fixture
def cli_root(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    write_loop(root, "alpha.yaml", loop_yaml("alpha"))
    write_loop(root, "-foo.yaml", loop_yaml("dash-foo"))
    write_loop(root, "--json.yaml", loop_yaml("dash-json"))
    write_loop(
        root,
        "bad.yaml",
        "name: bad\ninitial: nowhere\nscope: ['.']\nstates:\n  go:\n    terminal: true\n",
    )
    write_loop(root, "needy.yaml", loop_yaml("needy", action="echo ${context.input}"))
    write_run(root, "2026-10-06T100000", "alpha", completed_run("2026-10-06T10:00:00Z"))
    monkeypatch.chdir(root)
    return root


def run_json(cli: Callable[..., tuple[int, str, str]], *argv: str) -> tuple[int, dict[str, Any]]:
    code, out, err = cli("--json", *argv)
    assert err == ""
    envelope = json.loads(out)
    schema = render.load_output_schema()
    assert schema_errors(envelope, schema, schema) == []
    return code, envelope


def test_type_run_loop_recommends_the_best_loop(cli: Any, cli_root: Path) -> None:
    code, envelope = run_json(cli, "--type", RUN)
    assert code == 0
    rec = envelope["recommendations"][0]
    assert rec["action_type"] == RUN and rec["target"] == "alpha"
    assert rec["action_key"] == "run-loop" and rec["target_key"] == "loop:alpha"
    assert rec["action_spec"]["variant"] == "loop"
    assert rec["display_command"] == "ll-loop run -- alpha"
    assert envelope["schema_version"] == 2


def test_text_output_for_a_loop_recommendation(cli: Any, cli_root: Path) -> None:
    code, out, err = cli("--type", RUN)
    assert code == 0 and err == ""
    assert "[run-loop] alpha" in out and "ll-loop run -- alpha" in out
    assert "frequency" in out and "priority" not in out.split("axes:")[1].splitlines()[0]


def test_explain_selected_excluded_invalid_and_absent_loops(cli: Any, cli_root: Path) -> None:
    code, env = run_json(cli, "--explain", RUN, "alpha")
    assert code == 0 and env["explanation"]["assessment"]["eligible"] is True
    assert env["explanation"]["alternates"] == []  # loop targets share no key with issues
    code, env = run_json(cli, "--explain", RUN, "needy")
    assert code == 0 and env["explanation"]["assessment"]["exclusion_reasons"] == [
        "unresolved_input"
    ]
    code, env = run_json(cli, "--explain", RUN, "bad")
    assert code == 0 and env["explanation"]["assessment"]["eligible"] is False
    code, env = run_json(cli, "--explain", RUN, "ghost")
    assert code == 1 and env["explanation"] is None
    assert [d["code"] for d in env["diagnostics"]] == ["target_not_found"]
    assert "loop definition" in env["diagnostics"][0]["message"]
    code, out, err = cli("--explain", RUN, "ghost")
    assert code == 1 and err == "" and "no loop target 'ghost'" in out


@pytest.mark.parametrize("operand", ["-foo", "--json"])
def test_option_looking_explain_targets_are_literal_operands(
    cli: Any, cli_root: Path, operand: str
) -> None:
    code, env = run_json(cli, "--explain", RUN, operand)
    assert code == 0
    assessment = env["explanation"]["assessment"]
    assert assessment["target"] == operand and assessment["target_key"] == f"loop:{operand}"
    assert assessment["display_command"] == f"ll-loop run -- {operand}"


def test_trailing_output_flags_keep_their_meaning_after_a_literal_target(
    cli: Any, cli_root: Path
) -> None:
    code, out, err = cli("--explain", RUN, "--json", "--json")
    assert code == 0 and err == ""
    envelope = json.loads(out)  # one literal '--json' target, one real --json flag
    assert envelope["explanation"]["assessment"]["target"] == "--json"
    code, out, _ = cli("--explain", RUN, "-foo")
    assert code == 0 and out.startswith("ll-next --explain run-loop -foo")


def test_explain_conflicts_remain_usage_errors(cli: Any, cli_root: Path) -> None:
    for argv in (
        ("--explain", RUN, "alpha", "--top", "2"),
        ("--explain", RUN, "alpha", "--type", RUN),
        ("--explain", RUN),
    ):
        code, out, err = cli(*argv)
        assert code == 2 and out == "" and err.strip()


def test_loop_and_issue_sharing_a_name_keep_diagnostics_and_alternates_separate(
    cli: Any, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_issue(root, "features/P2-FEAT-001-first.md", text=ready_issue())
    write_issue(root, "features/P3-FEAT-001-second.md", text=ready_issue())  # ambiguous id
    write_loop(
        root, "FEAT-001.yaml", "name: FEAT-001\ninitial: go\nstates:\n  go:\n    terminal: true\n"
    )
    monkeypatch.chdir(root)
    _, issue_env = run_json(cli, "--explain", "implement-issue", "FEAT-001")
    issue_diags = issue_env["diagnostics"]
    assert issue_diags and all(d["subject"] == "FEAT-001" for d in issue_diags)
    assert "ambiguous_issue_id" in {d["code"] for d in issue_diags}
    _, loop_env = run_json(cli, "--explain", RUN, "FEAT-001")
    loop_diags = loop_env["diagnostics"]
    assert loop_diags and all(d["subject"] == "loop:FEAT-001" for d in loop_diags)
    assert "ambiguous_issue_id" not in {d["code"] for d in loop_diags}
    assert loop_env["explanation"]["assessment"]["action_type"] == RUN
    assert loop_env["explanation"]["alternates"] == []
    assert {a["action_type"] for a in issue_env["explanation"]["alternates"]} == {
        "refine-issue",
        "resolve-blocker",
    }


def test_issue_scoped_runs_do_not_touch_the_loop_domain(
    cli: Any, cli_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_issue(cli_root, "features/P2-FEAT-001-a.md", text=ready_issue())

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("loop domain touched")

    monkeypatch.setattr(loop_state_module, "_read_bytes", boom)
    monkeypatch.setattr(loop_state_module, "_scandir", boom)
    assert run_json(cli, "--type", "implement-issue")[0] == 0
    assert run_json(cli, "--explain", "refine-issue", "FEAT-001")[0] == 0
    assert run_json(cli, "--type", "resolve-blocker")[0] in (0, 1)


def test_real_builtins_never_leak_validation_warnings_to_stdout_or_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock: None, capfd: pytest.CaptureFixture[str]
) -> None:
    """Over the shipped built-ins (83 validation warnings): stderr empty, stdout clean JSON."""
    root = loop_project(tmp_path / "proj")
    monkeypatch.chdir(root)
    with patch("sys.argv", ["ll-next", "--json", "--type", RUN]):
        code = main_next()
    out, err = capfd.readouterr()
    assert err == "" and code == 1  # history-free project: no built-in is offered
    envelope = json.loads(out)
    assert envelope["recommendations"] == []
    codes = {d["code"] for d in envelope["diagnostics"]}
    assert "loop_validation_warning" not in codes and "gate_failed" in codes
    assert envelope["schema_version"] == 2


def test_help_documents_the_new_action_types(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["ll-next", "--help"]):
        code = main_next()
    out = capsys.readouterr().out
    assert code == 0
    for name in ("resolve-blocker", "run-loop"):
        assert name in out
    assert "exact loop command operand" in " ".join(out.split())


def test_configured_run_loop_cap_applies_to_selection(tmp_path: Path, builtin: Path) -> None:
    config = {"project": {"name": "t"}, "next": {"verbs": {"run-loop": {"cap": 1}}}}
    root = loop_project(tmp_path / "proj", config=config)
    for name in ("a", "b", "c"):
        write_loop(root, f"{name}.yaml", loop_yaml(name))
        write_run(root, "2026-10-06T100000", name, completed_run("2026-10-06T10:00:00Z"))
    state = loop_state(root)
    settings = state.config.next.resolve_arena_settings()
    chosen = select_candidates(
        candidates_from_assessments(assess_candidates(state, settings=settings)),
        top=3,
        bucket_order=bucket_order_for([RUN]),
        caps=settings.caps,
    )
    assert len(chosen) == 1

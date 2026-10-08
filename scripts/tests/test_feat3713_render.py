"""Human/explain rendering of sprint and scan evidence (FEAT-3713 step 4)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from little_loops.next_arena.candidates import (
    assess_candidates,
    assessments_for_target,
    candidates_from_assessments,
)
from little_loops.next_arena.render import build_explanation, render_explain_text, render_text
from little_loops.next_arena.scan_state import resolve_scan_scope
from tests.next_arena_support import memory_state
from tests.sprint_support import SETTINGS, bug, build, feat, ready, sprint_state, write_sprint
from tests.test_feat3713_scan_candidates import activity


def explain(state: Any, key: str, verb: str, target: str) -> str:
    assessments = assess_candidates(state, settings=SETTINGS)
    named, alternates = assessments_for_target(assessments, key, verb)
    return render_explain_text(
        project_root=state.project_root,
        explanation=build_explanation(named, alternates),
        verb=verb,
        target=target,
    )


def sprint_project(tmp_path: Path) -> Any:
    root = build(
        tmp_path / "p",
        {feat(1): ready(), bug(2): ready({"blocked_by": ["FEAT-001"]})},
        {},
    )
    write_sprint(root, "alpha", ["FEAT-001", "BUG-002"])
    return root, sprint_state(root)


def test_sprint_explain_shows_identity_members_waves_history_and_the_runtime_note(
    tmp_path: Path,
) -> None:
    root, state = sprint_project(tmp_path)
    text = explain(state, "sprint:alpha", "run-sprint", "alpha")
    assert "eligible: yes -> ll-sprint run -- alpha" in text
    assert "sprint: .sprints/alpha.yaml; sprint definition bytes sha256:" in text
    assert "members: remaining FEAT-001, BUG-002; done/cancelled (removed) -" in text
    assert "waves: FEAT-001 -> BUG-002" in text
    assert "history: no qualified invocation observed (history_not_collected)" in text
    assert "[name-based-definition-unknown]" in text
    assert "loads the definition current when it runs" in text
    assert "learning-test preflight" in text


def test_sprint_explain_for_an_excluded_sprint_lists_member_problems(tmp_path: Path) -> None:
    root = build(tmp_path / "p", {feat(1): ready()}, {})
    write_sprint(root, "alpha", ["FEAT-001", "BUG-404"])
    text = explain(sprint_state(root), "sprint:alpha", "run-sprint", "alpha")
    assert "eligible: no" in text and "missing_issue" in text
    assert "member BUG-404: missing_issue" in text


def test_sprint_recommendation_text_has_one_evidence_line(tmp_path: Path) -> None:
    root, state = sprint_project(tmp_path)
    cands = [
        c
        for c in candidates_from_assessments(assess_candidates(state, settings=SETTINGS))
        if c.action_type == "run-sprint"
    ]
    text = render_text(project_root=root, recommendations=cands, bucket_order=("run-sprint",))
    assert "ll-sprint run -- alpha" in text
    assert "sprint: 1 of 2 remaining member(s) ready now; last run: no qualified invocation" in text


def _scan_state(tmp_path: Path, **overrides: Any) -> Any:
    root = tmp_path / "proj"
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    scope = resolve_scan_scope(["src", "missing-dir"], ["**/vendor/**"], root)
    return replace(memory_state(root, {}), scan_scope=scope, scan_activity=activity(**overrides))


def test_scan_explain_distinguishes_exact_lower_bound_partial_and_unknown(tmp_path: Path) -> None:
    key = None
    cases = {
        "saturated": ({}, "at least 20 (threshold met; exact total unknown)"),
        "exact": (
            {
                "saturated": False,
                "complete": True,
                "scoped_commit_count": 7,
                "lower_bound": None,
                "truncation_reason": None,
            },
            "exactly 7",
        ),
        "partial": (
            {"saturated": False, "lower_bound": 5, "truncation_reason": "deadline"},
            "at least 5 observed, then deadline (partial, not a count)",
        ),
        "unknown": (
            {
                "available": False,
                "unavailable_reason": "git_failed",
                "detail": "boom",
                "saturated": False,
                "lower_bound": None,
                "truncation_reason": None,
            },
            "UNKNOWN (git_failed: boom)",
        ),
    }
    for name, (overrides, expected) in cases.items():
        state = _scan_state(tmp_path / name, **overrides)
        key = f"scan:{state.scan_scope.scope_hash}"
        text = explain(state, key, "capture-issues", "project")
        assert expected in text, name
        assert "scan-freshness-unknown" in text
        assert "takes no scope argument" in text
        assert "directory 'missing-dir': missing" in text  # dropped directories stay visible


def test_scan_recommendation_text_labels_freshness(tmp_path: Path) -> None:
    state = _scan_state(tmp_path)
    cands = candidates_from_assessments(assess_candidates(state, settings=SETTINGS))
    scan = [c for c in cands if c.action_type == "capture-issues"]
    text = render_text(
        project_root=state.project_root, recommendations=scan, bucket_order=("capture-issues",)
    )
    assert "/ll:scan-codebase" in text
    assert "scan scope: src; >=20 scoped commit(s) in 30 day(s); scan-freshness-unknown" in text

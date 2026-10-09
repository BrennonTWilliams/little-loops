"""refine-issue adapter: ordered checks, legacy ``cmd_next_action`` parity, caps (FEAT-3561 D)."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from little_loops.cli.issues.next_action import cmd_next_action
from little_loops.config import BRConfig
from little_loops.next_arena.candidates import assess_candidates, next_refine_step
from tests.next_arena_candidates_support import (
    FORMAT_ENTRY,
    VERIFY_ENTRY,
    get,
    issue,
    project,
)
from tests.next_arena_support import collect, make_project, record, write_issue

REFINE = "refine-issue"
IMPL = "implement-issue"
REL = "bugs/P2-BUG-001-a.md"
REFINE_ENTRY = ("/ll:refine-issue", "2026-09-03T10:00:00")

LEGACY_TO_KEY = {
    "NEEDS_FORMAT": "format-issue",
    "NEEDS_VERIFY": "verify-issues",
    "NEEDS_SCORE": "confidence-check",
    "NEEDS_REFINE": "refine-issue",
    "ALL_DONE": None,
}


def _legacy(root: Path, capsys: pytest.CaptureFixture[str]) -> str:
    """The first token printed by the real ``ll-issues next-action`` for *root*."""
    args = argparse.Namespace(skip=None, refine_cap=5, ready_threshold=85, outcome_threshold=65)
    capsys.readouterr()
    cmd_next_action(BRConfig(root), args)
    return capsys.readouterr().out.split()[0]


def _arena(root: Path, issue_id: str = "BUG-001") -> Any:
    return get(assess_candidates(collect(root)), REFINE, issue_id)


def _case(
    root: Path,
    fm: Mapping[str, Any],
    *,
    sessions: list[tuple[str, str]] | None = None,
    status: str | None = None,
) -> None:
    make_project(root)
    data = dict(fm)
    if status is not None:
        data["status"] = status
    write_issue(root, REL, text=issue(data, sessions=sessions or []))


FORMATTED = [FORMAT_ENTRY]
VERIFIED = [FORMAT_ENTRY, VERIFY_ENTRY]
S90_80 = {"confidence_score": 90, "outcome_confidence": 80}
S70_70 = {"confidence_score": 70, "outcome_confidence": 70}
S90_50 = {"confidence_score": 90, "outcome_confidence": 50}

# (id, frontmatter, sessions, status) -- valid-domain common population
PARITY_CASES = [
    ("unformatted", S90_80, [], None),
    ("unformatted_blocked", S90_80, [], "blocked"),
    ("unverified", S90_80, FORMATTED, None),
    ("unscored", {}, VERIFIED, None),
    ("readiness_only", {"confidence_score": 90}, VERIFIED, None),
    ("outcome_only", {"outcome_confidence": 80}, VERIFIED, None),
    ("below_readiness", {"confidence_score": 70, "outcome_confidence": 80}, VERIFIED, None),
    ("below_outcome", {"confidence_score": 90, "outcome_confidence": 60}, VERIFIED, None),
    ("below_both", S70_70, VERIFIED, None),
    ("below_both_blocked", S70_70, VERIFIED, "blocked"),
    ("all_done", S90_80, VERIFIED, None),
    ("boundary_ok", {"confidence_score": 85, "outcome_confidence": 65}, VERIFIED, None),
    ("boundary_low", {"confidence_score": 84, "outcome_confidence": 65}, VERIFIED, None),
    ("one_refine_run", S70_70, [*VERIFIED, REFINE_ENTRY], None),
    ("capped", S70_70, [*VERIFIED, *[REFINE_ENTRY] * 5], None),
    ("four_refine_runs", S70_70, [*VERIFIED, *[REFINE_ENTRY] * 4], None),
    ("digit_string_scores", {"confidence_score": "70", "outcome_confidence": "70"}, VERIFIED, None),
]


@pytest.mark.parametrize(
    ("fm", "sessions", "status"),
    [pytest.param(fm, s, st, id=name) for name, fm, s, st in PARITY_CASES],
)
def test_adapter_matches_cmd_next_action_on_the_valid_domain(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fm: Mapping[str, Any],
    sessions: list[tuple[str, str]],
    status: str | None,
) -> None:
    _case(tmp_path, fm, sessions=sessions, status=status)
    legacy = LEGACY_TO_KEY[_legacy(tmp_path, capsys)]
    item = _arena(tmp_path)
    assert item.evidence["refinement"]["action_key"] == legacy
    assert item.action_key == legacy
    assert item.eligible is (legacy is not None)


def test_ordered_checks_stop_at_the_first_applicable_step(tmp_path: Path) -> None:
    # no format log, no verify, no scores, below thresholds: format wins
    _case(tmp_path, {})
    item = _arena(tmp_path)
    assert item.action_key == "format-issue"
    assert item.display_command == "/ll:format-issue BUG-001"
    step = item.evidence["refinement"]
    assert (step["formatted"], step["verified"], step["scores_valid"]) == (False, False, False)


@pytest.mark.parametrize(
    ("sessions", "fm", "key"),
    [
        (FORMATTED, {}, "verify-issues"),
        (VERIFIED, {}, "confidence-check"),
        (VERIFIED, {"confidence_score": 90}, "confidence-check"),
        (VERIFIED, S70_70, "refine-issue"),
    ],
)
def test_each_step_maps_to_its_action_key_and_command(
    tmp_path: Path, sessions: list[tuple[str, str]], fm: Mapping[str, Any], key: str
) -> None:
    _case(tmp_path, fm, sessions=sessions)
    item = _arena(tmp_path)
    assert item.action_key == key
    assert item.action_spec is not None
    assert item.action_spec.command == key
    assert list(item.action_spec.args) == ["BUG-001"]
    assert item.display_command == f"/ll:{key} BUG-001"


# ---------------------------------------------------------------- intentional differences


def test_101_65_formatted_verified_requests_confidence_check_while_legacy_says_all_done(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _case(tmp_path, {"confidence_score": 101, "outcome_confidence": 65}, sessions=VERIFIED)
    assert _legacy(tmp_path, capsys) == "ALL_DONE"
    item = _arena(tmp_path)
    assert item.action_key == "confidence-check"
    assert item.evidence["refinement"]["scores_valid"] is False
    assert item.display_command == "/ll:confidence-check BUG-001"
    # and the implementation gate also refuses the invalid score
    assert get(assess_candidates(collect(tmp_path)), IMPL, "BUG-001").eligible is False


@pytest.mark.parametrize(
    "fm",
    [
        {"confidence_score": 90, "outcome_confidence": 101},
        {"confidence_score": -5, "outcome_confidence": 70},
        {"confidence_score": 90.5, "outcome_confidence": 70},
        {"confidence_score": "true", "outcome_confidence": 70},
        {"confidence_score": 90, "outcome_confidence": "999"},
    ],
)
def test_invalid_domain_scores_request_confidence_check(
    tmp_path: Path, fm: Mapping[str, Any]
) -> None:
    _case(tmp_path, fm, sessions=VERIFIED)
    assert _arena(tmp_path).action_key == "confidence-check"


def test_waived_outcome_difference_fixture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fm = {**S90_50, "outcome_gate_waived": True}
    _case(tmp_path, fm, sessions=VERIFIED)
    assert _legacy(tmp_path, capsys) == "NEEDS_REFINE"  # legacy ignores the waiver
    item = _arena(tmp_path)
    assert item.action_key is None and item.eligible is False
    assert "no_refinement_needed" in item.exclusion_reasons
    assert item.evidence["refinement"]["reason"] == "no_refinement_needed"
    # the waiver only removes the outcome shortfall: a readiness shortfall still refines
    _case(
        tmp_path / "ready",
        {"confidence_score": 70, "outcome_confidence": 50, "outcome_gate_waived": "true"},
        sessions=VERIFIED,
    )
    assert _arena(tmp_path / "ready").action_key == "refine-issue"


def test_waiver_does_not_suppress_format_or_verify(tmp_path: Path) -> None:
    fm = {**S90_50, "outcome_gate_waived": True}
    _case(tmp_path / "a", fm, sessions=[])
    assert _arena(tmp_path / "a").action_key == "format-issue"
    _case(tmp_path / "b", fm, sessions=FORMATTED)
    assert _arena(tmp_path / "b").action_key == "verify-issues"


def test_non_boolean_waiver_value_does_not_waive(tmp_path: Path) -> None:
    _case(tmp_path, {**S90_50, "outcome_gate_waived": "yes"}, sessions=VERIFIED)
    assert _arena(tmp_path).action_key == "refine-issue"


# --------------------------------------------------------------------------- refine cap


def test_capped_refine_is_a_diagnostic_and_never_repeats(tmp_path: Path) -> None:
    _case(tmp_path, S70_70, sessions=[*VERIFIED, *[REFINE_ENTRY] * 5])
    item = _arena(tmp_path)
    assert item.action_key is None and item.action_spec is None
    assert item.eligible is False
    assert item.gates["refinement"].status == "fail"
    assert item.gates["refinement"].code == "refine_cap_exhausted"
    assert "refine_cap_exhausted" in item.exclusion_reasons
    assert [d.code for d in item.diagnostics if d.code == "refine_cap_exhausted"] == [
        "refine_cap_exhausted"
    ]
    assert item.evidence["refinement"]["capped"] is True
    assert item.evidence["refinement"]["refine_count"] == 5


def test_refine_cap_is_a_consumed_setting(tmp_path: Path) -> None:
    config = {"next": {"verbs": {"refine-issue": {"refine_cap": 2}}}}
    make_project(tmp_path, config=config)
    write_issue(tmp_path, REL, text=issue(S70_70, sessions=[*VERIFIED, *[REFINE_ENTRY] * 2]))
    item = _arena(tmp_path)
    assert item.gates["refinement"].code == "refine_cap_exhausted"
    assert item.evidence["refinement"]["refine_cap"] == 2
    config = {"next": {"verbs": {"refine-issue": {"refine_cap": 3}}}}
    root = tmp_path / "three"
    make_project(root, config=config)
    write_issue(root, REL, text=issue(S70_70, sessions=[*VERIFIED, *[REFINE_ENTRY] * 2]))
    assert _arena(root).action_key == "refine-issue"


def test_cap_does_not_hide_earlier_applicable_steps(tmp_path: Path) -> None:
    _case(tmp_path, S70_70, sessions=[*FORMATTED, *[REFINE_ENTRY] * 9])
    assert _arena(tmp_path).action_key == "verify-issues"


def test_gap_analysis_refine_runs_are_exempt_from_the_cap(tmp_path: Path) -> None:
    gap = ("/ll:refine-issue:gap-analysis", "2026-09-03T10:00:00")
    _case(tmp_path, S70_70, sessions=[*VERIFIED, *[gap] * 8])
    assert _arena(tmp_path).action_key == "refine-issue"


# ------------------------------------------------------------------- scope & structure


def test_refine_applies_to_open_and_blocked_leaves_only(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-001-open.md": issue({"status": "open"}),
        "bugs/P2-BUG-002-blocked.md": issue({"status": "blocked"}),
        "bugs/P2-BUG-003-deferred.md": issue({"status": "deferred"}),
        "bugs/P2-BUG-004-wip.md": issue({"status": "in_progress"}),
        "bugs/P2-BUG-005-done.md": issue({"status": "done"}),
        "epics/P1-EPIC-006-e.md": issue({"status": "open"}),
    }
    assessments = assess_candidates(project(tmp_path, files))
    eligible = {a.target for a in assessments if a.action_type == REFINE and a.eligible}
    assert eligible == {"BUG-001", "BUG-002"}


def test_refine_assessment_for_ineligible_target_has_no_action_even_if_a_step_exists(
    tmp_path: Path,
) -> None:
    item = get(
        assess_candidates(project(tmp_path, {"bugs/P2-BUG-001-a.md": issue({"status": "done"})})),
        REFINE,
        "BUG-001",
    )
    assert item.evidence["refinement"]["action_key"] == "format-issue"
    assert item.eligible is False
    assert item.action_key is None and item.display_command is None


def test_next_refine_step_is_directly_callable_per_record(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, REL, text=issue(S90_80))
    state = collect(tmp_path)
    rec = record(state, REL)
    step = next_refine_step(rec, state, 5)
    assert step.action_key == "format-issue" and step.legacy_step == "NEEDS_FORMAT"


def test_adapter_is_pure_over_captured_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changing live templates/env/stamp after capture cannot change the step."""
    make_project(tmp_path)
    write_issue(tmp_path, REL, text=issue(S90_80, sessions=VERIFIED))
    state = collect(tmp_path)
    before = next_refine_step(record(state, REL), state, 5)
    (tmp_path / ".ll").mkdir(exist_ok=True)
    (tmp_path / ".ll" / "program-design-cutover.json").write_text('{"cutover": "2020-01-01"}')
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "nowhere"))
    assert next_refine_step(record(state, REL), state, 5) == before
    assert before.action_key is None


def test_threshold_overrides_apply_to_the_refine_comparison(tmp_path: Path) -> None:
    config = {"commands": {"confidence_gate": {"readiness_threshold": 60, "outcome_threshold": 60}}}
    make_project(tmp_path, config=config)
    write_issue(tmp_path, REL, text=issue(S70_70, sessions=VERIFIED))
    assert _arena(tmp_path).action_key is None
    strict = tmp_path / "strict"
    make_project(strict, config={"commands": {"confidence_gate": {"readiness_threshold": 95}}})
    write_issue(strict, REL, text=issue(S70_70, sessions=VERIFIED))
    assert _arena(strict).action_key == "refine-issue"


def test_readiness_gap_axis_reflects_the_arena_comparison(tmp_path: Path) -> None:
    _case(tmp_path, S70_70, sessions=VERIFIED)
    axis = _arena(tmp_path).axes["readiness_gap"]
    assert axis.score is not None and axis.score > 0.2
    assert axis.raw["readiness_shortfall"] == pytest.approx(15 / 85)
    _case(tmp_path / "waived", {**S90_50, "outcome_gate_waived": True}, sessions=VERIFIED)
    waived = _arena(tmp_path / "waived").axes["readiness_gap"]
    assert waived.raw["outcome_shortfall"] == 0.0
    assert waived.score == pytest.approx(0.2)

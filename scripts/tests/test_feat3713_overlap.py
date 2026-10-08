"""Selected sprint/issue overlap annotation (FEAT-3713 step 4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from little_loops.next_arena.candidates import assess_candidates, candidates_from_assessments
from little_loops.next_arena.selection import bucket_order_for, select_candidates
from tests.sprint_support import SETTINGS, bug, build, feat, ready, sprint_state, write_sprint


def selected(root: Path, *, top: int | None, types: list[str] | None = None) -> list[Any]:
    state = sprint_state(root)
    cands = candidates_from_assessments(assess_candidates(state, settings=SETTINGS))
    return select_candidates(
        cands, top=top, bucket_order=bucket_order_for(types), caps=dict(SETTINGS.caps)
    )


def project(tmp_path: Path) -> Path:
    root = build(
        tmp_path / "p",
        {
            feat(1, prio="P0"): ready(),
            bug(2, prio="P1"): ready(),
            bug(3, prio="P3"): ready(),
            feat(4): ready({"status": "done"}),
        },
        {},
    )
    write_sprint(root, "alpha", ["FEAT-001", "BUG-002", "FEAT-004"])
    write_sprint(root, "gamma", ["BUG-003"])
    return root


def overlaps(items: list[Any]) -> dict[str, list[dict[str, str]]]:
    return {c.target_key: c.evidence.get("selected_overlap", []) for c in items}


def test_selected_sprint_and_member_actions_are_annotated_as_alternatives(tmp_path: Path) -> None:
    root = project(tmp_path)
    items = selected(root, top=6)
    got = overlaps(items)
    sprint = got["sprint:alpha"]
    assert {e["target_key"] for e in sprint} == {"issue:FEAT-001", "issue:BUG-002"}
    for entry in sprint:
        assert set(entry) == {"target_key", "action_type", "display_command"}
        assert entry["display_command"].startswith("/ll:")
    # both sides: every selected issue action lists the selected sprint counterpart
    for key in ("issue:FEAT-001", "issue:BUG-002"):
        assert got[key] == [
            {
                "target_key": "sprint:alpha",
                "action_type": "run-sprint",
                "display_command": "ll-sprint run -- alpha",
            }
        ]
    # the second sprint pairs with its own member only
    assert [e["target_key"] for e in got["sprint:gamma"]] == ["issue:BUG-003"]
    assert [e["target_key"] for e in got["issue:BUG-003"]] == ["sprint:gamma"]


def test_terminal_members_never_create_overlap(tmp_path: Path) -> None:
    root = project(tmp_path)
    items = selected(root, top=8)
    targets = {e["target_key"] for e in overlaps(items)["sprint:alpha"]}
    assert "issue:FEAT-004" not in targets  # done member: remaining (nonterminal) only


def test_overlap_depends_on_the_selected_set(tmp_path: Path) -> None:
    root = project(tmp_path)
    only_sprints = selected(root, top=4, types=["run-sprint"])
    assert all("selected_overlap" not in c.evidence for c in only_sprints)
    only_issues = selected(root, top=4, types=["implement-issue"])
    assert all("selected_overlap" not in c.evidence for c in only_issues)
    # selecting one of the member issues alongside the sprint annotates just that pair
    one = selected(root, top=None, types=["implement-issue", "run-sprint"])
    assert {c.target_key for c in one} == {"issue:FEAT-001", "sprint:alpha"}
    pair = overlaps(one)
    assert pair["sprint:alpha"] and pair["issue:FEAT-001"]


def test_annotation_is_deterministic_and_does_not_touch_alternates(tmp_path: Path) -> None:
    root = project(tmp_path)
    first, second = selected(root, top=6), selected(root, top=6)
    assert [c.to_dict() for c in first] == [c.to_dict() for c in second]
    for cand in first:
        assert all(a.action_type != "run-sprint" for a in cand.alternates)  # not an Alternate
    json.dumps([c.to_dict() for c in first], allow_nan=False)


def test_text_output_renders_one_overlap_line_per_annotated_recommendation(
    tmp_path: Path,
) -> None:
    from little_loops.next_arena.render import render_text

    root = project(tmp_path)
    items = selected(root, top=6)
    text = render_text(
        project_root=root, recommendations=items, bucket_order=bucket_order_for(None)
    )
    lines = [ln for ln in text.splitlines() if "overlaps (alternative choices" in ln]
    annotated = [c for c in items if c.evidence.get("selected_overlap")]
    assert len(lines) == len(annotated) >= 3
    assert all("not a bundle" in ln for ln in lines)

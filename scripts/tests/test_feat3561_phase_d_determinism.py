"""Determinism and mixed-bucket behavior of the assessment/selection pipeline (FEAT-3561 D)."""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path
from typing import Any

from little_loops.next_arena.candidates import assess_candidates, generate_candidates
from little_loops.next_arena.selection import select_candidates
from tests.next_arena_candidates_support import (
    FORMAT_ENTRY,
    VERIFY_ENTRY,
    get,
    issue,
    project,
    ready_issue,
)
from tests.next_arena_support import make_project, memory_state

IMPL = "implement-issue"
REFINE = "refine-issue"
ORDER = (IMPL, REFINE)


def _files() -> dict[str, str]:
    session = [FORMAT_ENTRY, VERIFY_ENTRY, ("/ll:refine-issue", "2026-10-05T09:00:00")]
    return {
        "bugs/P0-BUG-001-a.md": ready_issue(sessions=session),
        "bugs/P2-BUG-002-b.md": issue(
            {"confidence_score": 70, "outcome_confidence": 70}, sessions=session
        ),
        "features/P1-FEAT-003-c.md": ready_issue(
            {"blocked_by": ["BUG-001"], "captured_at": "2026-09-01"}
        ),
        "features/P3-FEAT-004-d.md": ready_issue({"decision_needed": True}),
        "enhancements/P2-ENH-005-e.md": issue({"status": "deferred"}),
        "enhancements/P4-ENH-006-f.md": ready_issue(effort="Large"),
        "epics/P1-EPIC-007-g.md": issue({"status": "open"}),
        "bugs/P2-BUG-008-h.md": ready_issue(),
        "bugs/P2-BUG-008-i.md": ready_issue(),
        "bugs/notes.md": issue({"status": "open", "blocks": ["BUG-006"]}),
    }


def _dump(state: Any) -> str:
    assessments = [a.to_dict() for a in assess_candidates(state)]
    selected = select_candidates(
        generate_candidates(state), top=6, bucket_order=ORDER, caps={IMPL: 3, REFINE: 3}
    )
    return json.dumps(
        {"assessments": assessments, "selected": [c.to_dict() for c in selected]},
        sort_keys=False,
        allow_nan=False,
    )


def test_shuffled_source_order_with_fixed_clock_is_identical(tmp_path: Path) -> None:
    files = _files()
    baseline = _dump(project(tmp_path, files))
    rng = random.Random(3)
    for _ in range(5):
        shutil.rmtree(tmp_path / ".issues")
        order = list(files)
        rng.shuffle(order)
        assert _dump(project(tmp_path, files, order=order)) == baseline


def test_in_memory_snapshots_are_identical_regardless_of_dict_order(tmp_path: Path) -> None:
    make_project(tmp_path)
    files = _files()
    rng = random.Random(11)
    baseline = _dump(memory_state(tmp_path, files))
    for _ in range(5):
        shuffled = list(files.items())
        rng.shuffle(shuffled)
        assert _dump(memory_state(tmp_path, dict(shuffled))) == baseline


def test_repeated_assessment_of_one_snapshot_is_identical(tmp_path: Path) -> None:
    state = project(tmp_path, _files())
    assert _dump(state) == _dump(state)


def test_reordered_config_objects_produce_identical_output(tmp_path: Path) -> None:
    forward = {
        "next": {
            "verbs": {
                "implement-issue": {
                    "cap": 3,
                    "weights": {
                        "priority": 0.4,
                        "outcome": 0.2,
                        "leverage": 0.2,
                        "effort": 0.1,
                        "momentum": 0.1,
                    },
                },
                "refine-issue": {
                    "refine_cap": 4,
                    "weights": {
                        "priority": 0.3,
                        "readiness_gap": 0.3,
                        "leverage": 0.1,
                        "staleness": 0.2,
                        "momentum": 0.1,
                    },
                },
            }
        },
        "commands": {"confidence_gate": {"readiness_threshold": 80, "outcome_threshold": 60}},
    }
    reordered = {
        "commands": {"confidence_gate": {"outcome_threshold": 60, "readiness_threshold": 80}},
        "next": {
            "verbs": {
                "refine-issue": {
                    "weights": {
                        "momentum": 0.1,
                        "staleness": 0.2,
                        "leverage": 0.1,
                        "readiness_gap": 0.3,
                        "priority": 0.3,
                    },
                    "refine_cap": 4,
                },
                "implement-issue": {
                    "weights": {
                        "momentum": 0.1,
                        "effort": 0.1,
                        "leverage": 0.2,
                        "outcome": 0.2,
                        "priority": 0.4,
                    },
                    "cap": 3,
                },
            }
        },
    }
    files = _files()
    a = project(tmp_path / "a", files, config=forward)
    b = project(tmp_path / "b", files, config=reordered)
    left = [x.to_dict() for x in assess_candidates(a)]
    right = [x.to_dict() for x in assess_candidates(b)]
    scrub = lambda items: json.loads(  # noqa: E731
        json.dumps(items)
        .replace(str((tmp_path / "a").resolve()), "R")
        .replace(str((tmp_path / "b").resolve()), "R")
    )
    assert scrub(left) == scrub(right)
    for item in left:
        assert list(item["axes"]) == list(
            ("priority", "outcome", "leverage", "effort", "momentum")
            if item["action_type"] == IMPL
            else ("priority", "readiness_gap", "leverage", "staleness", "momentum")
        )


def test_assessment_depends_only_on_the_captured_state(tmp_path: Path) -> None:
    state = project(tmp_path, _files())
    first = _dump(state)
    for rel in list((tmp_path / ".issues").rglob("*.md")):
        rel.write_text("---\nstatus: done\n---\n")
    assert _dump(state) == first


# ----------------------------------------------------------------------- mixed buckets


def test_mixed_bucket_cold_start_one_verb_scored_one_cold(tmp_path: Path) -> None:
    """implement-issue has numeric utility; refine-issue's candidate is cold start."""
    config = {
        "next": {
            "verbs": {
                "refine-issue": {
                    "weights": {"readiness_gap": 0, "leverage": 0, "staleness": 0, "momentum": 0}
                }
            }
        }
    }
    files = {
        "bugs/P1-BUG-001-a.md": ready_issue(),
        "bugs/P2-BUG-002-b.md": ready_issue(),
    }
    state = project(tmp_path, files, config=config)
    assessments = assess_candidates(state)
    impl = get(assessments, IMPL, "BUG-001")
    refine = get(assessments, REFINE, "BUG-001")
    assert impl.utility is not None and impl.bucket_rank == 1
    assert refine.eligible and refine.utility is None and refine.selection_score is None
    assert refine.bucket_rank is not None and refine.cold_start
    candidates = generate_candidates(state)
    selected = select_candidates(candidates, top=None, bucket_order=ORDER, caps={})
    # one pass: the scored implement bucket and the cold-start refine bucket both appear
    assert [(c.action_type, c.target) for c in selected] == [(IMPL, "BUG-001"), (REFINE, "BUG-002")]
    assert selected[1].utility is None and selected[1].selection_score is None


def test_cold_start_candidates_sort_after_scored_ones_within_a_verb(tmp_path: Path) -> None:
    files = {
        "bugs/BUG-001-nopriority.md": ready_issue(),
        "bugs/P5-BUG-002-lowest.md": ready_issue(),
        "bugs/P0-BUG-003-top.md": ready_issue(),
    }
    items = [a for a in assess_candidates(project(tmp_path, files)) if a.action_type == IMPL]
    ranked = sorted(items, key=lambda a: a.bucket_rank or 0)
    assert [a.target for a in ranked] == ["BUG-003", "BUG-002", "BUG-001"]
    assert [a.utility is None for a in ranked] == [False, False, True]

"""Mapping-valued relationship metadata fails closed in the ``ll-next`` arena (BUG-3772)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.next_arena.blockers import build_blocker_index
from little_loops.next_arena.candidates import assess_candidates
from little_loops.next_arena.graph import (
    REASON_UNSUPPORTED_SHAPE,
    UNSUPPORTED_RAW_EXCERPT_LIMIT,
)
from little_loops.next_arena.state import ProjectState
from tests.next_arena_candidates_support import body, get, project
from tests.next_arena_support import record

IMPL = "implement-issue"
REFINE = "refine-issue"
SCORES = "confidence_score: 90\noutcome_confidence: 80\n"


def _text(extra_fm: str = "", status: str = "open", text_body: str | None = None) -> str:
    return f"---\nstatus: {status}\n{SCORES}{extra_fm}---\n\n" + (text_body or body())


def _mapping(field: str, *keys: str, value: str = "ignored") -> str:
    return f"{field}:\n" + "".join(f'  "{key}": {value}\n' for key in keys)


def _unresolved(item):  # type: ignore[no-untyped-def]
    return item.evidence["dependencies"]["unresolved"]


# ---------------------------------------------------------------------------- capture


@pytest.mark.parametrize("field", ["blocked_by", "depends_on", "blocks"])
def test_nonempty_mapping_is_captured_with_exact_keys(tmp_path: Path, field: str) -> None:
    files = {"features/P3-FEAT-001-a.md": _text(_mapping(field, " FEAT-002 ", "FEAT-2", "2"))}
    state = project(tmp_path, files)
    rec = record(state, "features/P3-FEAT-001-a.md")
    (fact,) = rec.unsupported_relationships
    assert fact.field == field
    assert fact.keys == (" FEAT-002 ", "FEAT-2", "2")
    assert "FEAT-2" in fact.raw and "\n" not in fact.raw
    assert getattr(rec, field) == ()


def test_empty_mapping_keeps_body_fallback(tmp_path: Path) -> None:
    extra = "blocked_by: {}\n"
    text_body = body(extra="## Blocked By\n\n- FEAT-002\n")
    files = {
        "features/P3-FEAT-001-a.md": _text(extra, text_body=text_body),
        "features/P3-FEAT-002-b.md": _text(),
    }
    rec = record(project(tmp_path, files), "features/P3-FEAT-001-a.md")
    assert rec.unsupported_relationships == ()
    assert rec.blocked_by == ("FEAT-002",)


def test_nonempty_mapping_suppresses_body_fallback_even_when_terminal(tmp_path: Path) -> None:
    text_body = body(extra="## Blocked By\n\n- FEAT-002\n")
    files = {
        "features/P3-FEAT-001-a.md": _text(
            _mapping("blocked_by", "FEAT-003"), status="done", text_body=text_body
        ),
    }
    rec = record(project(tmp_path, files), "features/P3-FEAT-001-a.md")
    assert rec.blocked_by == ()
    assert [f.field for f in rec.unsupported_relationships] == ["blocked_by"]


# ------------------------------------------------------------------------- assessment


@pytest.mark.parametrize("field", ["blocked_by", "depends_on"])
def test_own_field_mapping_excludes_implementation_but_not_refinement(
    tmp_path: Path, field: str
) -> None:
    files = {
        "features/P3-FEAT-001-a.md": _text(_mapping(field, "FEAT-002")),
        "features/P3-FEAT-002-b.md": _text(status="done"),
    }
    assessments = assess_candidates(project(tmp_path, files))
    item = get(assessments, IMPL, "FEAT-001")
    assert item.eligible is False
    assert item.gates["prerequisites"].status == "fail"
    (entry,) = _unresolved(item)
    assert entry["reason"] == REASON_UNSUPPORTED_SHAPE
    assert entry["kind"] == field
    assert entry["prerequisite_id"] is None
    assert entry["source_paths"] == [".issues/features/P3-FEAT-001-a.md"]
    assert "FEAT-002" in entry["raw_excerpt"]
    assert entry["raw_truncated"] is False
    assert "prerequisites" not in get(assessments, REFINE, "FEAT-001").gates
    assert get(assessments, IMPL, "FEAT-002") is not None


def test_mutual_mapping_keys_are_excluded_without_an_invented_cycle(tmp_path: Path) -> None:
    files = {
        "features/P3-FEAT-001-a.md": _text(_mapping("depends_on", "FEAT-002")),
        "features/P3-FEAT-002-b.md": _text(_mapping("depends_on", "FEAT-001")),
    }
    state = project(tmp_path, files)
    for issue_id in ("FEAT-001", "FEAT-002"):
        item = get(assess_candidates(state), IMPL, issue_id)
        assert item.eligible is False
        assert item.evidence["dependencies"]["in_cycle"] is False
    assert not any(d.code == "dependency_cycle" for d in state.diagnostics)
    assert state.graph.depends_on["FEAT-001"] == ()


def test_outside_blocks_mapping_excludes_exact_named_targets_only(tmp_path: Path) -> None:
    files = {
        "features/P3-FEAT-001-a.md": _text(),
        "features/P3-FEAT-002-b.md": _text(),
        "features/P3-FEAT-003-c.md": _text(),
        "features/P3-FEAT-004-d.md": _text(_mapping("blocks", "FEAT-001", "FEAT-2", "FEAT-404")),
    }
    state = project(tmp_path, files)
    assessments = assess_candidates(state)
    hit = get(assessments, IMPL, "FEAT-001")
    assert hit.eligible is False
    (entry,) = _unresolved(hit)
    assert entry["kind"] == "blocks"
    assert entry["reason"] == REASON_UNSUPPORTED_SHAPE
    assert entry["source_paths"] == [".issues/features/P3-FEAT-004-d.md"]
    for other in ("FEAT-002", "FEAT-003", "FEAT-004"):
        assert get(assessments, IMPL, other).eligible is True
    assert state.graph.dangling_blocks == {}


def test_only_the_declared_field_is_reported_on_a_multi_field_source(tmp_path: Path) -> None:
    files = {
        "features/P3-FEAT-001-a.md": _text(),
        "features/P3-FEAT-004-d.md": _text(
            _mapping("blocks", "FEAT-001") + _mapping("depends_on", "FEAT-009")
        ),
    }
    assessments = assess_candidates(project(tmp_path, files))
    (entry,) = _unresolved(get(assessments, IMPL, "FEAT-001"))
    assert entry["kind"] == "blocks"
    assert "FEAT-009" not in entry["raw_excerpt"]


def test_uniquely_terminal_and_anonymous_terminal_blocks_do_not_exclude(tmp_path: Path) -> None:
    files = {
        "features/P3-FEAT-001-a.md": _text(),
        "features/P3-FEAT-004-d.md": _text(_mapping("blocks", "FEAT-001"), status="done"),
        "features/notes-anon.md": _text(_mapping("blocks", "FEAT-001"), status="cancelled"),
    }
    state = project(tmp_path, files)
    assert get(assess_candidates(state), IMPL, "FEAT-001").eligible is True
    assert not any(d.code == "unsupported_dependency_shape" for d in state.diagnostics)


def test_nonterminal_anonymous_blocks_mapping_excludes_target(tmp_path: Path) -> None:
    files = {
        "features/P3-FEAT-001-a.md": _text(),
        "features/notes-anon.md": _text(_mapping("blocks", "FEAT-001")),
    }
    state = project(tmp_path, files)
    assert get(assess_candidates(state), IMPL, "FEAT-001").eligible is False
    diag = [d for d in state.diagnostics if d.code == "unsupported_dependency_shape"]
    assert len(diag) == 1 and diag[0].subject is None


@pytest.mark.parametrize("status", ["deferred", "in_progress", "blocked", "bogus"])
def test_nonterminal_sources_still_exclude(tmp_path: Path, status: str) -> None:
    files = {
        "features/P3-FEAT-001-a.md": _text(),
        "features/P3-FEAT-004-d.md": _text(_mapping("blocks", "FEAT-001"), status=status),
    }
    assert get(assess_candidates(project(tmp_path, files)), IMPL, "FEAT-001").eligible is False


def test_terminal_duplicate_cannot_launder_an_ambiguous_blocks_mapping(tmp_path: Path) -> None:
    files = {
        "bugs/P2-BUG-010-open.md": _text(),
        "bugs/P3-BUG-010-done.md": _text(_mapping("blocks", "FEAT-020"), status="done"),
        "features/P3-FEAT-020-t.md": _text(),
    }
    state = project(tmp_path, files)
    item = get(assess_candidates(state), IMPL, "FEAT-020")
    assert item.eligible is False
    assert any(e["reason"] == REASON_UNSUPPORTED_SHAPE for e in _unresolved(item))
    assert any(d.code == "unsupported_dependency_shape" for d in state.diagnostics)


def test_supported_relationships_are_unchanged(tmp_path: Path) -> None:
    files = {
        "features/P3-FEAT-001-a.md": _text("blocked_by:\n- FEAT-002\n"),
        "features/P3-FEAT-002-b.md": _text(status="done"),
    }
    assert get(assess_candidates(project(tmp_path, files)), IMPL, "FEAT-001").eligible is True


# --------------------------------------------------------------------------- diagnostics


def test_live_source_gets_a_bounded_diagnostic_and_full_raw_is_kept(tmp_path: Path) -> None:
    long_value = "x" * 2000
    files = {
        "features/P3-FEAT-001-a.md": _text(_mapping("blocked_by", "FEAT-002", value=long_value)),
    }
    state = project(tmp_path, files)
    rec = record(state, "features/P3-FEAT-001-a.md")
    assert len(rec.unsupported_relationships[0].raw) > UNSUPPORTED_RAW_EXCERPT_LIMIT
    (diag,) = [d for d in state.diagnostics if d.code == "unsupported_dependency_shape"]
    assert diag.subject == "FEAT-001"
    assert diag.paths == (".issues/features/P3-FEAT-001-a.md",)
    assert "blocked_by" in diag.message and "truncated" in diag.message
    assert len(diag.message) < 2 * UNSUPPORTED_RAW_EXCERPT_LIMIT
    item = get(assess_candidates(state), IMPL, "FEAT-001")
    (entry,) = _unresolved(item)
    assert entry["raw_truncated"] is True
    assert len(entry["raw_excerpt"]) <= UNSUPPORTED_RAW_EXCERPT_LIMIT
    reason = item.gates["prerequisites"].reason
    assert "blocked_by" in reason and "truncated" in reason
    assert len(reason) < 2 * UNSUPPORTED_RAW_EXCERPT_LIMIT


def test_wide_blocks_mapping_does_not_repeat_the_full_raw_per_target(tmp_path: Path) -> None:
    keys = [f"FEAT-{n:03d}" for n in range(10, 40)]
    files = {"features/P3-FEAT-001-src.md": _text(_mapping("blocks", *keys, value="y" * 100))}
    for key in keys:
        files[f"features/P3-{key}-t.md"] = _text()
    assessments = assess_candidates(project(tmp_path, files))
    for key in keys:
        (entry,) = _unresolved(get(assessments, IMPL, key))
        assert len(entry["raw_excerpt"]) <= UNSUPPORTED_RAW_EXCERPT_LIMIT
        assert entry["raw_truncated"] is True


def test_assessment_is_independent_of_source_order(tmp_path: Path) -> None:
    files = {
        "features/P3-FEAT-001-a.md": _text(_mapping("depends_on", "FEAT-002")),
        "features/P3-FEAT-002-b.md": _text(_mapping("blocks", "FEAT-001")),
        "features/notes-anon.md": _text(_mapping("blocks", "FEAT-002")),
    }
    fwd = project(tmp_path / "fwd", files)
    rev = project(tmp_path / "rev", files, order=list(reversed(list(files))))

    def snap(state: ProjectState, root: Path) -> str:
        payload = {
            "assessments": [a.to_dict() for a in assess_candidates(state)],
            "diagnostics": [d.to_dict() for d in state.diagnostics],
        }
        return json.dumps(payload, sort_keys=True).replace(str(root), "ROOT")

    assert snap(fwd, tmp_path / "fwd") == snap(rev, tmp_path / "rev")


# ----------------------------------------------------------------------------- blockers


def test_mixed_supported_and_unsupported_prerequisites_are_multi_blocked(tmp_path: Path) -> None:
    files = {
        "features/P3-FEAT-001-a.md": _text(
            "blocked_by:\n- FEAT-002\n" + _mapping("depends_on", "X")
        ),
        "features/P3-FEAT-002-b.md": _text(),
    }
    index = build_blocker_index(project(tmp_path, files))
    assert index.immediate.get("FEAT-002", ()) == ()
    assert index.direct.get("FEAT-002") == ("FEAT-001",)


def test_unsupported_only_evidence_creates_no_named_root(tmp_path: Path) -> None:
    files = {
        "features/P3-FEAT-001-a.md": _text(_mapping("blocked_by", "FEAT-002")),
        "features/P3-FEAT-002-b.md": _text(),
    }
    index = build_blocker_index(project(tmp_path, files))
    assert dict(index.direct) == {} and dict(index.immediate) == {}

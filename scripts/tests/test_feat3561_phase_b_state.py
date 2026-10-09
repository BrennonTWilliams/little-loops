"""ProjectState collection: lifecycle, priority, edges, captured raw fields, purity (FEAT-3561 B)."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from little_loops.issue_parser import IssueParser
from little_loops.next_arena import state as state_mod
from little_loops.next_arena.state import (
    build_source_record,
    collect_project_state,
    infer_parser_id,
    resolve_lifecycle,
)
from tests.next_arena_support import (
    AS_OF,
    collect,
    make_project,
    record,
    write_issue,
)

# --------------------------------------------------------------------------- lifecycle

LIFECYCLE_MATRIX = [
    # (frontmatter, status, provenance, has_conflict)
    ({}, "open", "default", False),
    ({"completed_at": "2026-01-01"}, "done", "legacy_completed_at", False),
    ({"status": "open"}, "open", "frontmatter", False),
    ({"status": "open", "completed_at": "2026-01-01"}, "open", "frontmatter", True),
    ({"status": "in_progress", "completed_at": "2026-01-01"}, "in_progress", "frontmatter", True),
    ({"status": "deferred"}, "deferred", "frontmatter", False),
    ({"status": "blocked"}, "blocked", "frontmatter", False),
    ({"status": "done"}, "done", "frontmatter", False),
    ({"status": "done", "completed_at": "2026-01-01"}, "done", "frontmatter", False),
    ({"status": "cancelled"}, "cancelled", "frontmatter", False),
    # shared parser synonym canonicalization
    ({"status": "complete"}, "done", "frontmatter", False),
    ({"status": "completed"}, "done", "frontmatter", False),
    ({"status": "wip"}, "in_progress", "frontmatter", False),
    ({"status": "pending"}, "open", "frontmatter", False),
    # blank explicit status is absence
    ({"status": None, "completed_at": "2026-01-01"}, "done", "legacy_completed_at", False),
    # invalid explicit status is never rescued by completed_at
    ({"status": "bogus", "completed_at": "2026-01-01"}, "invalid", "invalid", False),
    ({"status": "Done"}, "invalid", "invalid", False),
    ({"status": "superseded"}, "invalid", "invalid", False),
]


@pytest.mark.parametrize(("frontmatter", "status", "provenance", "conflict"), LIFECYCLE_MATRIX)
def test_lifecycle_matrix_on_disk(
    tmp_path: Path, frontmatter: dict[str, Any], status: str, provenance: str, conflict: bool
) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-001-x.md", frontmatter)
    rec = record(collect(tmp_path), "bugs/P3-BUG-001-x.md")
    assert (rec.lifecycle_status, rec.status_provenance) == (status, provenance)
    assert (rec.conflicting_completed_at is not None) is conflict
    codes = {d.code for d in rec.diagnostics}
    assert ("conflicting_completed_at" in codes) is conflict
    assert ("invalid_status" in codes) is (status == "invalid")


def test_resolve_lifecycle_is_pure_over_frontmatter() -> None:
    life = resolve_lifecycle({"status": "open", "completed_at": "x"})
    assert (life.status, life.provenance, life.conflicting_completed_at) == (
        "open",
        "frontmatter",
        "x",
    )


def test_reopened_issue_does_not_use_issueinfo_status(tmp_path: Path) -> None:
    """The parser's IssueInfo.status says done for open+completed_at; the arena says open."""
    make_project(tmp_path)
    path = write_issue(
        tmp_path, "bugs/P3-BUG-001-x.md", {"status": "open", "completed_at": "2026-01-01"}
    )
    state = collect(tmp_path)
    assert IssueParser(state.config).parse_file(path).status == "done"
    assert record(state, "bugs/P3-BUG-001-x.md").lifecycle_status == "open"


# ---------------------------------------------------------------------------- priority


def test_priority_filename_over_frontmatter_with_disagreement(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P1-BUG-001-x.md", {"priority": "P4"})
    state = collect(tmp_path)
    rec = record(state, "bugs/P1-BUG-001-x.md")
    assert (rec.priority, rec.priority_int, rec.priority_source) == ("P1", 1, "filename")
    assert rec.priority_conflict == ("P1", "P4")
    assert any(d.code == "priority_disagreement" for d in state.diagnostics)


def test_priority_frontmatter_fallback_for_unprefixed_anchored_name(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/BUG-002-x.md", {"priority": "p2"})
    rec = record(collect(tmp_path), "bugs/BUG-002-x.md")
    assert (rec.priority, rec.priority_source, rec.priority_conflict) == ("P2", "frontmatter", None)


@pytest.mark.parametrize("frontmatter", [{}, {"priority": "P9"}, {"priority": ""}, {"priority": 3}])
def test_missing_or_invalid_priority_stays_missing_not_p5(
    tmp_path: Path, frontmatter: dict[str, Any]
) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/BUG-003-x.md", frontmatter)
    state = collect(tmp_path)
    rec = record(state, "bugs/BUG-003-x.md")
    assert (rec.priority, rec.priority_int, rec.priority_source) == (None, None, None)
    # the shared parser would substitute the lowest configured priority
    parsed = IssueParser(state.config).parse_file(rec.path)
    assert parsed.priority == "P5"


# ------------------------------------------------------------------- edges and raw fields


def test_edges_from_frontmatter_and_body_sections(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(
        tmp_path,
        "features/P3-FEAT-010-a.md",
        {"blocked_by": ["BUG-001"], "depends_on": ["FEAT-002", "FEAT-003"]},
        "# T\n\n## Blocks\n\n- FEAT-020\n- **ENH-021**: note\n",
    )
    write_issue(
        tmp_path,
        "features/P3-FEAT-011-b.md",
        None,
        "# T\n\n## Blocked By\n\n- BUG-005\n\n## Blocks\n\n- FEAT-030\n",
    )
    state = collect(tmp_path)
    a = record(state, "features/P3-FEAT-010-a.md")
    assert a.blocked_by == ("BUG-001",)
    assert a.depends_on == ("FEAT-002", "FEAT-003")
    assert a.blocks == ("FEAT-020", "ENH-021")
    b = record(state, "features/P3-FEAT-011-b.md")
    assert (b.blocked_by, b.blocks) == (("BUG-005",), ("FEAT-030",))


def test_frontmatter_edges_win_over_conflicting_body_like_parser(tmp_path: Path) -> None:
    make_project(tmp_path)
    path = write_issue(
        tmp_path,
        "bugs/P3-BUG-001-x.md",
        {"blocked_by": ["BUG-100"]},
        "# T\n\n## Blocked By\n\n- BUG-200\n",
    )
    state = collect(tmp_path)
    assert record(state, "bugs/P3-BUG-001-x.md").blocked_by == ("BUG-100",)
    assert IssueParser(state.config).parse_file(path).blocked_by == ["BUG-100"]


def test_raw_score_and_flag_fields_are_kept_raw(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(
        tmp_path,
        "bugs/P3-BUG-001-x.md",
        {
            "confidence_score": "101",
            "outcome_confidence": "abc",
            "outcome_gate_waived": "TRUE",
            "decision_needed": "True",
            "captured_at": "2026-09-30",
            "discovered_date": "2026-09-01",
        },
    )
    write_issue(
        tmp_path,
        "bugs/P3-BUG-002-x.md",
        {"outcome_gate_waived": "yes", "decision_needed": "1", "confidence_score": 85},
    )
    write_issue(tmp_path, "bugs/P3-BUG-003-x.md", {})
    state = collect(tmp_path)
    one = record(state, "bugs/P3-BUG-001-x.md")
    assert (one.confidence_score_raw, one.outcome_confidence_raw) == ("101", "abc")
    assert (one.outcome_gate_waived_raw, one.outcome_gate_waived) == ("TRUE", True)
    assert (one.decision_needed_raw, one.decision_needed) == ("True", True)
    assert (one.captured_at_raw, one.discovered_date_raw) == ("2026-09-30", "2026-09-01")
    two = record(state, "bugs/P3-BUG-002-x.md")
    assert (two.outcome_gate_waived, two.decision_needed) == (False, False)
    assert two.confidence_score_raw == "85"
    three = record(state, "bugs/P3-BUG-003-x.md")
    assert three.confidence_score_raw is None and three.outcome_confidence_raw is None
    assert three.captured_at_raw is None


def test_session_log_text_commands_and_type_flags(tmp_path: Path) -> None:
    make_project(tmp_path)
    log = (
        "# T\n\n## Session Log\n"
        "- `/ll:refine-issue` - 2026-10-01T10:00:00 - `a.jsonl`\n"
        "- `/ll:refine-issue` - 2026-10-02T10:00:00 - `b.jsonl`\n"
        "- `/ll:verify-issues` - 2026-10-03T10:00:00 - `c.jsonl`\n"
    )
    write_issue(tmp_path, "features/P3-FEAT-001-x.md", {"parent": "EPIC-9"}, log)
    write_issue(tmp_path, "epics/P3-EPIC-009-e.md", {})
    state = collect(tmp_path)
    rec = record(state, "features/P3-FEAT-001-x.md")
    assert rec.session_log is not None and "verify-issues" in rec.session_log
    assert rec.session_commands == ("/ll:refine-issue", "/ll:verify-issues")
    assert dict(rec.session_command_counts) == {"/ll:refine-issue": 2, "/ll:verify-issues": 1}
    assert (rec.issue_type, rec.category, rec.from_category_dir, rec.in_legacy_dir) == (
        "FEAT",
        "features",
        True,
        False,
    )
    assert rec.parent == "EPIC-9"
    assert record(state, "epics/P3-EPIC-009-e.md").is_epic


# --------------------------------------------------------------- collection / enumeration


def test_collects_all_statuses_category_and_legacy_dirs_md_only_sorted(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-002-b.md", {"status": "done"})
    write_issue(tmp_path, "bugs/P3-BUG-001-a.md", {"status": "open"})
    write_issue(tmp_path, "features/P3-FEAT-003-c.md", {"status": "deferred"})
    write_issue(tmp_path, "bugs/notes.txt", text="not markdown")
    write_issue(tmp_path, "completed/P3-BUG-004-old.md", {"status": "done"})
    write_issue(tmp_path, "deferred/P3-BUG-005-old.md", {"status": "deferred"})
    (tmp_path / ".issues" / "bugs" / "subdir").mkdir()
    write_issue(tmp_path, "bugs/subdir/P3-BUG-006-nested.md", {})
    state = collect(tmp_path)
    paths = [r.rel_path for r in state.records]
    assert paths == sorted(paths)
    assert paths == [
        ".issues/bugs/P3-BUG-001-a.md",
        ".issues/bugs/P3-BUG-002-b.md",
        ".issues/completed/P3-BUG-004-old.md",
        ".issues/deferred/P3-BUG-005-old.md",
        ".issues/features/P3-FEAT-003-c.md",
    ]
    legacy = record(state, "completed/P3-BUG-004-old.md")
    assert (legacy.in_legacy_dir, legacy.from_category_dir, legacy.category) == (True, False, None)
    assert legacy.issue_id == "BUG-004" and legacy.filename_issue is None


def test_enumeration_order_does_not_change_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_project(tmp_path)
    for n in range(1, 6):
        write_issue(tmp_path, f"bugs/P3-BUG-00{n}-x.md", {"blocked_by": [f"BUG-00{n % 5 + 1}"]})
    write_issue(tmp_path, "features/P3-FEAT-010-x.md", {"blocks": ["BUG-001"]})
    base = collect(tmp_path)
    monkeypatch.setattr(state_mod, "_list_issue_files", lambda d: sorted(d.glob("*.md"))[::-1])
    reversed_state = collect(tmp_path)
    assert reversed_state.records == base.records
    assert reversed_state.identity == base.identity
    assert reversed_state.graph == base.graph
    assert reversed_state.diagnostics == base.diagnostics


def test_one_read_and_one_parse_per_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_project(tmp_path)
    for n in range(1, 5):
        write_issue(tmp_path, f"bugs/P3-BUG-00{n}-x.md", {"status": "open"})
    write_issue(tmp_path, "completed/P3-BUG-010-old.md", {"status": "done"})
    write_issue(tmp_path, "bugs/notes.md", {})

    reads: list[Path] = []
    parses: list[str] = []
    real_read, real_parse = state_mod._read_text, state_mod._parse_frontmatter

    def read(path: Path) -> str:
        reads.append(path)
        return real_read(path)

    def parse(content: str) -> dict[str, Any]:
        parses.append(content)
        return real_parse(content)

    monkeypatch.setattr(state_mod, "_read_text", read)
    monkeypatch.setattr(state_mod, "_parse_frontmatter", parse)
    state = collect(tmp_path)
    assert len(state.records) == 6
    assert sorted(reads) == sorted(r.path for r in state.records)
    assert len(set(reads)) == len(reads) == 6
    assert len(parses) == 6

    # downstream reads of the captured state perform no further I/O or parses
    reads.clear()
    parses.clear()
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("live file read"))
    from little_loops.next_arena.state import downstream_leverage, is_formatted_from_state

    for rec in state.records:
        is_formatted_from_state(rec, state.formatting_policy)
        if rec.issue_id:
            downstream_leverage(state, rec.issue_id)
    assert reads == [] and parses == []


def test_no_subprocess_no_writes_no_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-001-x.md", {"blocks": ["BUG-002"]})
    write_issue(tmp_path, "bugs/P3-BUG-002-x.md", {})

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("subprocess/process spawn during collection")

    for name in ("run", "Popen", "call", "check_call", "check_output", "getoutput"):
        monkeypatch.setattr(subprocess, name, boom)
    for name in ("system", "popen", "fork", "execv", "execvp", "posix_spawn"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, boom)

    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    mtimes = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}
    state = collect_project_state(tmp_path, as_of=AS_OF)  # builds its own BRConfig
    assert len(state.records) == 2
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == before
    assert mtimes == {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}


# ----------------------------------------------------------------------------- as_of


def test_as_of_defaults_to_aware_utc_and_rejects_naive(tmp_path: Path) -> None:
    make_project(tmp_path)
    state = collect_project_state(tmp_path)
    assert state.as_of.utcoffset() == timedelta(0)
    assert state.as_of.tzinfo is UTC
    with pytest.raises(ValueError, match="timezone-aware"):
        collect_project_state(tmp_path, as_of=datetime(2026, 10, 7, 12, 0))


def test_as_of_is_converted_to_utc_and_captured_once(tmp_path: Path) -> None:
    make_project(tmp_path)
    plus5 = timezone(timedelta(hours=5))
    state = collect_project_state(tmp_path, as_of=datetime(2026, 10, 7, 17, 0, tzinfo=plus5))
    assert state.as_of == datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    assert state.as_of.tzinfo is UTC


def test_injected_config_is_used_and_root_is_resolved(tmp_path: Path) -> None:
    from little_loops.config import BRConfig

    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-001-x.md", {})
    config = BRConfig(tmp_path)
    state = collect(tmp_path, config=config)
    assert state.config is config
    assert state.project_root == tmp_path.resolve()


# ---------------------------------------------------------------- thresholds / config


def test_thresholds_from_effective_merged_confidence_gate(tmp_path: Path) -> None:
    make_project(
        tmp_path,
        config={"commands": {"confidence_gate": {"readiness_threshold": 90, "enabled": True}}},
    )
    (tmp_path / ".ll" / "ll.local.md").write_text(
        "---\ncommands:\n  confidence_gate:\n    outcome_threshold: 40\n---\n", encoding="utf-8"
    )
    state = collect(tmp_path)
    assert (state.thresholds.readiness, state.thresholds.outcome) == (90, 40)
    assert state.thresholds.enabled is True
    assert state.config_errors == ()


def test_local_null_removes_threshold_back_to_default(tmp_path: Path) -> None:
    make_project(tmp_path, config={"commands": {"confidence_gate": {"readiness_threshold": 90}}})
    (tmp_path / ".ll" / "ll.local.md").write_text(
        "---\ncommands:\n  confidence_gate:\n    readiness_threshold: null\n---\n",
        encoding="utf-8",
    )
    state = collect(tmp_path)
    assert (state.thresholds.readiness, state.config_errors) == (85, ())


def test_default_thresholds_are_85_65(tmp_path: Path) -> None:
    make_project(tmp_path)
    state = collect(tmp_path)
    assert (state.thresholds.readiness, state.thresholds.outcome) == (85, 65)


@pytest.mark.parametrize("bad", [True, False, 101, -1, "85", 85.5, None, [85]])
def test_invalid_thresholds_become_captured_config_errors(tmp_path: Path, bad: Any) -> None:
    make_project(tmp_path, config={"commands": {"confidence_gate": {"readiness_threshold": bad}}})
    state = collect(tmp_path)
    assert state.thresholds.readiness is None
    assert state.thresholds.outcome == 65
    assert len(state.config_errors) == 1
    assert "readiness_threshold" in state.config_errors[0]


# ------------------------------------------------------- numberless / allocator bypass


def test_numberless_source_never_allocates_or_invents_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import little_loops.issue_parser as ip

    make_project(tmp_path)
    write_issue(tmp_path, "bugs/notes.md", {"status": "open", "blocks": ["FEAT-200"]})
    write_issue(tmp_path, "bugs/README.md", {})
    write_issue(tmp_path, "completed/old-notes.md", {"status": "done", "blocks": ["FEAT-201"]})
    write_issue(tmp_path, "features/P3-FEAT-200-target.md", {})
    write_issue(tmp_path, "features/P3-FEAT-201-other.md", {})
    write_issue(tmp_path, "features/P3-FEAT-202-independent.md", {})

    def raising(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("allocator or stem-ID fallback was used")

    monkeypatch.setattr(ip, "get_next_issue_number", raising)
    monkeypatch.setattr(IssueParser, "_generate_id_from_filename", raising)
    monkeypatch.setattr(IssueParser, "_parse_type_and_id", raising)
    monkeypatch.setattr(IssueParser, "parse_file", raising)

    state = collect(tmp_path)
    notes = record(state, "bugs/notes.md")
    assert notes.issue_id is None and notes.inferred_id is None and notes.filename_issue
    assert notes.content.startswith("---") and notes.lifecycle_status == "open"
    assert ".issues/bugs/notes.md" not in state.identity.node_ids
    assert not any(n for n in state.graph.node_status if "notes" in n.lower())
    diag = [
        d
        for d in state.diagnostics
        if d.code == "unsupported_issue_filename" and d.paths == (".issues/bugs/notes.md",)
    ]
    assert len(diag) == 1 and diag[0].subject is None

    # the nonterminal numberless source keeps unresolved prerequisite evidence on its target
    pending = state.graph.unresolved_for("FEAT-200")
    assert [(p.kind, p.prerequisite_id, p.reason) for p in pending] == [
        ("blocks", None, "unanchored_source")
    ]
    assert pending[0].source_paths == (".issues/bugs/notes.md",)
    assert not state.graph.prerequisites_satisfied("FEAT-200")
    # a known terminal numberless source creates no blocker; independent targets stay usable
    assert state.graph.prerequisites_satisfied("FEAT-201")
    assert state.graph.prerequisites_satisfied("FEAT-202")


def test_numberless_source_with_invalid_status_still_blocks(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/notes.md", {"status": "bogus", "blocks": ["FEAT-200"]})
    write_issue(tmp_path, "features/P3-FEAT-200-target.md", {})
    state = collect(tmp_path)
    assert record(state, "bugs/notes.md").lifecycle_status == "invalid"
    assert not state.graph.prerequisites_satisfied("FEAT-200")


# --------------------------------------------------------- unreadable sources fail closed


def test_unreadable_source_is_invalid_and_diagnosed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_project(tmp_path)
    write_issue(tmp_path, "bugs/P3-BUG-001-x.md", {"status": "done"})
    write_issue(tmp_path, "bugs/P3-BUG-002-x.md", {"blocked_by": ["BUG-001"]})
    real = state_mod._read_text

    def flaky(path: Path) -> str:
        if path.name.startswith("P3-BUG-001"):
            raise PermissionError("denied")
        return real(path)

    monkeypatch.setattr(state_mod, "_read_text", flaky)
    state = collect(tmp_path)
    rec = record(state, "bugs/P3-BUG-001-x.md")
    assert rec.read_error and rec.lifecycle_status == "invalid" and rec.content == ""
    assert any(d.code == "unreadable_source" for d in state.diagnostics)
    # an unreadable prerequisite never satisfies an edge
    assert not state.graph.prerequisites_satisfied("BUG-002")


# ----------------------------------------------- inferred-ID mirror parity with the parser


@pytest.mark.parametrize(
    ("dirname", "filename"),
    [
        ("bugs", "P3-BUG-001-new.md"),
        ("bugs", "P3-001-old.md"),
        ("bugs", "P0-12-old.md"),
        ("features", "feature-7-thing.md"),
        ("features", "P2-FEAT-100-fix-BUG-5-thing.md"),
        ("enhancements", "P3-ENH-3144-correct-epic-3127-tasks.md"),
        ("epics", "P1-EPIC-0003-x.md"),
        ("bugs", "p3-bug-001-lower.md"),
        ("bugs", "BUG-002.md"),
        ("completed", "P3-BUG-004-old.md"),
        ("completed", "P3-004-old.md"),
        ("bugs", "ENH-55-in-bugs-dir.md"),
    ],
)
def test_infer_parser_id_matches_real_parser_for_numbered_names(
    tmp_path: Path, dirname: str, filename: str
) -> None:
    from little_loops.config import BRConfig

    make_project(tmp_path)
    config = BRConfig(tmp_path)
    path = tmp_path / ".issues" / dirname / filename
    if dirname == "completed":
        # outside every category dir the real parser uses the stem as ID: the mirror
        # deliberately returns None there for numberless/uncategorized names
        real = IssueParser(config)._parse_type_and_id(filename, path)[1]
        mirror = infer_parser_id(filename, dirname, config)
        assert mirror is None or mirror == real
        return
    real = IssueParser(config)._parse_type_and_id(filename, path)[1]
    assert infer_parser_id(filename, dirname, config) == real


def test_infer_parser_id_returns_none_where_parser_would_allocate(tmp_path: Path) -> None:
    from little_loops.config import BRConfig

    make_project(tmp_path)
    config = BRConfig(tmp_path)
    assert infer_parser_id("notes.md", "bugs", config) is None
    assert infer_parser_id("README.md", "features", config) is None
    assert infer_parser_id("old-notes.md", "completed", config) is None


def test_build_source_record_needs_no_filesystem(tmp_path: Path) -> None:
    from little_loops.config import BRConfig

    config = BRConfig(tmp_path)
    rec = build_source_record(
        tmp_path / ".issues" / "bugs" / "P2-BUG-042-mem.md",
        "---\nstatus: blocked\npriority: P4\n---\n# BUG-042: In memory\n",
        project_root=tmp_path.resolve(),
        config=config,
    )
    assert (rec.issue_id, rec.lifecycle_status, rec.priority, rec.title) == (
        "BUG-042",
        "blocked",
        "P2",
        "In memory",
    )

"""BUG-3006: audit_issue_collisions() classifies retype vs number-reuse."""

from __future__ import annotations

from pathlib import Path

from little_loops.issue_history.collisions import audit_issue_collisions
from little_loops.session_store import record_issue_event, record_issue_snapshot


def test_number_reuse_classified_correctly(tmp_path: Path) -> None:
    """BUG-9001 (deleted, open) and EPIC-9001 (on disk, done) share issue_num=9001.

    Mirrors the live BUG-1978/EPIC-1978 repro: distinct transitions so both
    rows survive the dedup index (a same-transition pair would be silently
    discarded before the audit ever sees it — that's the bug this fix makes
    visible via the collision warning, not via this retrospective report).
    """
    issues_dir = tmp_path / ".issues"
    epics_dir = issues_dir / "epics"
    epics_dir.mkdir(parents=True, exist_ok=True)
    (epics_dir / "P2-EPIC-9001-second.md").write_text(
        "---\nid: EPIC-9001\ntype: EPIC\npriority: P2\nstatus: done\n"
        "title: Second\n---\n\n# Second\n",
        encoding="utf-8",
    )
    # BUG-9001 has no on-disk file — deleted/renumbered, matching the repro steps.

    db = tmp_path / ".ll" / "history.db"
    # BUG-9001 occupies the "done" slot first; EPIC-9001's later attempt to
    # record "done" would collide and get silently dropped by INSERT OR
    # IGNORE, leaving only its earlier "open" capture-time event on record —
    # exactly the live EPIC-1978 shape (on-disk status "done" with zero
    # recorded "done" rows).
    record_issue_event(db, "BUG-9001", "done")
    record_issue_event(db, "EPIC-9001", "open")

    groups = audit_issue_collisions(db, issues_dir)
    events_groups = [g for g in groups if g.table == "issue_events"]
    assert len(events_groups) == 1
    group = events_groups[0]
    assert group.issue_num == 9001
    assert group.classification == "number_reuse"
    ids = {e.issue_id for e in group.entries}
    assert ids == {"BUG-9001", "EPIC-9001"}
    on_disk = {e.issue_id: e.on_disk for e in group.entries}
    assert on_disk == {"BUG-9001": False, "EPIC-9001": True}


def test_retype_classified_correctly(tmp_path: Path) -> None:
    """ENH-2576 (deferred, no file) and FEAT-2576 (done, on disk) is a retype."""
    issues_dir = tmp_path / ".issues"
    features_dir = issues_dir / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    issue_file = features_dir / "P2-FEAT-2576-retyped.md"
    issue_file.write_text(
        "---\nid: FEAT-2576\ntype: FEAT\npriority: P2\nstatus: done\n"
        "title: Retyped\n---\n\n# Retyped\n",
        encoding="utf-8",
    )

    db = tmp_path / ".ll" / "history.db"
    record_issue_snapshot(db, "ENH-2576", "deferred", str(issue_file))
    record_issue_snapshot(db, "FEAT-2576", "done", str(issue_file))

    groups = audit_issue_collisions(db, issues_dir)
    snapshot_groups = [g for g in groups if g.table == "issue_snapshots"]
    assert len(snapshot_groups) == 1
    group = snapshot_groups[0]
    assert group.issue_num == 2576
    assert group.classification == "retype"


def test_no_collisions_returns_empty(tmp_path: Path) -> None:
    issues_dir = tmp_path / ".issues"
    db = tmp_path / ".ll" / "history.db"
    record_issue_event(db, "ENH-100", "done")

    assert audit_issue_collisions(db, issues_dir) == []

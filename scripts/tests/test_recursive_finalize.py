"""Tests for finalize_decomposed_parent (ENH-1977 Fix 4)."""

from __future__ import annotations

from pathlib import Path

from little_loops.frontmatter import parse_frontmatter
from little_loops.recursive_finalize import finalize_decomposed_parent


def _write(path: Path, fm: str, body: str = "Body.\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{fm}\n---\n\n{body}", encoding="utf-8")


def _make_tree(tmp_path: Path, *, epic: bool) -> Path:
    issues = tmp_path / ".issues"
    parent_fm = "id: ENH-200\ntype: ENH\nstatus: open"
    if epic:
        parent_fm += "\nparent: EPIC-100"
    _write(issues / "enhancements" / "P2-ENH-200-parent.md", parent_fm)
    _write(
        issues / "enhancements" / "P2-ENH-201-child-a.md",
        "id: ENH-201\ntype: ENH\nstatus: open\nparent: ENH-200",
        "## Parent Issue\nDecomposed from ENH-200: Parent\n",
    )
    _write(
        issues / "enhancements" / "P2-ENH-202-child-b.md",
        "id: ENH-202\ntype: ENH\nstatus: open\nparent: ENH-200",
        "## Parent Issue\nDecomposed from ENH-200: Parent\n",
    )
    if epic:
        _write(
            issues / "epics" / "P2-EPIC-100-theme.md",
            "id: EPIC-100\ntype: EPIC\nstatus: open\nrelates_to: [ENH-200]",
        )
    return issues


def test_parent_closed_and_moved(tmp_path: Path) -> None:
    """Parent is set done and moved to completed/ (no EPIC path)."""
    issues = _make_tree(tmp_path, epic=False)
    result = finalize_decomposed_parent("ENH-200", ["ENH-201", "ENH-202"], issues)

    assert result["epic"] is None
    assert result["moved"] is True
    moved = issues / "completed" / "P2-ENH-200-parent.md"
    assert moved.exists()
    fm = parse_frontmatter(moved.read_text())
    assert fm["status"] == "done"
    assert "completed_at" in fm
    assert "Decomposed into**: ENH-201, ENH-202" in moved.read_text()
    # Without an EPIC, children keep their original parent linkage.
    child = issues / "enhancements" / "P2-ENH-201-child-a.md"
    assert parse_frontmatter(child.read_text())["parent"] == "ENH-200"


def test_epic_relink(tmp_path: Path) -> None:
    """Children are repointed to the EPIC and lineage recorded via relates_to."""
    issues = _make_tree(tmp_path, epic=True)
    result = finalize_decomposed_parent("ENH-200", ["ENH-201", "ENH-202"], issues)

    assert result["epic"] == "EPIC-100"
    for cid in ("ENH-201", "ENH-202"):
        child = next(issues.rglob(f"*-{cid}-*.md"))
        cfm = parse_frontmatter(child.read_text())
        assert cfm["parent"] == "EPIC-100", f"{cid} should be repointed to the EPIC"
        assert "ENH-200" in cfm["relates_to"], f"{cid} should record lineage to parent"

    epic = next(issues.rglob("*-EPIC-100-*.md"))
    efm = parse_frontmatter(epic.read_text())
    assert "ENH-201" in efm["relates_to"]
    assert "ENH-202" in efm["relates_to"]
    # Decomposed parent is dropped from the EPIC membership list.
    assert "ENH-200" not in efm["relates_to"]


def test_idempotent(tmp_path: Path) -> None:
    """A second call does not duplicate notes or relates_to entries."""
    issues = _make_tree(tmp_path, epic=True)
    finalize_decomposed_parent("ENH-200", ["ENH-201", "ENH-202"], issues)
    # Second call: parent already in completed/, EPIC already linked.
    finalize_decomposed_parent("ENH-200", ["ENH-201", "ENH-202"], issues)

    moved = issues / "completed" / "P2-ENH-200-parent.md"
    assert moved.read_text().count("Decomposed into") == 1
    epic = next(issues.rglob("*-EPIC-100-*.md"))
    relates = parse_frontmatter(epic.read_text())["relates_to"]
    assert relates.count("ENH-201") == 1
    assert relates.count("ENH-202") == 1


def test_missing_parent_reports_warning(tmp_path: Path) -> None:
    """A missing parent yields a warning, not a crash."""
    issues = tmp_path / ".issues"
    issues.mkdir()
    result = finalize_decomposed_parent("ENH-999", ["ENH-201"], issues)
    assert result["moved"] is False
    assert any("parent file not found" in w for w in result["warnings"])


def test_cli_children_file_path(tmp_path: Path, capsys: object) -> None:
    """ENH-2615: cmd_finalize_decomposition reads child IDs from --children-file
    (the invocation shape autodev's enqueue_children/enqueue_or_skip use with
    the run_dir's autodev-new-children.txt artifact)."""
    import argparse

    from little_loops.cli.issues.finalize_decomposition import cmd_finalize_decomposition

    issues = _make_tree(tmp_path, epic=True)
    children_file = tmp_path / "autodev-new-children.txt"
    children_file.write_text("ENH-201\nENH-202\n")

    args = argparse.Namespace(
        parent="ENH-200",
        children=[],
        children_file=str(children_file),
        issues_dir=str(issues),
        no_move=False,
        config=tmp_path,
    )
    rc = cmd_finalize_decomposition(None, args)  # type: ignore[arg-type]  # config unused

    assert rc == 0
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "children=2" in out
    assert (issues / "completed" / "P2-ENH-200-parent.md").exists()
    for cid in ("ENH-201", "ENH-202"):
        child = next(issues.rglob(f"*-{cid}-*.md"))
        assert parse_frontmatter(child.read_text())["parent"] == "EPIC-100"

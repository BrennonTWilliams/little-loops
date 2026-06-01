"""CLI-level tests for ll-deps tree subcommand."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from little_loops.cli.deps import main_deps as main


def _setup_project(tmp_path: Path) -> Path:
    """Create minimal project structure and return issues_dir."""
    issues_dir = tmp_path / ".issues"
    for subdir in ("bugs", "features", "enhancements", "epics"):
        (issues_dir / subdir).mkdir(parents=True)
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir()
    (ll_dir / "ll-config.json").write_text('{"issues": {"base_dir": ".issues"}}')
    return issues_dir


def _write_issue(
    directory: Path,
    issue_id: str,
    priority: str = "P2",
    status: str = "open",
    title: str | None = None,
    parent: str | None = None,
    relates_to: list[str] | None = None,
    blocked_by: list[str] | None = None,
) -> Path:
    """Write a minimal issue .md file with YAML frontmatter."""
    slug = (title or issue_id).lower().replace(" ", "-")
    filename = f"{priority}-{issue_id}-{slug}.md"
    lines = ["---", f"status: {status}"]
    if parent:
        lines.append(f"parent: {parent}")
    if relates_to:
        lines.append("relates_to:")
        for ref in relates_to:
            lines.append(f"  - {ref}")
    if blocked_by:
        lines.append("blocked_by:")
        for ref in blocked_by:
            lines.append(f"  - {ref}")
    lines += ["---", "", f"# {issue_id}: {title or 'Test ' + issue_id}"]
    (directory / filename).write_text("\n".join(lines))
    return directory / filename


class TestDepsTree:
    """CLI-level tests for ll-deps tree subcommand."""

    def test_tree_epic_not_found(self, tmp_path: Path) -> None:
        """Missing EPIC returns exit code 1."""
        issues_dir = _setup_project(tmp_path)
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "tree", "--epic", "EPIC-999"]):
            result = main()
        assert result == 1

    def test_tree_no_children(self, tmp_path: Path, capsys: object) -> None:
        """EPIC with no children prints sentinel and exits 0."""
        issues_dir = _setup_project(tmp_path)
        _write_issue(issues_dir / "epics", "EPIC-001", title="Lonely epic")
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "tree", "--epic", "EPIC-001"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()  # type: ignore[union-attr]
        assert "no children" in captured.out

    def test_tree_linear_chain(self, tmp_path: Path, capsys: object) -> None:
        """EPIC with linear chain renders ├── and └── connectors."""
        issues_dir = _setup_project(tmp_path)
        _write_issue(
            issues_dir / "epics",
            "EPIC-001",
            title="My Epic",
            relates_to=["FEAT-001", "FEAT-002"],
        )
        _write_issue(issues_dir / "features", "FEAT-001", title="First")
        _write_issue(issues_dir / "features", "FEAT-002", title="Second", blocked_by=["FEAT-001"])
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "tree", "--epic", "EPIC-001"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()  # type: ignore[union-attr]
        assert "FEAT-001" in captured.out
        assert "FEAT-002" in captured.out
        assert "├── " in captured.out
        assert "└── " in captured.out

    def test_tree_backward_refs(self, tmp_path: Path, capsys: object) -> None:
        """Children declared via parent: field (backward refs) appear in tree."""
        issues_dir = _setup_project(tmp_path)
        _write_issue(issues_dir / "epics", "EPIC-001", title="Parent epic")
        _write_issue(issues_dir / "features", "FEAT-001", title="Child via parent", parent="EPIC-001")
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "tree", "--epic", "EPIC-001"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()  # type: ignore[union-attr]
        assert "FEAT-001" in captured.out

    def test_tree_done_children_included(self, tmp_path: Path, capsys: object) -> None:
        """Done children appear in the tree with [done] badge."""
        issues_dir = _setup_project(tmp_path)
        _write_issue(
            issues_dir / "epics",
            "EPIC-001",
            title="Epic",
            relates_to=["FEAT-001"],
        )
        _write_issue(issues_dir / "features", "FEAT-001", title="Completed feature", status="done")
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "tree", "--epic", "EPIC-001"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()  # type: ignore[union-attr]
        assert "FEAT-001" in captured.out
        assert "[done]" in captured.out

    def test_tree_json_output(self, tmp_path: Path, capsys: object) -> None:
        """--format json emits valid JSON with root, nodes, and edges keys."""
        issues_dir = _setup_project(tmp_path)
        _write_issue(
            issues_dir / "epics",
            "EPIC-001",
            title="JSON epic",
            relates_to=["FEAT-001", "FEAT-002"],
        )
        _write_issue(issues_dir / "features", "FEAT-001", title="Alpha")
        _write_issue(issues_dir / "features", "FEAT-002", title="Beta", blocked_by=["FEAT-001"])
        with patch.object(
            sys, "argv", ["ll-deps", "-d", str(issues_dir), "tree", "--epic", "EPIC-001", "-f", "json"]
        ):
            result = main()
        assert result == 0
        captured = capsys.readouterr()  # type: ignore[union-attr]
        data = json.loads(captured.out)
        assert data["root"] == "EPIC-001"
        node_ids = {n["id"] for n in data["nodes"]}
        assert "FEAT-001" in node_ids
        assert "FEAT-002" in node_ids
        assert "edges" in data

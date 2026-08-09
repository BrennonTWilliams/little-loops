"""Tests for ll-issues scaffold-epic sub-command (FEAT-2947)."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.cli.issues.scaffold_epic import ChildSpec, scaffold_epic
from little_loops.config import BRConfig
from little_loops.frontmatter import parse_frontmatter

_CONFIG: dict[str, Any] = {
    "project": {"name": "test-project"},
    "issues": {
        "base_dir": ".issues",
        "categories": {
            "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
            "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
            "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
            "epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"},
        },
        "priorities": ["P0", "P1", "P2", "P3", "P4", "P5"],
    },
}


@pytest.fixture
def project(temp_project_dir: Path) -> Path:
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(_CONFIG))
    for cat in ("bugs", "features", "enhancements", "epics"):
        (temp_project_dir / ".issues" / cat).mkdir(parents=True, exist_ok=True)
    return temp_project_dir


def _config(root: Path) -> BRConfig:
    return BRConfig(root)


def _invoke(argv: list[str]) -> tuple[int, str]:
    from little_loops.cli import main_issues

    with patch.object(sys, "argv", argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = main_issues()
        return result, buf.getvalue()


class TestScaffoldEpic:
    def test_creates_epic_and_children_both_directions_wired(self, project: Path) -> None:
        config = _config(project)
        epic, children = scaffold_epic(
            config,
            title="Ship X",
            children=[
                ChildSpec(type="FEAT", title="Do A", priority="P2", summary="Do the A thing"),
                ChildSpec(type="ENH", title="Improve B", priority="P3"),
            ],
        )

        assert epic.id == "EPIC-001"
        assert [c.id for c in children] == ["FEAT-002", "ENH-003"]

        epic_content = epic.path.read_text(encoding="utf-8")
        for child in children:
            assert f"- **{child.id}**" in epic_content
            fm = parse_frontmatter(child.path.read_text(encoding="utf-8"))
            assert fm["parent"] == epic.id

    def test_no_transactional_multi_file_written_on_success(self, project: Path) -> None:
        config = _config(project)
        epic, children = scaffold_epic(
            config,
            title="Ship Y",
            children=[ChildSpec(type="BUG", title="Fix Y", priority="P2")],
        )
        assert epic.path.exists()
        for c in children:
            assert c.path.exists()

    def test_invalid_child_type_raises_before_writing(self, project: Path) -> None:
        config = _config(project)
        with pytest.raises(ValueError):
            scaffold_epic(
                config,
                title="Ship Z",
                children=[
                    ChildSpec(type="FEAT", title="Good child", priority="P2"),
                    ChildSpec(type="NOPE", title="Bad child", priority="P2"),
                ],
            )
        assert list((project / ".issues" / "epics").glob("*.md")) == []
        assert list((project / ".issues" / "features").glob("*.md")) == []

    def test_unlink_on_failure_removes_partial_writes(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failure after the EPIC file is written unlinks it (D5)."""
        import little_loops.cli.issues.scaffold_epic as se_mod

        config = _config(project)
        real_open = open
        call_count = {"n": 0}

        def flaky_open(path: Any, mode: str = "r", encoding: str | None = None) -> Any:
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise OSError("simulated write failure")
            return real_open(path, mode, encoding=encoding)

        monkeypatch.setattr(se_mod, "open", flaky_open, raising=False)

        with pytest.raises(OSError):
            scaffold_epic(
                config,
                title="Ship Boom",
                children=[ChildSpec(type="BUG", title="Fated child", priority="P2")],
            )

        assert list((project / ".issues" / "epics").glob("*.md")) == []
        assert list((project / ".issues" / "bugs").glob("*.md")) == []

    def test_stage_adds_every_created_file_in_one_call(self, project: Path) -> None:
        from tests.helpers import copy_git_template

        copy_git_template(project)
        config = _config(project)
        epic, children = scaffold_epic(
            config,
            title="Ship Staged",
            children=[ChildSpec(type="ENH", title="Staged child", priority="P2")],
            stage=True,
        )

        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=project,
            capture_output=True,
            text=True,
            check=True,
        )
        staged_paths = {line[3:] for line in status.stdout.splitlines() if line.startswith("A ")}
        resolved_project = project.resolve()
        assert str(epic.path.resolve().relative_to(resolved_project)) in staged_paths
        for c in children:
            assert str(c.path.resolve().relative_to(resolved_project)) in staged_paths


class TestScaffoldEpicCli:
    def test_scaffold_epic_json_output(self, project: Path) -> None:
        children_json = json.dumps(
            [{"type": "FEAT", "title": "Do A", "priority": "P2", "summary": "Do the A thing"}]
        )
        exit_code, out = _invoke(
            [
                "ll-issues",
                "scaffold-epic",
                "--title",
                "Ship X",
                "--children",
                children_json,
                "--json",
                "--config",
                str(project),
            ]
        )
        assert exit_code == 0
        payload = json.loads(out)
        assert payload["epic"]["id"] == "EPIC-001"
        assert len(payload["children"]) == 1

    def test_scaffold_epic_children_from_file(self, project: Path, tmp_path: Path) -> None:
        children_file = tmp_path / "children.json"
        children_file.write_text(json.dumps([{"type": "BUG", "title": "Fix it"}]))
        exit_code, out = _invoke(
            [
                "ll-issues",
                "scaffold-epic",
                "--title",
                "From file",
                "--children",
                f"@{children_file}",
                "--json",
                "--config",
                str(project),
            ]
        )
        assert exit_code == 0
        payload = json.loads(out)
        assert len(payload["children"]) == 1

    def test_scaffold_epic_invalid_json_reports_error(self, project: Path) -> None:
        exit_code, _ = _invoke(
            [
                "ll-issues",
                "scaffold-epic",
                "--title",
                "Bad",
                "--children",
                "not json",
                "--config",
                str(project),
            ]
        )
        assert exit_code == 1

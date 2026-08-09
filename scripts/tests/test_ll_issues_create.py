"""Tests for ll-issues create sub-command (FEAT-2947)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.cli.issues.create import IssueSpec, create_issue
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


class TestCreateIssue:
    def test_writes_to_correct_type_dir_with_expected_filename(self, project: Path) -> None:
        config = _config(project)
        spec = IssueSpec(type="BUG", title="Login button unresponsive", priority="P3")
        created = create_issue(config, spec)

        assert created.id == "BUG-001"
        expected = project / ".issues" / "bugs" / "P3-BUG-001-login-button-unresponsive.md"
        assert created.path.resolve() == expected.resolve()
        assert created.path.exists()

    def test_frontmatter_round_trips_exactly(self, project: Path) -> None:
        config = _config(project)
        spec = IssueSpec(
            type="FEAT",
            title="a: colon title",
            priority="P1",
            parent=None,
            labels=["cli", "issues"],
        )
        created = create_issue(config, spec)
        content = created.path.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)

        assert fm["id"] == "FEAT-001"
        assert fm["title"] == "a: colon title"
        assert fm["priority"] == "P1"
        assert fm["status"] == "open"
        assert fm["labels"] == ["cli", "issues"]
        # Childless issue must never carry the literal string "None" (D2).
        assert "parent" not in fm

    def test_parent_written_as_yaml_not_none_string(self, project: Path) -> None:
        config = _config(project)
        epic = create_issue(config, IssueSpec(type="EPIC", title="Umbrella", variant="full"))
        child = create_issue(config, IssueSpec(type="ENH", title="Child thing", parent=epic.id))

        fm = parse_frontmatter(child.path.read_text(encoding="utf-8"))
        assert fm["parent"] == epic.id
        assert fm["parent"] != "None"

    def test_parent_wiring_appends_epic_children_bullet(self, project: Path) -> None:
        config = _config(project)
        epic = create_issue(config, IssueSpec(type="EPIC", title="Umbrella", variant="full"))
        child = create_issue(config, IssueSpec(type="ENH", title="Child thing", parent=epic.id))

        epic_content = epic.path.read_text(encoding="utf-8")
        assert f"- **{child.id}** — Child thing (open)" in epic_content

    def test_parent_wiring_skipped_silently_for_non_epic_parent(self, project: Path) -> None:
        config = _config(project)
        # A BUG has no `## Children` section — wiring must no-op, not raise.
        parent = create_issue(config, IssueSpec(type="BUG", title="Parent bug"))
        child = create_issue(config, IssueSpec(type="ENH", title="Followup", parent=parent.id))
        assert parse_frontmatter(child.path.read_text())["parent"] == parent.id

    def test_body_file_content_becomes_summary(self, project: Path) -> None:
        config = _config(project)
        created = create_issue(
            config, IssueSpec(type="BUG", title="Some bug", body="The real summary text.")
        )
        assert "The real summary text." in created.path.read_text(encoding="utf-8")

    def test_ids_are_globally_unique_across_types(self, project: Path) -> None:
        config = _config(project)
        a = create_issue(config, IssueSpec(type="BUG", title="First"))
        b = create_issue(config, IssueSpec(type="FEAT", title="Second"))
        assert a.id == "BUG-001"
        assert b.id == "FEAT-002"

    def test_collision_retry_backstop_skips_preexisting_path(self, project: Path) -> None:
        config = _config(project)
        # Pre-create the path get_next_issue_number would otherwise pick, to
        # exercise the open(path, "x") FileExistsError retry loop (D3).
        collide_path = project / ".issues" / "bugs" / "P2-BUG-001-first-bug.md"
        collide_path.write_text("pre-existing", encoding="utf-8")

        created = create_issue(config, IssueSpec(type="BUG", title="First bug"))
        assert created.id == "BUG-002"
        assert collide_path.read_text(encoding="utf-8") == "pre-existing"

    def test_unknown_type_raises(self, project: Path) -> None:
        config = _config(project)
        with pytest.raises(ValueError):
            create_issue(config, IssueSpec(type="TASK", title="Bad type"))


class TestConcurrentCreate:
    """Two callers racing for the next ID must get distinct IDs (D3)."""

    def test_two_threads_never_collide(self, project: Path) -> None:
        config = _config(project)
        results: list[str] = []
        errors: list[BaseException] = []
        barrier = threading.Barrier(2)

        def worker(title: str) -> None:
            try:
                barrier.wait(timeout=5)
                created = create_issue(config, IssueSpec(type="BUG", title=title))
                results.append(created.id)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(f"Racer {i}",)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
        assert len(results) == 2
        assert len(set(results)) == 2


class TestStage:
    def test_stage_flag_git_adds_created_file(self, project: Path) -> None:
        import subprocess

        from tests.helpers import copy_git_template

        copy_git_template(project)
        config = _config(project)
        created = create_issue(config, IssueSpec(type="BUG", title="Stage me", stage=True))

        status = subprocess.run(
            ["git", "status", "--short", "--", str(created.path)],
            cwd=project,
            capture_output=True,
            text=True,
            check=True,
        )
        assert status.stdout.strip().startswith("A ")


class TestCreateCli:
    def test_create_json_output(self, project: Path) -> None:
        exit_code, out = _invoke(
            [
                "ll-issues",
                "create",
                "--type",
                "ENH",
                "--title",
                "CLI created enhancement",
                "--json",
                "--config",
                str(project),
            ]
        )
        assert exit_code == 0
        payload = json.loads(out)
        assert payload["id"] == "ENH-001"
        assert Path(payload["path"]).exists()

    def test_create_body_file_stdin(self, project: Path) -> None:
        with patch("sys.stdin", io.StringIO("Piped summary body.")):
            exit_code, out = _invoke(
                [
                    "ll-issues",
                    "create",
                    "--type",
                    "BUG",
                    "--title",
                    "Piped body bug",
                    "--body-file",
                    "-",
                    "--json",
                    "--config",
                    str(project),
                ]
            )
        assert exit_code == 0
        path = Path(json.loads(out)["path"])
        assert "Piped summary body." in path.read_text(encoding="utf-8")

"""Tests for ll-issues create sub-command (FEAT-2947)."""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.cli.issues.create import IssueSpec, create_issue, render_issue_preview
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


class TestFullBodyMerge:
    """BUG-3193: a sectioned body must merge, not duplicate the scaffold."""

    def _headings(self, body: str) -> list[str]:
        return re.findall(r"^##\s+(.+)$", body, re.MULTILINE)

    def test_no_duplicate_headings_for_sectioned_body(self, project: Path) -> None:
        config = _config(project)
        body = (
            "## Summary\n\nReal summary text.\n\n"
            "## Current Behavior\n\nActual current behavior.\n\n"
            "## Status\n\n**Open** | Created: 2020-01-01 | Priority: P1\n"
        )
        created = create_issue(config, IssueSpec(type="BUG", title="Sectioned", body=body))
        content = created.path.read_text(encoding="utf-8")
        headings = self._headings(content)
        assert headings.count("Summary") == 1
        assert "Real summary text." in content
        assert "Actual current behavior." in content

    def test_plain_prose_body_unaffected(self, project: Path) -> None:
        config = _config(project)
        created = create_issue(
            config, IssueSpec(type="BUG", title="Plain prose", body="Just some prose text.")
        )
        content = created.path.read_text(encoding="utf-8")
        assert "Just some prose text." in content
        # Still the old Summary-only scaffold shape.
        assert content.count("## Summary") == 1
        assert "## Current Behavior" in content

    def test_fenced_heading_quote_not_misrouted(self, project: Path) -> None:
        config = _config(project)
        body = (
            "Some prose quoting the template:\n\n"
            "```\n## Current Behavior\n## Status\n```\n\nno real sections here.\n"
        )
        created = create_issue(config, IssueSpec(type="BUG", title="Fence quote", body=body))
        content = created.path.read_text(encoding="utf-8")
        # Falls through to the plain-prose scaffold path: the placeholder text still
        # fires (proving no merge occurred), and the fenced quote is preserved verbatim
        # as part of the caller's Summary text, not treated as a real heading.
        assert "[If applicable" in content
        assert "no real sections here." in content
        assert content.count("## Summary") == 1

    def test_no_section_dropped_outside_variant(self, project: Path) -> None:
        config = _config(project)
        body = (
            "## Summary\n\nSummary text.\n\n"
            "## Steps to Reproduce\n\nStep one.\n\n"
            "## Program Design\n\nDesign notes.\n\n"
            "## Related Key Documentation\n\n- some doc\n\n"
            "## Status\n\n**Open** | Created: 2020-01-01 | Priority: P1\n"
        )
        created = create_issue(config, IssueSpec(type="BUG", title="No drop", body=body))
        content = created.path.read_text(encoding="utf-8")
        for heading in ("Steps to Reproduce", "Program Design", "Related Key Documentation"):
            assert f"## {heading}" in content
        assert "Step one." in content
        assert "Design notes." in content
        assert "- some doc" in content

    def test_unsupplied_variant_sections_keep_placeholder(self, project: Path) -> None:
        config = _config(project)
        body = "## Summary\n\nSummary text.\n\n## Current Behavior\n\nBehavior text.\n"
        created = create_issue(config, IssueSpec(type="BUG", title="Placeholders", body=body))
        content = created.path.read_text(encoding="utf-8")
        assert "[What should happen instead]" in content  # Expected Behavior placeholder
        assert "**Priority**: [P0-P5]" in content  # Impact placeholder

    def test_fresh_full_variant_issue_reports_nonzero_placeholder_count(
        self, project: Path
    ) -> None:
        """ENH-3244: a freshly created issue ships the template's own placeholders."""
        from little_loops.issue_parser import placeholder_count

        config = _config(project)
        created = create_issue(config, IssueSpec(type="BUG", title="Fresh full", variant="full"))

        assert placeholder_count(created.path) > 0

    def test_filling_every_placeholder_drops_count_to_zero(self, project: Path) -> None:
        """Replacing every derived placeholder token clears the gap entirely."""
        from little_loops.issue_parser import _template_placeholder_patterns, placeholder_count

        config = _config(project)
        created = create_issue(config, IssueSpec(type="BUG", title="Fresh full", variant="full"))
        assert placeholder_count(created.path) > 0

        content = created.path.read_text(encoding="utf-8")
        patterns = _template_placeholder_patterns("BUG")
        for tokens in patterns.values():
            for token in tokens:
                content = content.replace(token, "REAL CONTENT")
        created.path.write_text(content, encoding="utf-8")

        assert placeholder_count(created.path) == 0

    def test_leading_h1_not_doubled(self, project: Path) -> None:
        config = _config(project)
        body = "# Some caller title\n\n## Summary\n\nSummary text.\n\n## Status\n\n**Open**\n"
        created = create_issue(config, IssueSpec(type="BUG", title="H1 test", body=body))
        content = created.path.read_text(encoding="utf-8")
        assert content.count("Some caller title") == 0
        assert re.search(r"^# BUG-\d+: H1 test$", content, re.MULTILINE)

    def test_preamble_folded_into_summary(self, project: Path) -> None:
        config = _config(project)
        body = "Leading prose before the first heading.\n\n## Summary\n\nReal summary.\n"
        created = create_issue(config, IssueSpec(type="BUG", title="Preamble", body=body))
        content = created.path.read_text(encoding="utf-8")
        assert "Leading prose before the first heading." in content
        assert "Real summary." in content

    def test_caller_status_does_not_lose_generated_footer(self, project: Path) -> None:
        config = _config(project)
        body = "## Summary\n\nText.\n\n## Status\n\n**Open** | Created: 2019-01-01 | Priority: P5\n"
        created = create_issue(config, IssueSpec(type="BUG", title="Status regen", body=body))
        content = created.path.read_text(encoding="utf-8")
        assert "2019-01-01" not in content
        assert re.search(r"\*\*Open\*\* \| Created: \d{4}-\d{2}-\d{2} \| Priority: P2", content)

    def test_status_is_last_heading(self, project: Path) -> None:
        config = _config(project)
        body = (
            "## Summary\n\nText.\n\n## Steps to Reproduce\n\nStep.\n\n"
            "## Related Key Documentation\n\n- doc\n\n## Status\n\n**Open**\n"
        )
        created = create_issue(config, IssueSpec(type="BUG", title="Status last", body=body))
        headings = self._headings(created.path.read_text(encoding="utf-8"))
        assert headings[-1] == "Status"

    def test_caller_session_log_not_duplicated(self, project: Path) -> None:
        config = _config(project)
        body = "## Summary\n\nText.\n\n## Session Log\n\n- caller entry\n\n## Status\n\n**Open**\n"
        created = create_issue(config, IssueSpec(type="BUG", title="Session log", body=body))
        content = created.path.read_text(encoding="utf-8")
        assert content.count("## Session Log") == 0
        assert "caller entry" not in content

    def test_body_opening_with_frontmatter_rejected(self, project: Path) -> None:
        config = _config(project)
        body = "---\nid: BUG-1\n---\n\nbody text\n"
        with pytest.raises(ValueError, match="frontmatter"):
            create_issue(config, IssueSpec(type="BUG", title="Bad body", body=body))

    def test_preview_and_apply_produce_identical_bodies(self, project: Path) -> None:
        from datetime import UTC, datetime

        config = _config(project)
        body = "## Summary\n\nText.\n\n## Current Behavior\n\nBehavior.\n\n## Status\n\n**Open**\n"
        spec = IssueSpec(type="BUG", title="Parity", body=body)
        now = datetime(2026, 1, 1, tzinfo=UTC)

        preview = render_issue_preview(config, spec, now=now)["rendered_body"]
        created = create_issue(config, spec, now=now)
        applied = created.path.read_text(encoding="utf-8")

        # Only the allocated id (vs. ID_PLACEHOLDER) legitimately differs.
        assert applied == preview.replace("<assigned-at-apply>", created.id)


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

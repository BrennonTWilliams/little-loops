"""Tests for ll-issues link sub-command (FEAT-2842)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def _write_issue(issues_dir: Path, filename: str, content: str) -> Path:
    path = issues_dir / "features" / filename
    path.write_text(content)
    return path


class TestIssuesCLILink:
    """Tests for ll-issues link sub-command."""

    def _run(self, temp_project_dir: Path, *cli_args: str) -> int:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "link", *cli_args, "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            return main_issues()

    def test_link_blocked_by_creates_new_key(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        result = self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109")

        assert result == 0
        content = a.read_text()
        assert "blocked_by" in content
        assert "FEAT-109" in content

    def test_link_is_idempotent_no_duplicate_entry(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        assert self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109") == 0
        assert self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109") == 0

        content = a.read_text()
        assert content.count("FEAT-109") == 1
        assert content.count("blocked_by:") == 1

    def test_link_appends_to_existing_list(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir,
            "P2-FEAT-110-a.md",
            "---\nid: FEAT-110\nstatus: open\nblocked_by:\n- FEAT-108\n---\n# FEAT-110: A\n",
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        assert self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109") == 0

        content = a.read_text()
        assert "FEAT-108" in content
        assert "FEAT-109" in content

    def test_link_unknown_target_exits_nonzero_without_modifying_file(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        original = a.read_text()

        result = self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-999")

        assert result != 0
        assert a.read_text() == original

    def test_link_no_unknown_warning_for_done_blocker(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        caplog: Any,
    ) -> None:
        """A blocked_by edge pointing at a done issue must not warn as unknown.

        `_check_cycle` builds the graph from `find_issues_for_graph`, which
        excludes terminal statuses (done/cancelled) by design (BUG-2897) — so
        a done blocker is legitimately absent from that issue list. Without
        passing `all_known_ids` to `DependencyGraph.from_issues`, that absence
        is indistinguishable from a typo'd/nonexistent ID and gets logged as
        an "unknown issue" warning.
        """
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        _write_issue(
            issues_dir,
            "P2-FEAT-110-a.md",
            "---\nid: FEAT-110\nstatus: open\nblocked_by:\n- FEAT-100\n---\n# FEAT-110: A\n",
        )
        _write_issue(
            issues_dir, "P2-FEAT-100-c.md", "---\nid: FEAT-100\nstatus: done\n---\n# FEAT-100: C\n"
        )
        _write_issue(
            issues_dir, "P2-FEAT-101-d.md", "---\nid: FEAT-101\nstatus: open\n---\n# FEAT-101: D\n"
        )

        import logging

        with caplog.at_level(logging.WARNING):
            result = self._run(temp_project_dir, "FEAT-110", "--depends-on", "FEAT-101")

        assert result == 0
        assert "FEAT-100" not in caplog.text

    def test_link_cycle_refused_nonzero_exit(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        _write_issue(
            issues_dir,
            "P2-FEAT-110-a.md",
            "---\nid: FEAT-110\nstatus: open\nblocked_by:\n- FEAT-109\n---\n# FEAT-110: A\n",
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        # FEAT-109 blocked_by FEAT-110 would create a cycle (110 -> 109 -> 110)
        result = self._run(temp_project_dir, "FEAT-109", "--blocked-by", "FEAT-110")

        assert result != 0

    def test_link_preserves_unrelated_frontmatter_and_body(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir,
            "P2-FEAT-110-a.md",
            "---\nid: FEAT-110\nstatus: open\npriority: P2\n---\n# FEAT-110: A\n\nSome body text.\n",
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        assert self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109") == 0

        content = a.read_text()
        assert "priority: P2" in content
        assert "# FEAT-110: A" in content
        assert "Some body text." in content

    def test_link_unlink_removes_entry(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir,
            "P2-FEAT-110-a.md",
            "---\nid: FEAT-110\nstatus: open\nblocked_by:\n- FEAT-109\n---\n# FEAT-110: A\n",
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        result = self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109", "--unlink")

        assert result == 0
        content = a.read_text()
        assert "FEAT-109" not in content

    def test_link_json_output(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "link",
                "FEAT-110",
                "--blocked-by",
                "FEAT-109",
                "--json",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0

    def test_link_dry_run_does_not_modify_file(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        original = a.read_text()
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        result = self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109", "--dry-run")

        assert result == 0
        assert a.read_text() == original

    def test_link_bare_numeric_id_resolves(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        result = self._run(temp_project_dir, "110", "--blocked-by", "109")

        assert result == 0
        assert "FEAT-109" in a.read_text()


_EPIC_BODY = "# EPIC-200: Epic\n\n## Children\n\n- **FEAT-1** — Existing (open)\n\n## Notes\n"


class TestIssuesCLILinkParent:
    """Tests for ``ll-issues link CHILD --parent EPIC`` (ENH-3749)."""

    @pytest.fixture
    def project(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> Path:
        (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))
        (issues_dir / "epics").mkdir(parents=True, exist_ok=True)
        return temp_project_dir

    def _run(self, project: Path, *cli_args: str) -> int:
        with patch.object(sys, "argv", ["ll-issues", "link", *cli_args, "--config", str(project)]):
            from little_loops.cli import main_issues

            return main_issues()

    def _child(self, project: Path, extra: str = "", status: str = "open", num: int = 110) -> Path:
        path = project / ".issues" / "features" / f"P2-FEAT-{num}-a.md"
        path.write_bytes(
            f"---\nid: FEAT-{num}\ntype: FEAT\nstatus: {status}\ntitle: Child A\n{extra}---\n"
            f"# FEAT-{num}: Child A\n".encode()
        )
        return path

    def _epic(self, project: Path, num: int = 200, body: str = _EPIC_BODY) -> Path:
        path = project / ".issues" / "epics" / f"P2-EPIC-{num}-e.md"
        path.write_bytes(f"---\nid: EPIC-{num}\ntype: EPIC\nstatus: open\n---\n{body}".encode())
        return path

    def test_assigns_parent_and_children_bullet(self, project: Path) -> None:
        child, epic = self._child(project), self._epic(project)
        assert self._run(project, "110", "--parent", "200") == 0
        text = child.read_text()
        assert "parent: EPIC-200" in text
        assert "epic:" not in text  # absent key stays absent
        assert "- **FEAT-110** — Child A (open)" in epic.read_text()

    @pytest.mark.parametrize("status", ["done", "deferred", "blocked"])
    def test_bullet_uses_child_status(self, project: Path, status: str) -> None:
        self._child(project, status=status)
        epic = self._epic(project)
        assert self._run(project, "FEAT-110", "--parent", "EPIC-200") == 0
        assert f"- **FEAT-110** — Child A ({status})" in epic.read_text()

    def test_syncs_existing_and_null_epic_key(self, project: Path) -> None:
        child = self._child(project, extra="epic:\n")
        self._epic(project)
        assert self._run(project, "110", "--parent", "200") == 0
        assert "epic: EPIC-200" in child.read_text()

    def test_rerun_performs_no_writes(self, project: Path) -> None:
        self._child(project)
        self._epic(project)
        assert self._run(project, "110", "--parent", "200") == 0
        with patch("little_loops.file_utils.atomic_write") as writer:
            assert self._run(project, "110", "--parent", "200") == 0
        writer.assert_not_called()

    def test_same_parent_rerun_repairs_missing_bullet(self, project: Path) -> None:
        child = self._child(project, extra="parent: EPIC-200\n")
        before = child.read_bytes()
        epic = self._epic(project)
        assert self._run(project, "110", "--parent", "200") == 0
        assert child.read_bytes() == before
        assert "FEAT-110" in epic.read_text()

    def test_body_listed_only_writes_child_only(self, project: Path) -> None:
        child = self._child(project)
        body = _EPIC_BODY.replace("(open)\n", "(open)\n- **FEAT-110** — Listed (open)\n", 1)
        epic = self._epic(project, body=body)
        before = epic.read_bytes()
        assert self._run(project, "110", "--parent", "200") == 0
        assert epic.read_bytes() == before
        assert "parent: EPIC-200" in child.read_text()

    def test_conflict_rejected_without_writes(self, project: Path) -> None:
        child = self._child(project, extra="parent: EPIC-300\n")
        epic = self._epic(project)
        before = (child.read_bytes(), epic.read_bytes())
        assert self._run(project, "110", "--parent", "200") == 1
        assert (child.read_bytes(), epic.read_bytes()) == before

    def test_disagreeing_keys_rejected(self, project: Path) -> None:
        self._child(project, extra="parent: EPIC-200\nepic: EPIC-300\n")
        self._epic(project)
        assert self._run(project, "110", "--parent", "200") == 1

    def test_reparent_reports_displaced_and_keeps_old_bullets(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        child = self._child(project, extra="parent: EPIC-300\nepic: EPIC-300\n")
        self._epic(project)
        old = self._epic(project, num=300, body=_EPIC_BODY + "\n- **FEAT-110** — Child A (open)\n")
        old_bytes = old.read_bytes()
        assert self._run(project, "110", "--parent", "200", "--reparent", "--json") == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["previous_parents"] == ["EPIC-300"]
        assert any("EPIC-300" in w for w in doc["warnings"])
        assert "parent: EPIC-200" in child.read_text() and "epic: EPIC-200" in child.read_text()
        assert old.read_bytes() == old_bytes

    def test_reparent_missing_old_parent_still_assigns(self, project: Path) -> None:
        child = self._child(project, extra="parent: EPIC-999\n")
        self._epic(project)
        assert self._run(project, "110", "--parent", "200", "--reparent") == 0
        assert "parent: EPIC-200" in child.read_text()

    def test_missing_heading_is_explicit_success(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        child = self._child(project)
        epic = self._epic(project, body="# EPIC-200: Epic\n")
        before = epic.read_bytes()
        assert self._run(project, "110", "--parent", "200", "--json") == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["epic_body_status"] == "missing_heading"
        assert doc["child_written"] is True and doc["epic_written"] is False
        assert epic.read_bytes() == before
        assert "parent: EPIC-200" in child.read_text()

    def test_missing_heading_reported_even_when_unchanged(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._child(project, extra="parent: EPIC-200\n")
        self._epic(project, body="# EPIC-200: Epic\n")
        assert self._run(project, "110", "--parent", "200", "--json") == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["status"] == "unchanged"
        assert doc["epic_body_status"] == "missing_heading"

    def test_target_must_be_epic_and_child_not_epic(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._child(project)
        self._child(project, num=111)
        assert self._run(project, "110", "--parent", "111", "--json") == 1
        assert json.loads(capsys.readouterr().out)["reason"] == "invalid_target"
        self._epic(project)
        assert self._run(project, "200", "--parent", "200", "--json") == 1
        assert json.loads(capsys.readouterr().out)["reason"] == "invalid_type"

    def test_identity_mismatch_rejected(self, project: Path) -> None:
        path = self._child(project)
        path.write_text(path.read_text().replace("id: FEAT-110", "id: FEAT-999"))
        self._epic(project)
        assert self._run(project, "110", "--parent", "200") == 1

    def test_post_fence_parent_rejected(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = self._child(project)
        path.write_text(path.read_text().replace("---\n# FEAT", "---\nparent: EPIC-300\n# FEAT"))
        self._epic(project)
        before = path.read_bytes()
        assert self._run(project, "110", "--parent", "200", "--json") == 1
        assert json.loads(capsys.readouterr().out)["reason"] == "metadata_unsafe"
        assert path.read_bytes() == before

    def test_intentional_parentless_overridden_with_warning(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        child = self._child(project, extra="parentless_reason: standalone\n")
        self._epic(project)
        assert self._run(project, "110", "--parent", "200", "--json") == 0
        doc = json.loads(capsys.readouterr().out)
        assert any("parentless" in w for w in doc["warnings"])
        assert "parentless_reason: standalone" in child.read_text()

    def test_ambiguous_children_section_rejected(self, project: Path) -> None:
        child = self._child(project)
        body = "# EPIC-200: Epic\n\n## Children\n\n- **FEAT-1** — Existing (open)\nlazy text\n"
        epic = self._epic(project, body=body)
        before = (child.read_bytes(), epic.read_bytes())
        assert self._run(project, "110", "--parent", "200") == 1
        assert (child.read_bytes(), epic.read_bytes()) == before

    @pytest.mark.parametrize("flag", ["--unlink", "--remove", "--force", "--reciprocal"])
    def test_unsupported_flag_combinations_rejected(
        self, project: Path, flag: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        child = self._child(project)
        self._epic(project)
        before = child.read_bytes()
        assert self._run(project, "110", "--parent", "200", flag, "--json") == 1
        assert json.loads(capsys.readouterr().out)["reason"] == "unsupported_flag_combination"
        assert child.read_bytes() == before

    def test_reparent_requires_parent(self, project: Path) -> None:
        self._child(project)
        self._child(project, num=111)
        assert self._run(project, "110", "--blocked-by", "111", "--reparent") == 1

    def test_parent_mutually_exclusive_with_list_flags(self, project: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            self._run(project, "110", "--parent", "200", "--blocked-by", "111")
        assert exc.value.code == 2

    def test_dry_run_matches_apply_without_writing(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        child, epic = self._child(project), self._epic(project)
        before = (child.read_bytes(), epic.read_bytes())
        assert self._run(project, "110", "--parent", "200", "--dry-run", "--json") == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["status"] == "would_assign"
        assert doc["child_would_change"] and doc["epic_would_change"]
        assert not doc["child_written"] and not doc["epic_written"]
        assert (child.read_bytes(), epic.read_bytes()) == before

    def test_dry_run_rejection_is_still_an_error(self, project: Path) -> None:
        self._child(project, extra="parent: EPIC-300\n")
        self._epic(project)
        assert self._run(project, "110", "--parent", "200", "--dry-run") == 1

    def test_crlf_and_mode_preserved(self, project: Path) -> None:
        child = self._child(project)
        epic = self._epic(project)
        for path in (child, epic):
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
            path.chmod(0o640)
        assert self._run(project, "110", "--parent", "200") == 0
        for path in (child, epic):
            data = path.read_bytes()
            assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
            assert path.stat().st_mode & 0o777 == 0o640

    def test_lock_timeout_rejected(self, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self._child(project)
        self._epic(project)
        with patch("little_loops.file_utils.acquire_lock", side_effect=TimeoutError("busy")):
            assert self._run(project, "110", "--parent", "200", "--json") == 1
        assert json.loads(capsys.readouterr().out)["reason"] == "lock_timeout"

    def test_first_write_failure_leaves_both_untouched(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        child, epic = self._child(project), self._epic(project)
        before = (child.read_bytes(), epic.read_bytes())
        with patch("little_loops.file_utils.atomic_write", side_effect=OSError("disk")):
            assert self._run(project, "110", "--parent", "200", "--json") == 1
        doc = json.loads(capsys.readouterr().out)
        assert doc["status"] == "rejected" and doc["reason"] == "write_failed"
        assert (child.read_bytes(), epic.read_bytes()) == before

    def test_second_write_failure_reports_partial_state(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.file_utils import atomic_write as real

        child, epic = self._child(project), self._epic(project)
        epic_before = epic.read_bytes()

        def flaky(path: Path, content: str, *a: Any, **kw: Any) -> None:
            if Path(path).name == epic.name:
                raise OSError("disk")
            real(path, content, *a, **kw)

        with patch("little_loops.file_utils.atomic_write", flaky):
            assert self._run(project, "110", "--parent", "200", "--json") == 1
        doc = json.loads(capsys.readouterr().out)
        assert doc["status"] == "partial_failure"
        assert doc["child_written"] is True and doc["epic_written"] is False
        assert "ll-issues link FEAT-110 --parent EPIC-200" in doc["repair"]
        assert epic.read_bytes() == epic_before
        assert "parent: EPIC-200" in child.read_text()

    def test_json_is_single_document_on_rejection(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._child(project)
        assert self._run(project, "110", "--parent", "999", "--json") == 1
        out = capsys.readouterr().out
        assert json.loads(out)["reason"] == "not_found"

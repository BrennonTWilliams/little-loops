"""Tests for ll-issues epic-consistency subcommand (FEAT-2332)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def epic_consistency_dir(temp_project_dir: Path, sample_config: dict[str, Any]) -> Path:
    """Base fixture: temp project with config and empty .issues dirs."""
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))
    issues_base = temp_project_dir / ".issues"
    (issues_base / "epics").mkdir(parents=True, exist_ok=True)
    (issues_base / "bugs").mkdir(parents=True, exist_ok=True)
    (issues_base / "features").mkdir(parents=True, exist_ok=True)
    (issues_base / "enhancements").mkdir(parents=True, exist_ok=True)
    return issues_base


def _write_epic(epics_dir: Path, epic_id: str, children_section: str = "") -> Path:
    """Write an EPIC file with an optional ## Children section."""
    body = f"---\nstatus: open\n---\n# {epic_id}: Test epic\n\n## Summary\nTest.\n"
    if children_section:
        body += f"\n## Children\n\n{children_section}\n"
    path = epics_dir / f"P2-{epic_id}-test-epic.md"
    path.write_text(body)
    return path


def _write_child(issues_dir: Path, issue_id: str, parent: str | None = None) -> Path:
    """Write a child issue file, optionally with parent: frontmatter."""
    prefix = issue_id.split("-")[0]
    subdir_map = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements"}
    subdir = issues_dir / subdir_map[prefix]
    subdir.mkdir(parents=True, exist_ok=True)
    fm = "---\nstatus: open\n"
    if parent:
        fm += f"parent: {parent}\n"
    fm += "---\n"
    path = subdir / f"P2-{issue_id}-test-child.md"
    path.write_text(f"{fm}# {issue_id}: Test child\n")
    return path


# ---------------------------------------------------------------------------
# TestEpicConsistencyClean
# ---------------------------------------------------------------------------


class TestEpicConsistencyClean:
    """A consistent EPIC (body matches parent: set) exits 0."""

    def test_clean_epic_exits_zero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Clean EPIC with matching body and parent: set exits 0."""
        epics_dir = epic_consistency_dir / "epics"
        _write_epic(
            epics_dir,
            "EPIC-001",
            children_section="- **FEAT-010** — feature one\n- **BUG-011** — bug one",
        )
        _write_child(epic_consistency_dir, "FEAT-010", parent="EPIC-001")
        _write_child(epic_consistency_dir, "BUG-011", parent="EPIC-001")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-001", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "EPIC-001" in captured.out

    def test_epic_with_no_children_exits_zero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """EPIC with no children and no ## Children section exits 0."""
        epics_dir = epic_consistency_dir / "epics"
        _write_epic(epics_dir, "EPIC-002")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-002", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0


# ---------------------------------------------------------------------------
# TestEpicConsistencyCategoryA
# ---------------------------------------------------------------------------


class TestEpicConsistencyCategoryA:
    """Category-(a): parent: child missing from ## Children body."""

    def test_missing_from_body_exits_nonzero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """EPIC with a parent: child absent from body exits non-zero."""
        epics_dir = epic_consistency_dir / "epics"
        _write_epic(epics_dir, "EPIC-010", children_section="")  # empty body
        _write_child(epic_consistency_dir, "FEAT-020", parent="EPIC-010")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-010", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result != 0
        captured = capsys.readouterr()
        assert "FEAT-020" in captured.out

    def test_category_a_label_in_output(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Category-(a) drift is labeled in the text output."""
        epics_dir = epic_consistency_dir / "epics"
        _write_epic(epics_dir, "EPIC-010", children_section="")
        _write_child(epic_consistency_dir, "FEAT-020", parent="EPIC-010")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-010", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            main_issues()

        captured = capsys.readouterr()
        out = captured.out.lower()
        # Should indicate missing from body (category a)
        assert "missing" in out or "(a)" in out or "parent" in out


# ---------------------------------------------------------------------------
# TestEpicConsistencyCategoryB
# ---------------------------------------------------------------------------


class TestEpicConsistencyCategoryB:
    """Category-(b): body-listed real issue with no parent: backref."""

    def test_body_without_parent_exits_nonzero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Body lists an issue that has no parent: EPIC-NNN → exits non-zero."""
        epics_dir = epic_consistency_dir / "epics"
        # FEAT-030 is in body but doesn't have parent: EPIC-020
        _write_epic(
            epics_dir,
            "EPIC-020",
            children_section="- **FEAT-030** — orphaned body entry",
        )
        _write_child(epic_consistency_dir, "FEAT-030", parent=None)  # no parent

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-020", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result != 0
        captured = capsys.readouterr()
        assert "FEAT-030" in captured.out

    def test_category_b_label_in_output(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Category-(b) drift is labeled in the text output."""
        epics_dir = epic_consistency_dir / "epics"
        _write_epic(
            epics_dir,
            "EPIC-020",
            children_section="- **FEAT-030** — orphaned",
        )
        _write_child(epic_consistency_dir, "FEAT-030", parent=None)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-020", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            main_issues()

        captured = capsys.readouterr()
        out = captured.out.lower()
        assert "body" in out or "(b)" in out or "no parent" in out or "backref" in out


# ---------------------------------------------------------------------------
# TestEpicConsistencyProsePreservation
# ---------------------------------------------------------------------------


class TestEpicConsistencyProsePreservation:
    """Non-issue tokens and sub-epic prose are preserved and not flagged."""

    def test_non_issue_tokens_ignored(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Non-issue tokens (MR-1, CT-0, EG-4) in ## Children are not flagged as drift."""
        epics_dir = epic_consistency_dir / "epics"
        _write_epic(
            epics_dir,
            "EPIC-030",
            children_section=(
                "- **FEAT-040** — real child\n"
                "- **MR-1** — rule identifier\n"
                "- **CT-0** — template\n"
                "- **EG-4** — example\n"
            ),
        )
        _write_child(epic_consistency_dir, "FEAT-040", parent="EPIC-030")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-030", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        # MR-1 / CT-0 / EG-4 must not appear as drift violations
        assert "MR-1" not in captured.out or "(b)" not in captured.out

    def test_sub_epic_refs_not_flagged(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """EPIC-* references in ## Children are treated as sub-epic prose, not flagged."""
        epics_dir = epic_consistency_dir / "epics"
        _write_epic(
            epics_dir,
            "EPIC-040",
            children_section=(
                "- **FEAT-050** — real child\n- **EPIC-041** — sub-epic prose reference\n"
            ),
        )
        _write_child(epic_consistency_dir, "FEAT-050", parent="EPIC-040")
        # EPIC-041 exists but is not a child with parent: EPIC-040
        _write_epic(epics_dir, "EPIC-041", children_section="")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-040", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        # EPIC-041 ref in body should be fine (sub-epic prose); no drift
        assert result == 0


# ---------------------------------------------------------------------------
# TestEpicConsistencyFix
# ---------------------------------------------------------------------------


class TestEpicConsistencyFix:
    """--fix rewrites ## Children for category-(a) drift only."""

    def test_fix_adds_missing_category_a_children(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--fix adds missing parent: children to ## Children section."""
        epics_dir = epic_consistency_dir / "epics"
        epic_path = _write_epic(epics_dir, "EPIC-050", children_section="")
        _write_child(epic_consistency_dir, "FEAT-060", parent="EPIC-050")

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "epic-consistency",
                "EPIC-050",
                "--fix",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        updated = epic_path.read_text()
        assert "FEAT-060" in updated

    def test_fix_preserves_existing_description(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
    ) -> None:
        """--fix keeps existing per-child description text after the em-dash."""
        epics_dir = epic_consistency_dir / "epics"
        epic_path = _write_epic(
            epics_dir,
            "EPIC-051",
            children_section="- **FEAT-061** — my custom description",
        )
        _write_child(epic_consistency_dir, "FEAT-061", parent="EPIC-051")
        _write_child(epic_consistency_dir, "FEAT-062", parent="EPIC-051")

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "epic-consistency",
                "EPIC-051",
                "--fix",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            main_issues()

        updated = epic_path.read_text()
        assert "my custom description" in updated
        assert "FEAT-062" in updated

    def test_fix_does_not_drop_category_b_entries(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
    ) -> None:
        """--fix reports category-(b) entries but does not silently remove them."""
        epics_dir = epic_consistency_dir / "epics"
        epic_path = _write_epic(
            epics_dir,
            "EPIC-052",
            children_section="- **FEAT-070** — body-only entry",
        )
        # FEAT-070 has no parent: EPIC-052 → category (b)
        _write_child(epic_consistency_dir, "FEAT-070", parent=None)

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "epic-consistency",
                "EPIC-052",
                "--fix",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            main_issues()

        # The body-only entry must still be present after --fix
        updated = epic_path.read_text()
        assert "FEAT-070" in updated

    def test_fix_preserves_sub_epic_prose(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
    ) -> None:
        """--fix does not remove sub-epic prose lines from ## Children."""
        epics_dir = epic_consistency_dir / "epics"
        epic_path = _write_epic(
            epics_dir,
            "EPIC-053",
            children_section=(
                "- **FEAT-080** — real child\n"
                "- **EPIC-099** — sub-epic reference\n"
                "- **MR-1** — rule\n"
            ),
        )
        _write_child(epic_consistency_dir, "FEAT-080", parent="EPIC-053")
        _write_epic(epics_dir, "EPIC-099", children_section="")

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "epic-consistency",
                "EPIC-053",
                "--fix",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        updated = epic_path.read_text()
        assert "EPIC-099" in updated
        assert "MR-1" in updated


# ---------------------------------------------------------------------------
# TestEpicConsistencyIdempotency
# ---------------------------------------------------------------------------


class TestEpicConsistencyIdempotency:
    """Running --fix twice produces identical output (no-op on second run)."""

    def test_fix_is_idempotent(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
    ) -> None:
        """Second --fix run produces byte-identical file content."""
        epics_dir = epic_consistency_dir / "epics"
        epic_path = _write_epic(epics_dir, "EPIC-060", children_section="")
        _write_child(epic_consistency_dir, "FEAT-090", parent="EPIC-060")
        _write_child(epic_consistency_dir, "BUG-091", parent="EPIC-060")

        argv = [
            "ll-issues",
            "epic-consistency",
            "EPIC-060",
            "--fix",
            "--config",
            str(temp_project_dir),
        ]

        with patch.object(sys, "argv", argv):
            from little_loops.cli import main_issues

            main_issues()

        content_after_first = epic_path.read_text()

        with patch.object(sys, "argv", argv):
            from little_loops.cli import main_issues

            main_issues()

        content_after_second = epic_path.read_text()

        assert content_after_first == content_after_second


# ---------------------------------------------------------------------------
# TestEpicConsistencyJsonFormat
# ---------------------------------------------------------------------------


class TestEpicConsistencyJsonFormat:
    """--format json emits machine-readable per-EPIC report."""

    def test_json_output_shape(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--format json emits valid JSON with required keys."""
        epics_dir = epic_consistency_dir / "epics"
        _write_epic(
            epics_dir,
            "EPIC-070",
            children_section="- **FEAT-100** — documented but orphaned",
        )
        _write_child(epic_consistency_dir, "FEAT-100", parent=None)  # no parent backref
        _write_child(epic_consistency_dir, "BUG-101", parent="EPIC-070")  # missing from body

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "epic-consistency",
                "EPIC-070",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result != 0  # drift found
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "epic" in data or "results" in data
        # Check the per-EPIC shape (may be wrapped in results list or top-level)
        entry = data if "epic" in data else data["results"][0]
        assert "missing_from_body" in entry
        assert "body_without_parent" in entry
        assert "BUG-101" in entry["missing_from_body"]
        assert "FEAT-100" in entry["body_without_parent"]

    def test_json_includes_sub_epic_advisory(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """JSON output includes sub_epic_advisory for EPICs carrying parent: EPIC-NNN."""
        epics_dir = epic_consistency_dir / "epics"
        _write_epic(epics_dir, "EPIC-080")
        # EPIC-081 carries parent: EPIC-080 (sub-epic via parent: — advisory case)
        num = "081"
        path = epics_dir / f"P2-EPIC-{num}-sub-epic.md"
        path.write_text(f"---\nstatus: open\nparent: EPIC-080\n---\n# EPIC-{num}: Sub-epic\n")

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "epic-consistency",
                "EPIC-080",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            main_issues()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        entry = data if "epic" in data else data["results"][0]
        assert "sub_epic_advisory" in entry
        assert any("EPIC-081" in s for s in entry["sub_epic_advisory"])


# ---------------------------------------------------------------------------
# TestEpicConsistencyAll
# ---------------------------------------------------------------------------


class TestEpicConsistencyAll:
    """--all scans every EPIC in the epics directory."""

    def test_all_flag_scans_multiple_epics(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--all checks all EPICs and reports aggregate drift count."""
        epics_dir = epic_consistency_dir / "epics"
        _write_epic(epics_dir, "EPIC-090")  # clean
        _write_epic(epics_dir, "EPIC-091", children_section="")  # (a) drift
        _write_child(epic_consistency_dir, "FEAT-110", parent="EPIC-091")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "--all", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result != 0
        captured = capsys.readouterr()
        assert "EPIC-091" in captured.out

    def test_all_clean_exits_zero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--all exits 0 when all EPICs are consistent."""
        epics_dir = epic_consistency_dir / "epics"
        _write_epic(
            epics_dir,
            "EPIC-092",
            children_section="- **FEAT-120** — child",
        )
        _write_child(epic_consistency_dir, "FEAT-120", parent="EPIC-092")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "--all", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0


# ---------------------------------------------------------------------------
# TestEpicConsistencyRelatesTo
# ---------------------------------------------------------------------------


class TestEpicConsistencyRelatesTo:
    """Category-(c): relates_to entry that is also a parent: child."""

    def test_relates_to_child_flagged_as_category_c(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An issue in both relates_to: and parent: set is flagged as category-(c)."""
        epics_dir = epic_consistency_dir / "epics"
        # EPIC-100 has relates_to: [FEAT-130] AND FEAT-130 has parent: EPIC-100
        epic_content = (
            "---\nstatus: open\nrelates_to:\n- FEAT-130\n---\n"
            "# EPIC-100: Test\n\n## Summary\nTest.\n\n"
            "## Children\n\n- **FEAT-130** — child\n"
        )
        (epics_dir / "P2-EPIC-100-test.md").write_text(epic_content)
        _write_child(epic_consistency_dir, "FEAT-130", parent="EPIC-100")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-100", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result != 0  # category-(c) drift
        captured = capsys.readouterr()
        assert "FEAT-130" in captured.out


# ---------------------------------------------------------------------------
# TestEpicConsistencyErrorHandling
# ---------------------------------------------------------------------------


class TestEpicConsistencyErrorHandling:
    """Error cases: missing EPIC ID, unknown EPIC, neither --all nor EPIC-ID."""

    def test_unknown_epic_exits_nonzero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Unknown EPIC ID exits non-zero with an error message."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "epic-consistency",
                "EPIC-9999",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result != 0

    def test_invalid_id_format_exits_nonzero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Non-EPIC ID (e.g. FEAT-001) exits non-zero with an error."""
        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "epic-consistency",
                "FEAT-001",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result != 0


# ---------------------------------------------------------------------------
# TestEpicConsistencyTypeCasing
# ---------------------------------------------------------------------------


class TestEpicConsistencyTypeCasing:
    """Schema lint: type: must be 'EPIC' (uppercase) on EPIC files."""

    def _write_epic_with_type(self, epics_dir: Path, epic_id: str, type_value: str) -> Path:
        """Write an EPIC file with an explicit type: field."""
        body = (
            f"---\nid: {epic_id}\nstatus: open\ntype: {type_value}\n---\n"
            f"# {epic_id}: Test epic\n\n## Summary\nTest.\n"
        )
        path = epics_dir / f"P2-{epic_id}-test-epic.md"
        path.write_text(body)
        return path

    def test_lowercase_type_exits_nonzero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """EPIC with type: epic (lowercase) fails the lint check."""
        epics_dir = epic_consistency_dir / "epics"
        self._write_epic_with_type(epics_dir, "EPIC-200", "epic")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-200", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result != 0
        captured = capsys.readouterr()
        assert "type" in captured.out.lower() or "casing" in captured.out.lower()

    def test_uppercase_type_exits_zero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """EPIC with type: EPIC (uppercase) passes the type lint check."""
        epics_dir = epic_consistency_dir / "epics"
        self._write_epic_with_type(epics_dir, "EPIC-201", "EPIC")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-201", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0

    def test_missing_type_field_exits_zero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
    ) -> None:
        """EPIC with no type: field is not flagged (field absence is not a violation)."""
        epics_dir = epic_consistency_dir / "epics"
        # _write_epic omits type: field
        _write_epic(epics_dir, "EPIC-202")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-202", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0

    def test_all_flag_catches_lowercase_type(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--all flag reports type casing violations across all EPIC files."""
        epics_dir = epic_consistency_dir / "epics"
        self._write_epic_with_type(epics_dir, "EPIC-203", "epic")
        self._write_epic_with_type(epics_dir, "EPIC-204", "EPIC")  # clean

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "--all", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result != 0
        captured = capsys.readouterr()
        assert "EPIC-203" in captured.out


# ---------------------------------------------------------------------------
# TestEpicConsistencyChildrenFrontmatter
# ---------------------------------------------------------------------------


class TestEpicConsistencyChildrenFrontmatter:
    """Schema lint: EPIC files must not carry a frontmatter children: array."""

    def _write_epic_with_children_fm(
        self, epics_dir: Path, epic_id: str, children_ids: list[str]
    ) -> Path:
        """Write an EPIC file with frontmatter children: array."""
        children_yaml = "\n".join(f"- {c}" for c in children_ids)
        body = (
            f"---\nid: {epic_id}\nstatus: open\ntype: EPIC\n"
            f"children:\n{children_yaml}\n---\n"
            f"# {epic_id}: Test epic\n\n## Summary\nTest.\n"
        )
        path = epics_dir / f"P2-{epic_id}-test-epic.md"
        path.write_text(body)
        return path

    def test_children_frontmatter_exits_nonzero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """EPIC with frontmatter children: array fails the lint check."""
        epics_dir = epic_consistency_dir / "epics"
        self._write_epic_with_children_fm(epics_dir, "EPIC-210", ["FEAT-001", "ENH-002"])

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-210", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result != 0
        captured = capsys.readouterr()
        assert "children" in captured.out.lower()

    def test_no_children_frontmatter_exits_zero(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
    ) -> None:
        """EPIC without frontmatter children: array passes the schema check."""
        epics_dir = epic_consistency_dir / "epics"
        # No children_section so no body-level drift either
        _write_epic(epics_dir, "EPIC-211")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "epic-consistency", "EPIC-211", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0

    def test_json_output_includes_children_fm_flag(
        self,
        temp_project_dir: Path,
        epic_consistency_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--format json output includes has_children_frontmatter key when children: present."""
        epics_dir = epic_consistency_dir / "epics"
        self._write_epic_with_children_fm(epics_dir, "EPIC-212", ["FEAT-001"])

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "epic-consistency",
                "EPIC-212",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result != 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        entry = data if "epic" in data else data["results"][0]
        assert entry.get("has_children_frontmatter") is True

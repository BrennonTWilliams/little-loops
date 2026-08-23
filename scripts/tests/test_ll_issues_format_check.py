"""Tests for ll-issues format-check subcommand (ENH-2426)."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CLEAN_BUG_BODY = "\n".join(
    [
        "---",
        "id: BUG-9101",
        "status: open",
        "---",
        "",
        "# BUG-9101: Test bug",
        "",
        "## Summary",
        "A real problem happens under specific conditions.",
        "",
        "## Current Behavior",
        "It breaks in a specific way.",
        "",
        "## Expected Behavior",
        "It should not break.",
        "",
        "## Steps to Reproduce",
        "1. Do the thing.",
        "2. Observe failure.",
        "",
        "## Impact",
        "- **Priority**: P3 - Low",
        "- **Effort**: Small",
        "- **Risk**: Low",
        "- **Breaking Change**: No",
        "",
        "## Status",
        "open",
    ]
)


@pytest.fixture
def format_check_dir(temp_project_dir: Path, sample_config: dict[str, Any]) -> Path:
    """Base fixture: temp project with config and empty .issues dirs."""
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))
    issues_base = temp_project_dir / ".issues"
    (issues_base / "bugs").mkdir(parents=True, exist_ok=True)
    (issues_base / "features").mkdir(parents=True, exist_ok=True)
    (issues_base / "enhancements").mkdir(parents=True, exist_ok=True)
    return issues_base


def _write_issue(issues_dir: Path, filename: str, body: str) -> Path:
    path = issues_dir / "bugs" / filename
    path.write_text(body)
    return path


def _invoke(argv: list[str]) -> int:
    """Invoke main_issues() with given argv."""
    with patch.object(sys, "argv", argv):
        from little_loops.cli import main_issues

        return main_issues()


# ---------------------------------------------------------------------------
# TestFormatCheckClean
# ---------------------------------------------------------------------------


class TestFormatCheckClean:
    """A fully-populated, non-boilerplate issue exits 0."""

    def test_clean_issue_exits_zero(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_issue(format_check_dir, "P3-BUG-9101-test-bug.md", _CLEAN_BUG_BODY)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9101", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "BUG-9101" in out


# ---------------------------------------------------------------------------
# TestFormatCheckMissing
# ---------------------------------------------------------------------------


class TestFormatCheckMissing:
    """A required section absent entirely exits 1 and is reported as missing."""

    def test_missing_section_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace("## Expected Behavior\nIt should not break.\n\n", "")
        _write_issue(format_check_dir, "P3-BUG-9102-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9102", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "missing: Expected Behavior" in out


# ---------------------------------------------------------------------------
# TestFormatCheckRenamed
# ---------------------------------------------------------------------------


class TestFormatCheckRenamed:
    """A present deprecated section with a canonical replacement exits 1."""

    def test_renamed_section_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY + "\n\n## Proposed Fix\nOld-style content.\n"
        _write_issue(format_check_dir, "P3-BUG-9103-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9103", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "renamed: Proposed Fix → Proposed Solution" in out


# ---------------------------------------------------------------------------
# TestFormatCheckEmpty
# ---------------------------------------------------------------------------


class TestFormatCheckEmpty:
    """A required header present with a whitespace-only body exits 1."""

    def test_empty_section_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace(
            "## Summary\nA real problem happens under specific conditions.\n",
            "## Summary\n\n",
        )
        _write_issue(format_check_dir, "P3-BUG-9104-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9104", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "empty: Summary" in out


# ---------------------------------------------------------------------------
# TestFormatCheckBoilerplate
# ---------------------------------------------------------------------------


class TestFormatCheckBoilerplate:
    """A required header whose body equals its creation_template exits 1."""

    def test_boilerplate_section_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace(
            "## Summary\nA real problem happens under specific conditions.\n",
            "## Summary\n[Description extracted from input]\n",
        )
        _write_issue(format_check_dir, "P3-BUG-9105-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9105", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "boilerplate: Summary" in out


# ---------------------------------------------------------------------------
# TestFormatCheckMalformedId
# ---------------------------------------------------------------------------


class TestFormatCheckMalformedId:
    """A frontmatter id disagreeing with the filename's TYPE-NNN exits 1 (BUG-2769)."""

    def test_malformed_id_section_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: 9108")
        _write_issue(format_check_dir, "P3-BUG-9108-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9108", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "malformed_id: id: 9108 (expected BUG-9108)" in out


# ---------------------------------------------------------------------------
# TestFormatCheckMultiFrontmatter
# ---------------------------------------------------------------------------


class TestFormatCheckMultiFrontmatter:
    """An outer score_* block + canonical id:-bearing block exits 1 (BUG-2955)."""

    def test_double_frontmatter_block_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        outer_and_title = "\n".join(
            [
                "---",
                "score_complexity: 18",
                "status: done",
                "---",
                "# BUG-9110: Test bug",
                "",
            ]
        )
        canonical_and_body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9110")
        body = outer_and_title + canonical_and_body
        _write_issue(format_check_dir, "P3-BUG-9110-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9110", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "multi_frontmatter:" in out

    def test_single_block_issue_has_no_multi_frontmatter_gap(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9111")
        _write_issue(format_check_dir, "P3-BUG-9111-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9111", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "multi_frontmatter:" not in out


# ---------------------------------------------------------------------------
# TestFormatCheckJsonOutput
# ---------------------------------------------------------------------------


class TestFormatCheckJsonOutput:
    """--format json prints the structured gap report."""

    def test_clean_issue_json_output(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9106")
        _write_issue(format_check_dir, "P3-BUG-9106-test-bug.md", body)

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9106",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        data = json.loads(out)
        assert data == {
            "missing": [],
            "renamed": [],
            "empty": [],
            "boilerplate": [],
            "malformed_id": [],
            "prose_dep_drift": [],
            "stale_prose_dep": [],
            "program_design_nonspecific": [],
            "deprecated_key": [],
            "multi_frontmatter": [],
            "testable": [],
            "stale_file_ref": [],
            "unmarked_superseded_directive": [],
            # ENH-2993: one entry per H2 stacking >1 findings block.
            "duplicate_findings_block": [],
            # ENH-2999: ambiguous (>1 suffix match) split out from stale_file_ref.
            "ambiguous_file_ref": [],
            # ENH-3045: replacement-target ref with no Behavior Parity table.
            "missing_behavior_parity": [],
            # ENH-3046: blocked_by/depends_on ID whose body describes it as soft.
            "soft_dep_hard_edge": [],
            # BUG-3059: dependency entry that isn't a well-formed TYPE-NNN ID.
            "malformed_dep_id": [],
            # FEAT-3048: backticked symbol claim attributed to a cited file
            # that doesn't resolve as a def-site/module constant in it.
            "stale_symbol_ref": [],
            # BUG-3063 C: symbol claim that doesn't resolve in the cited file
            # but does resolve elsewhere in the repo (mis-attribution).
            "mislocated_symbol_ref": [],
            # FEAT-3048: backticked `ll-<tool> <sub> [--flag]` claim naming a
            # subcommand/flag the tool's argparse parser doesn't accept.
            "stale_cli_flag": [],
            # ENH-3247: same ### heading text repeated under one ## parent.
            "duplicate_heading": [],
            # ENH-3247: _Added by …:_ stub with no bullet before next heading/stub.
            "empty_provenance_stub": [],
            # ENH-3244: literal unfilled template placeholder still present in
            # its emitting section.
            "template_placeholders": [],
            # ENH-3256: recorded > **Selected:** decision whose rejected
            # option's discriminating identifiers still appear, unmarked, in
            # a directive section.
            "unapplied_decision": [],
            # BUG-3286: filename P<n>- prefix and frontmatter priority: both
            # present and disagreeing.
            "priority_drift": [],
            # ENH-3280: structured (section, identifier) projection of
            # unapplied_decision, for machine consumers.
            "unapplied_decision_detail": [],
            # ENH-2992: marker presence rides the same payload; not a gap, so
            # it does not affect the exit code above.
            "superseded_marker_count": 0,
        }

    def test_gapped_issue_json_output(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace("## Expected Behavior\nIt should not break.\n\n", "")
        _write_issue(format_check_dir, "P3-BUG-9107-test-bug.md", body)

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9107",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        data = json.loads(out)
        assert data["missing"] == ["Expected Behavior"]


# ---------------------------------------------------------------------------
# TestFormatCheckIssueNotFound
# ---------------------------------------------------------------------------


class TestFormatCheckIssueNotFound:
    """An unresolvable issue ID exits 1 with an error on stderr."""

    def test_not_found_exits_one(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = _invoke(
            ["ll-issues", "format-check", "BUG-9999", "--config", str(temp_project_dir)]
        )
        _, err = capsys.readouterr()

        assert result == 1
        assert "not found" in err.lower()


# ---------------------------------------------------------------------------
# TestFormatCheckFailOpen
# ---------------------------------------------------------------------------


class TestFormatCheckFailOpen:
    """An unresolved template (fail-open) exits 0 even though sections are missing."""

    def test_unresolved_template_exits_zero(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        sample_config: dict[str, Any],
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        empty_templates = tmp_path / "empty-templates"
        empty_templates.mkdir()

        config_override = {**sample_config}
        config_override["issues"] = {
            **sample_config.get("issues", {}),
            "templates_dir": str(empty_templates),
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(config_override))

        _write_issue(format_check_dir, "P3-BUG-9108-test-bug.md", "## Summary\nOnly Summary.")

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9108", "--config", str(temp_project_dir)]
        )

        assert result == 0


# ---------------------------------------------------------------------------
# TestFormatCheckProseDeps (FEAT-2849)
# ---------------------------------------------------------------------------


def _write_feature(issues_dir: Path, filename: str, body: str) -> Path:
    path = issues_dir / "features" / filename
    path.write_text(body)
    return path


class TestFormatCheckProseDeps:
    """prose_dep_drift / stale_prose_dep gap kinds (FEAT-2849)."""

    def test_prose_dep_on_active_issue_reports_drift(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_feature(
            format_check_dir,
            "P2-FEAT-9200-blocker.md",
            "---\nid: FEAT-9200\nstatus: open\n---\n\n# FEAT-9200: Blocker\n",
        )
        body = _CLEAN_BUG_BODY.replace(
            "id: BUG-9101",
            "id: BUG-9109",
        ).replace(
            "## Summary\nA real problem happens under specific conditions.",
            "## Summary\nDepends on FEAT-9200 for the underlying fix.",
        )
        _write_issue(format_check_dir, "P3-BUG-9109-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9109", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "prose_dep_drift: FEAT-9200" in out

    def test_prose_dep_on_done_issue_reports_stale(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_feature(
            format_check_dir,
            "P2-FEAT-9201-blocker.md",
            "---\nid: FEAT-9201\nstatus: done\n---\n\n# FEAT-9201: Blocker\n",
        )
        body = _CLEAN_BUG_BODY.replace(
            "id: BUG-9101",
            "id: BUG-9110",
        ).replace(
            "## Summary\nA real problem happens under specific conditions.",
            "## Summary\nBlocked by FEAT-9201 until it ships.",
        )
        _write_issue(format_check_dir, "P3-BUG-9110-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9110", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "stale_prose_dep: FEAT-9201" in out
        assert "prose_dep_drift" not in out

    def test_prose_dep_already_in_blocked_by_is_clean(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_feature(
            format_check_dir,
            "P2-FEAT-9202-blocker.md",
            "---\nid: FEAT-9202\nstatus: open\n---\n\n# FEAT-9202: Blocker\n",
        )
        body = _CLEAN_BUG_BODY.replace(
            "id: BUG-9101",
            "id: BUG-9111\nblocked_by:\n- FEAT-9202",
        ).replace(
            "## Summary\nA real problem happens under specific conditions.",
            "## Summary\nDepends on FEAT-9202 for the underlying fix.",
        )
        _write_issue(format_check_dir, "P3-BUG-9111-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9111", "--config", str(temp_project_dir)]
        )

        assert result == 0


# ---------------------------------------------------------------------------
# TestStaleFileRef (ENH-2983)
# ---------------------------------------------------------------------------

_EMPTY_GIT_LS_FILES = subprocess.CompletedProcess(
    args=["git", "ls-files", "-z"], returncode=0, stdout=b"", stderr=b""
)


class TestStaleFileRef:
    """stale_file_ref gap class (ENH-2983).

    ``temp_project_dir`` is a bare tmp dir with no ``.git`` ancestor, so
    ``build_ref_index()``'s real ``git ls-files`` call would fail open to an
    empty index anyway — these tests patch ``subprocess.run`` directly for
    determinism (and to make the "built at most once" assertion meaningful).
    """

    def _write_bug_with_ref(self, format_check_dir: Path, bug_id: str, ref_line: str) -> Path:
        filename = f"P3-{bug_id}-test-bug.md"
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", f"id: {bug_id}").replace(
            "## Current Behavior\nIt breaks in a specific way.",
            f"## Current Behavior\n{ref_line}",
        )
        return _write_issue(format_check_dir, filename, body)

    def test_all_reports_stale_file_ref_for_moved_path(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_bug_with_ref(
            format_check_dir,
            "BUG-9401",
            "See `scripts/little_loops/session_store.py` for details.",
        )

        with patch("little_loops.text_utils.subprocess.run", return_value=_EMPTY_GIT_LS_FILES):
            result = _invoke(
                ["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)]
            )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "stale_file_ref: scripts/little_loops/session_store.py" in out

    def test_all_states_not_git_tracked_predicate_not_missing(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """BUG-3194 Finding 3: the printed line must state the actual predicate
        (not git-tracked) rather than implying the file is missing/outdated —
        a present-but-gitignored file is a correct `stale_file_ref` verdict
        whose label alone misleads."""
        self._write_bug_with_ref(
            format_check_dir,
            "BUG-9403",
            "See `scripts/little_loops/session_store.py` for details.",
        )

        with patch("little_loops.text_utils.subprocess.run", return_value=_EMPTY_GIT_LS_FILES):
            result = _invoke(
                ["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)]
            )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "not git-tracked" in out

    def test_all_does_not_report_for_basenames_and_globs_only(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_bug_with_ref(
            format_check_dir,
            "BUG-9402",
            "See `SKILL.md` and skills/*/SKILL.md for details.",
        )

        with patch("little_loops.text_utils.subprocess.run", return_value=_EMPTY_GIT_LS_FILES):
            result = _invoke(
                ["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)]
            )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "stale_file_ref" not in out

    def test_single_id_json_reports_stale_file_ref(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_bug_with_ref(
            format_check_dir,
            "BUG-9403",
            "See `scripts/little_loops/session_store.py` for details.",
        )

        with patch("little_loops.text_utils.subprocess.run", return_value=_EMPTY_GIT_LS_FILES):
            result = _invoke(
                [
                    "ll-issues",
                    "format-check",
                    "BUG-9403",
                    "--format",
                    "json",
                    "--config",
                    str(temp_project_dir),
                ]
            )
        payload = json.loads(capsys.readouterr()[0])

        assert result == 1
        assert payload["stale_file_ref"] == ["scripts/little_loops/session_store.py"]

    def test_ref_index_built_once_per_all_invocation(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
    ) -> None:
        self._write_bug_with_ref(
            format_check_dir,
            "BUG-9501",
            "See `scripts/little_loops/session_store.py` for details.",
        )
        self._write_bug_with_ref(
            format_check_dir,
            "BUG-9502",
            "See `scripts/little_loops/other_gone.py` for details.",
        )

        with patch(
            "little_loops.text_utils.subprocess.run", return_value=_EMPTY_GIT_LS_FILES
        ) as mock_run:
            _invoke(["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)])

        # 2, not 1: ref_index (`git ls-files`) and the BUG-3063 C symbol reverse
        # index (also `git ls-files`, via build_symbol_index) are each built
        # exactly once per invocation, not once per issue.
        assert mock_run.call_count == 2

    def test_ref_index_built_once_per_single_id_invocation(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
    ) -> None:
        self._write_bug_with_ref(
            format_check_dir,
            "BUG-9404",
            "See `scripts/little_loops/session_store.py` for details.",
        )

        with patch(
            "little_loops.text_utils.subprocess.run", return_value=_EMPTY_GIT_LS_FILES
        ) as mock_run:
            _invoke(["ll-issues", "format-check", "BUG-9404", "--config", str(temp_project_dir)])

        # 2, not 1: ref_index and the BUG-3063 C symbol reverse index are each
        # built exactly once.
        assert mock_run.call_count == 2

    def test_ref_index_built_once_with_fix_apply_recheck(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
    ) -> None:
        """The --fix/--apply path re-runs check_format_gaps(); the index must not."""
        _write_feature(
            format_check_dir,
            "P2-FEAT-9503-blocker.md",
            "---\nid: FEAT-9503\nstatus: open\n---\n\n# FEAT-9503: Blocker\n",
        )
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9405").replace(
            "## Summary\nA real problem happens under specific conditions.",
            "## Summary\nDepends on FEAT-9503 for the underlying fix.",
        )
        _write_issue(format_check_dir, "P3-BUG-9405-test-bug.md", body)

        with patch(
            "little_loops.text_utils.subprocess.run", return_value=_EMPTY_GIT_LS_FILES
        ) as mock_run:
            _invoke(
                [
                    "ll-issues",
                    "format-check",
                    "BUG-9405",
                    "--fix",
                    "--apply",
                    "--config",
                    str(temp_project_dir),
                ]
            )

        # 2, not 1: ref_index and the BUG-3063 C symbol reverse index are each
        # built exactly once, even across the --fix/--apply recheck.
        assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# TestAmbiguousFileRef (ENH-2999)
# ---------------------------------------------------------------------------

_AMBIGUOUS_GIT_LS_FILES = subprocess.CompletedProcess(
    args=["git", "ls-files", "-z"],
    returncode=0,
    stdout=b"scripts/little_loops/pkg1/dir/utils.py\0scripts/little_loops/pkg2/dir/utils.py\0",
    stderr=b"",
)


class TestAmbiguousFileRef:
    """``ambiguous_file_ref`` gap class (ENH-2999).

    A reference whose suffix matches more than one tracked file is reported
    under its own class, distinct from ``stale_file_ref`` — the file was not
    deleted or moved, the reference just lacks enough path prefix to pick one
    of several real matches.
    """

    def _write_bug_with_ref(self, format_check_dir: Path, bug_id: str, ref_line: str) -> Path:
        filename = f"P3-{bug_id}-test-bug.md"
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", f"id: {bug_id}").replace(
            "## Current Behavior\nIt breaks in a specific way.",
            f"## Current Behavior\n{ref_line}",
        )
        return _write_issue(format_check_dir, filename, body)

    def test_all_reports_ambiguous_not_stale(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_bug_with_ref(
            format_check_dir,
            "BUG-9601",
            "See `dir/utils.py` for details.",
        )

        with patch("little_loops.text_utils.subprocess.run", return_value=_AMBIGUOUS_GIT_LS_FILES):
            result = _invoke(
                ["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)]
            )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "stale_file_ref" not in out
        assert (
            "ambiguous_file_ref: dir/utils.py (2: scripts/little_loops/pkg1/dir/utils.py, "
            "scripts/little_loops/pkg2/dir/utils.py)" in out
        )

    def test_single_id_json_reports_ambiguous_file_ref(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_bug_with_ref(
            format_check_dir,
            "BUG-9602",
            "See `dir/utils.py` for details.",
        )

        with patch("little_loops.text_utils.subprocess.run", return_value=_AMBIGUOUS_GIT_LS_FILES):
            result = _invoke(
                [
                    "ll-issues",
                    "format-check",
                    "BUG-9602",
                    "--format",
                    "json",
                    "--config",
                    str(temp_project_dir),
                ]
            )
        payload = json.loads(capsys.readouterr()[0])

        assert result == 1
        assert payload["stale_file_ref"] == []
        assert payload["ambiguous_file_ref"] == [
            "dir/utils.py (2: scripts/little_loops/pkg1/dir/utils.py, "
            "scripts/little_loops/pkg2/dir/utils.py)"
        ]

    def test_more_than_three_candidates_are_elided(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The count is always shown in full; candidate paths cap at three plus a marker."""
        self._write_bug_with_ref(
            format_check_dir,
            "BUG-9603",
            "See `agents/openai.yaml` for details.",
        )
        many_matches = subprocess.CompletedProcess(
            args=["git", "ls-files", "-z"],
            returncode=0,
            stdout=b"\0".join(f"skills/skill{i}/agents/openai.yaml".encode() for i in range(5))
            + b"\0",
            stderr=b"",
        )

        with patch("little_loops.text_utils.subprocess.run", return_value=many_matches):
            result = _invoke(
                [
                    "ll-issues",
                    "format-check",
                    "BUG-9603",
                    "--format",
                    "json",
                    "--config",
                    str(temp_project_dir),
                ]
            )
        payload = json.loads(capsys.readouterr()[0])

        assert result == 1
        assert len(payload["ambiguous_file_ref"]) == 1
        entry = payload["ambiguous_file_ref"][0]
        assert entry.startswith("agents/openai.yaml (5: ")
        assert entry.endswith(", …)")
        assert entry.count("skills/skill") == 3


# ---------------------------------------------------------------------------
# TestMissingBehaviorParity (ENH-3045)
# ---------------------------------------------------------------------------

_RESOLVED_GIT_LS_FILES = subprocess.CompletedProcess(
    args=["git", "ls-files", "-z"],
    returncode=0,
    stdout=b"scripts/little_loops/session_store.py\0",
    stderr=b"",
)


class TestMissingBehaviorParity:
    """``missing_behavior_parity`` gap class (ENH-3045).

    Fires when a resolved file ref in Summary/Proposed Solution/Files to
    Modify shares a line with a replacement keyword and no ``### Behavior
    Parity`` section exists; suppressed by the escape hatch or by scope.
    """

    def _write_bug_with_summary(self, format_check_dir: Path, bug_id: str, summary: str) -> Path:
        filename = f"P3-{bug_id}-test-bug.md"
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", f"id: {bug_id}").replace(
            "## Summary\nA real problem happens under specific conditions.",
            f"## Summary\n{summary}",
        )
        return _write_issue(format_check_dir, filename, body)

    def test_fires_on_resolved_ref_with_replacement_keyword_same_line(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_bug_with_summary(
            format_check_dir,
            "BUG-9701",
            "This deletes `scripts/little_loops/session_store.py` entirely.",
        )

        with patch("little_loops.text_utils.subprocess.run", return_value=_RESOLVED_GIT_LS_FILES):
            result = _invoke(
                ["ll-issues", "format-check", "BUG-9701", "--config", str(temp_project_dir)]
            )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "missing_behavior_parity: scripts/little_loops/session_store.py" in out

    def test_no_gap_without_replacement_keyword(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_bug_with_summary(
            format_check_dir,
            "BUG-9702",
            "This uses `scripts/little_loops/session_store.py` as a helper.",
        )

        with patch("little_loops.text_utils.subprocess.run", return_value=_RESOLVED_GIT_LS_FILES):
            result = _invoke(
                ["ll-issues", "format-check", "BUG-9702", "--config", str(temp_project_dir)]
            )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "missing_behavior_parity" not in out

    def test_no_gap_when_behavior_parity_section_present(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = (
            _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9703")
            .replace(
                "## Summary\nA real problem happens under specific conditions.",
                "## Summary\nThis deletes `scripts/little_loops/session_store.py` entirely.",
            )
            .replace(
                "## Impact",
                "### Behavior Parity\n"
                "| Artifact | Behavior | Disposition | Notes |\n"
                "|---|---|---|---|\n"
                "| `scripts/little_loops/session_store.py` | stores sessions | DROPPED | n/a |\n"
                "\n## Impact",
            )
        )
        _write_issue(format_check_dir, "P3-BUG-9703-test-bug.md", body)

        with patch("little_loops.text_utils.subprocess.run", return_value=_RESOLVED_GIT_LS_FILES):
            result = _invoke(
                ["ll-issues", "format-check", "BUG-9703", "--config", str(temp_project_dir)]
            )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "missing_behavior_parity" not in out

    def test_no_gap_with_escape_hatch(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace(
            "id: BUG-9101", "id: BUG-9704\nbehavior_parity_not_applicable: true"
        ).replace(
            "## Summary\nA real problem happens under specific conditions.",
            "## Summary\nThis deletes `scripts/little_loops/session_store.py` entirely.",
        )
        _write_issue(format_check_dir, "P3-BUG-9704-test-bug.md", body)

        with patch("little_loops.text_utils.subprocess.run", return_value=_RESOLVED_GIT_LS_FILES):
            result = _invoke(
                ["ll-issues", "format-check", "BUG-9704", "--config", str(temp_project_dir)]
            )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "missing_behavior_parity" not in out

    def test_no_gap_outside_scope_sections(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A replacement keyword in Current Behavior (not in scope) never fires."""
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9705").replace(
            "## Current Behavior\nIt breaks in a specific way.",
            "## Current Behavior\nThis deletes `scripts/little_loops/session_store.py`.",
        )
        _write_issue(format_check_dir, "P3-BUG-9705-test-bug.md", body)

        with patch("little_loops.text_utils.subprocess.run", return_value=_RESOLVED_GIT_LS_FILES):
            result = _invoke(
                ["ll-issues", "format-check", "BUG-9705", "--config", str(temp_project_dir)]
            )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "missing_behavior_parity" not in out

    def test_single_id_json_reports_missing_behavior_parity(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_bug_with_summary(
            format_check_dir,
            "BUG-9706",
            "This deletes `scripts/little_loops/session_store.py` entirely.",
        )

        with patch("little_loops.text_utils.subprocess.run", return_value=_RESOLVED_GIT_LS_FILES):
            result = _invoke(
                [
                    "ll-issues",
                    "format-check",
                    "BUG-9706",
                    "--format",
                    "json",
                    "--config",
                    str(temp_project_dir),
                ]
            )
        payload = json.loads(capsys.readouterr()[0])

        assert result == 1
        assert payload["missing_behavior_parity"] == ["scripts/little_loops/session_store.py"]


# ---------------------------------------------------------------------------
# TestSoftDepHardEdge (ENH-3046)
# ---------------------------------------------------------------------------


class TestSoftDepHardEdge:
    """``soft_dep_hard_edge`` gap class (ENH-3046).

    Fires when an ID in ``blocked_by``/``depends_on`` shares a blank-line-
    delimited paragraph with soft-dependency language ("soft dep",
    "optional", "nice to have", "has not landed"). No suppression escape
    hatch.
    """

    def _write_bug_with_blocker(
        self,
        format_check_dir: Path,
        bug_id: str,
        summary: str,
        *,
        blocked_by: str = "FEAT-9300",
    ) -> Path:
        filename = f"P3-{bug_id}-test-bug.md"
        body = _CLEAN_BUG_BODY.replace(
            "id: BUG-9101",
            f"id: {bug_id}\nblocked_by:\n- {blocked_by}",
        ).replace(
            "## Summary\nA real problem happens under specific conditions.",
            f"## Summary\n{summary}",
        )
        return _write_issue(format_check_dir, filename, body)

    def test_fires_on_soft_language_same_paragraph(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_feature(
            format_check_dir,
            "P2-FEAT-9300-blocker.md",
            "---\nid: FEAT-9300\nstatus: open\n---\n\n# FEAT-9300: Blocker\n",
        )
        self._write_bug_with_blocker(
            format_check_dir,
            "BUG-9901",
            "Soft dep on FEAT-9300 — do not implement here. "
            "If FEAT-9300 has not landed, this still ships proposal-only.",
        )

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9901", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "soft_dep_hard_edge: FEAT-9300" in out

    def test_no_gap_without_soft_language(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_feature(
            format_check_dir,
            "P2-FEAT-9301-blocker.md",
            "---\nid: FEAT-9301\nstatus: open\n---\n\n# FEAT-9301: Blocker\n",
        )
        self._write_bug_with_blocker(
            format_check_dir,
            "BUG-9902",
            "This requires FEAT-9301 to ship first.",
            blocked_by="FEAT-9301",
        )

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9902", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "soft_dep_hard_edge" not in out

    def test_no_gap_when_soft_language_in_different_paragraph(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Soft phrase in a different paragraph than the ID must not fire."""
        _write_feature(
            format_check_dir,
            "P2-FEAT-9302-blocker.md",
            "---\nid: FEAT-9302\nstatus: open\n---\n\n# FEAT-9302: Blocker\n",
        )
        self._write_bug_with_blocker(
            format_check_dir,
            "BUG-9903",
            "This requires FEAT-9302 to ship first.\n\n"
            "Some other paragraph mentions this is optional in general.",
            blocked_by="FEAT-9302",
        )

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9903", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "soft_dep_hard_edge" not in out

    def test_single_id_json_reports_soft_dep_hard_edge(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_feature(
            format_check_dir,
            "P2-FEAT-9303-blocker.md",
            "---\nid: FEAT-9303\nstatus: open\n---\n\n# FEAT-9303: Blocker\n",
        )
        self._write_bug_with_blocker(
            format_check_dir,
            "BUG-9904",
            "Soft dep on FEAT-9303 — nice to have but not required.",
            blocked_by="FEAT-9303",
        )

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9904",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        payload = json.loads(capsys.readouterr()[0])

        assert result == 1
        assert payload["soft_dep_hard_edge"] == ["FEAT-9303"]


# ---------------------------------------------------------------------------
# TestUnmarkedSupersededDirective (ENH-2995)
# ---------------------------------------------------------------------------


class TestUnmarkedSupersededDirective:
    """``unmarked_superseded_directive`` gap class (ENH-2995).

    Flags an issue whose ``### Codebase Research Findings`` block contains a
    closed-list correction phrase while none of the three directive sections
    (``## Implementation Steps``, ``### Files to Modify``,
    ``## Acceptance Criteria``) carries a ``⚠ Superseded`` marker.
    """

    def _write_bug_with_steps(self, format_check_dir: Path, bug_id: str, steps_block: str) -> Path:
        filename = f"P3-{bug_id}-test-bug.md"
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", f"id: {bug_id}") + "\n\n" + steps_block
        return _write_issue(format_check_dir, filename, body)

    def test_all_reports_correction_without_marker(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        steps_block = (
            "## Implementation Steps\n\n"
            "1. Add `pending_file` to the loop's `context:` block\n\n"
            "### Codebase Research Findings\n\n"
            "_Added by `/ll:refine-issue`:_\n\n"
            "- Step 1 is wrong — context template resolution omits this field.\n"
        )
        self._write_bug_with_steps(format_check_dir, "BUG-9601", steps_block)

        result = _invoke(["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 1
        assert "unmarked_superseded_directive: P3-BUG-9601-test-bug.md" in out

    def test_marked_line_is_not_flagged(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        steps_block = (
            "## Implementation Steps\n\n"
            "1. Add `pending_file` to the loop's `context:` block\n"
            "   > ⚠ Superseded — omit entirely; see § Codebase Research Findings"
            " under Implementation Steps\n\n"
            "### Codebase Research Findings\n\n"
            "_Added by `/ll:refine-issue`:_\n\n"
            "- Step 1 is wrong — context template resolution omits this field.\n"
        )
        self._write_bug_with_steps(format_check_dir, "BUG-9602", steps_block)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9602", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "unmarked_superseded_directive" not in out

    def test_correction_in_preserved_section_not_flagged(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Correction phrasing outside a `### Codebase Research Findings` block —
        e.g. plain prose in `## Summary` — must not trigger the gap class. Only
        the findings block itself is scanned."""
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9603").replace(
            "## Summary\nA real problem happens under specific conditions.",
            "## Summary\nA real problem happens under specific conditions. "
            "This claim is wrong per the current codebase.",
        )
        _write_issue(format_check_dir, "P3-BUG-9603-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9603", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "unmarked_superseded_directive" not in out

    def test_single_id_json_reports_unmarked_superseded_directive(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        steps_block = (
            "## Implementation Steps\n\n"
            "1. Add `pending_file` to the loop's `context:` block\n\n"
            "### Codebase Research Findings\n\n"
            "_Added by `/ll:refine-issue`:_\n\n"
            "- Step 1 is wrong — context template resolution omits this field.\n"
        )
        self._write_bug_with_steps(format_check_dir, "BUG-9604", steps_block)

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9604",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        payload = json.loads(capsys.readouterr()[0])

        assert result == 1
        assert payload["unmarked_superseded_directive"] == ["P3-BUG-9604-test-bug.md"]


class TestSupersededMarkerCountKey(TestUnmarkedSupersededDirective):
    """ENH-2992: the single-issue ``--format json`` payload also carries
    ``superseded_marker_count`` — marker *presence*, the inverse of the
    ``unmarked_superseded_directive`` gap class above. ``autodev.yaml``'s
    ``check_reconcile_needed`` reads this key as its contradiction predicate.

    Inherits the fixture helpers from the gap-class suite; only the JSON key
    under test differs.
    """

    def _json_for(self, temp_project_dir: Path, bug_id: str, capsys: Any) -> dict[str, Any]:
        result = _invoke(
            [
                "ll-issues",
                "format-check",
                bug_id,
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        payload = json.loads(capsys.readouterr()[0])
        assert isinstance(payload, dict)
        return {"exit": result, **payload}

    def test_marker_count_zero_when_unmarked(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        steps_block = (
            "## Implementation Steps\n\n"
            "1. Add `pending_file` to the loop's `context:` block\n\n"
            "### Codebase Research Findings\n\n"
            "_Added by `/ll:refine-issue`:_\n\n"
            "- Step 1 is wrong — context template resolution omits this field.\n"
        )
        self._write_bug_with_steps(format_check_dir, "BUG-9605", steps_block)

        payload = self._json_for(temp_project_dir, "BUG-9605", capsys)

        assert payload["superseded_marker_count"] == 0

    def test_marker_count_counts_marked_directive_line(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        steps_block = (
            "## Implementation Steps\n\n"
            "1. Add `pending_file` to the loop's `context:` block\n"
            "   > ⚠ Superseded — omit entirely; see § Codebase Research Findings\n\n"
            "### Codebase Research Findings\n\n"
            "_Added by `/ll:refine-issue`:_\n\n"
            "- Step 1 is wrong — context template resolution omits this field.\n"
        )
        self._write_bug_with_steps(format_check_dir, "BUG-9606", steps_block)

        payload = self._json_for(temp_project_dir, "BUG-9606", capsys)

        assert payload["superseded_marker_count"] == 1
        # Marker presence is not itself a gap — a marked issue is still
        # structurally compliant and must exit 0.
        assert payload["exit"] == 0


# ---------------------------------------------------------------------------
# TestFormatCheckAll (FEAT-2850)
# ---------------------------------------------------------------------------


class TestFormatCheckAll:
    """Repo-wide sweep mode via ``--all`` (FEAT-2850)."""

    def test_no_issue_id_and_no_all_errors(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = _invoke(["ll-issues", "format-check", "--config", str(temp_project_dir)])
        _, err = capsys.readouterr()

        assert result == 1
        assert "--all" in err

    def test_all_clean_exits_zero(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_issue(
            format_check_dir,
            "P3-BUG-9301-test-bug.md",
            _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9301"),
        )

        result = _invoke(["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 0
        assert "structurally compliant" in out

    def test_all_reports_gapped_issue_only(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_issue(
            format_check_dir,
            "P3-BUG-9302-test-bug.md",
            _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9302"),
        )
        gapped = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9303").replace(
            "## Expected Behavior\nIt should not break.\n\n", ""
        )
        _write_issue(format_check_dir, "P3-BUG-9303-test-bug.md", gapped)

        result = _invoke(["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 1
        assert "BUG-9303" in out
        assert "missing: Expected Behavior" in out
        assert "BUG-9302" not in out

    def test_all_json_output(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        gapped = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9304").replace(
            "## Expected Behavior\nIt should not break.\n\n", ""
        )
        _write_issue(format_check_dir, "P3-BUG-9304-test-bug.md", gapped)

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "--all",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        data = json.loads(out)
        assert data["BUG-9304"]["missing"] == ["Expected Behavior"]


# ---------------------------------------------------------------------------
# TestFormatCheckFix (FEAT-2851)
# ---------------------------------------------------------------------------


class TestFormatCheckFix:
    """``--fix``/``--apply`` backfills blocked_by from prose_dep_drift via link.py."""

    def _write_drifting_bug(self, format_check_dir: Path, bug_id: str, filename: str) -> Path:
        _write_feature(
            format_check_dir,
            "P2-FEAT-9500-blocker.md",
            "---\nid: FEAT-9500\nstatus: open\n---\n\n# FEAT-9500: Blocker\n",
        )
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", f"id: {bug_id}").replace(
            "## Summary\nA real problem happens under specific conditions.",
            "## Summary\nDepends on FEAT-9500 for the underlying fix.",
        )
        return _write_issue(format_check_dir, filename, body)

    def test_fix_without_apply_previews_and_does_not_write(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_drifting_bug(format_check_dir, "BUG-9401", "P3-BUG-9401-test-bug.md")
        before = path.read_text()

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9401", "--fix", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "would link (dry-run)" in out
        assert "prose_dep_drift: FEAT-9500" in out
        assert path.read_text() == before

    def test_fix_apply_writes_blocked_by_and_clears_drift(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_drifting_bug(format_check_dir, "BUG-9402", "P3-BUG-9402-test-bug.md")

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9402",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert "linked" in out
        assert "blocked_by" in path.read_text()
        assert "FEAT-9500" in path.read_text()
        assert result == 0
        assert "prose_dep_drift" not in out

    def test_fix_apply_is_idempotent(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_drifting_bug(format_check_dir, "BUG-9403", "P3-BUG-9403-test-bug.md")

        _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9403",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()
        after_first = path.read_text()

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9403",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "prose_dep_drift" not in out
        assert path.read_text() == after_first

    def test_fix_all_mode_applies_across_sweep(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_drifting_bug(format_check_dir, "BUG-9404", "P3-BUG-9404-test-bug.md")

        _invoke(
            [
                "ll-issues",
                "format-check",
                "--all",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert "BUG-9404" not in out or "prose_dep_drift" not in out.split("BUG-9404:")[-1]
        assert "blocked_by" in path.read_text()
        assert "FEAT-9500" in path.read_text()


# ---------------------------------------------------------------------------
# TestFormatCheckDuplicateHeadingFix (ENH-3247)
# ---------------------------------------------------------------------------


class TestFormatCheckDuplicateHeadingFix:
    """``--fix``/``--apply`` collapses duplicate ``###`` headings under one ``##``."""

    def _write_dup_heading_bug(self, format_check_dir: Path, bug_id: str, filename: str) -> Path:
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", f"id: {bug_id}")
        body += (
            "\n\n## Integration Map\n\n"
            "### Files to Modify\n- a.py\n\n"
            "### Dependent Files (Callers/Importers)\n- b.py\n\n"
            "### Dependent Files (Callers/Importers)\n- c.py\n"
        )
        return _write_issue(format_check_dir, filename, body)

    def test_detected_as_duplicate_heading_gap(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_dup_heading_bug(format_check_dir, "BUG-9410", "P3-BUG-9410-test-bug.md")

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9410", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "duplicate_heading: Integration Map > Dependent Files" in out

    def test_fix_without_apply_previews_and_does_not_write(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_dup_heading_bug(format_check_dir, "BUG-9411", "P3-BUG-9411-test-bug.md")
        before = path.read_text()

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9411", "--fix", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "would collapse" in out
        assert path.read_text() == before

    def test_fix_apply_collapses_and_is_idempotent(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_dup_heading_bug(format_check_dir, "BUG-9412", "P3-BUG-9412-test-bug.md")

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9412",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()
        after_first = path.read_text()

        assert result == 0
        assert "duplicate_heading" not in out
        assert after_first.count("### Dependent Files (Callers/Importers)") == 1
        assert "- b.py" in after_first
        assert "- c.py" in after_first

        result2 = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9412",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()

        assert result2 == 0
        assert path.read_text() == after_first

    def test_sweep_mode_does_not_write_body(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_dup_heading_bug(format_check_dir, "BUG-9413", "P3-BUG-9413-test-bug.md")
        before = path.read_text()

        _invoke(
            [
                "ll-issues",
                "format-check",
                "--all",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()

        assert path.read_text() == before

    def test_fence_safety_leaves_file_byte_identical(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9414")
        body += (
            "\n\n## Example\n\n"
            "```markdown\n"
            "## Integration Map\n\n"
            "### Files to Modify\n- a.py\n\n"
            "### Files to Modify\n- b.py\n"
            "```\n\n"
            "### Real Heading\n- content\n"
        )
        path = _write_issue(format_check_dir, "P3-BUG-9414-test-bug.md", body)
        before = path.read_text()

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9414",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()

        assert path.read_text() == before
        assert result == 0


# ---------------------------------------------------------------------------
# TestFormatCheckEmptyProvenanceStubFix (ENH-3247)
# ---------------------------------------------------------------------------


class TestFormatCheckEmptyProvenanceStubFix:
    """``--fix``/``--apply`` deletes empty ``_Added by …:_`` provenance stubs."""

    _STUB = "_Added by `/ll:refine-issue` — {date} — based on codebase analysis:_"

    def _write_stub_bug(self, format_check_dir: Path, bug_id: str, filename: str) -> Path:
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", f"id: {bug_id}")
        body += (
            "\n\n## Integration Map\n\n"
            "### Codebase Research Findings\n\n"
            f"{self._STUB.format(date='2026-08-10')}\n\n"
            f"{self._STUB.format(date='2026-08-11')}\n\n"
            f"{self._STUB.format(date='2026-08-12')}\n\n"
            "- a real finding\n"
        )
        return _write_issue(format_check_dir, filename, body)

    def test_detected_as_empty_provenance_stub_gap(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_stub_bug(format_check_dir, "BUG-9420", "P3-BUG-9420-test-bug.md")

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9420", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "empty_provenance_stub:" in out

    def test_fix_without_apply_previews_and_does_not_write(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_stub_bug(format_check_dir, "BUG-9421", "P3-BUG-9421-test-bug.md")
        before = path.read_text()

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9421", "--fix", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "would delete" in out
        assert path.read_text() == before

    def test_fix_apply_deletes_and_is_idempotent(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_stub_bug(format_check_dir, "BUG-9422", "P3-BUG-9422-test-bug.md")

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9422",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()
        after_first = path.read_text()

        assert result == 0
        assert "empty_provenance_stub" not in out
        assert after_first.count("_Added by") == 1
        assert "- a real finding" in after_first
        # No three-blank-line gap left behind by collapsing two adjacent stubs.
        assert "\n\n\n" not in after_first

        result2 = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9422",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()

        assert result2 == 0
        assert path.read_text() == after_first

    def test_sweep_mode_does_not_write_body(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_stub_bug(format_check_dir, "BUG-9423", "P3-BUG-9423-test-bug.md")
        before = path.read_text()

        _invoke(
            [
                "ll-issues",
                "format-check",
                "--all",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()

        assert path.read_text() == before


# ---------------------------------------------------------------------------
# TestFormatCheckTemplatePlaceholdersDetection (ENH-3244)
# ---------------------------------------------------------------------------


class TestFormatCheckTemplatePlaceholdersDetection:
    """``template_placeholders`` gap class: literal unfilled template debris.

    A ``--fix`` handler is registered for this class (ENH-3248), but it
    covers only the four frontmatter-derivable tokens
    (``_TEMPLATE_PLACEHOLDER_FIXABLE``) — every other placeholder (judgment
    assessments, research-shaped prose like the ``TBD -`` tokens exercised
    below) needs content the tool cannot invent and is left untouched. See
    ``TestFormatCheckTemplatePlaceholdersFix`` for the fixer's own coverage.
    """

    def _write_placeholder_bug(
        self, format_check_dir: Path, bug_id: str, filename: str, extra: str
    ) -> Path:
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", f"id: {bug_id}") + extra
        return _write_issue(format_check_dir, filename, body)

    def test_detected_as_template_placeholders_gap(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_placeholder_bug(
            format_check_dir,
            "BUG-9440",
            "P3-BUG-9440-test-bug.md",
            "\n\n## Integration Map\n\n### Files to Modify\n- TBD - requires codebase analysis\n",
        )

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9440", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "template_placeholders: Integration Map: TBD - requires codebase analysis" in out

    def test_json_output_carries_template_placeholders(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._write_placeholder_bug(
            format_check_dir,
            "BUG-9441",
            "P3-BUG-9441-test-bug.md",
            "\n\n## Implementation Steps\n\n1. [Major phase 1]\n2. Real step.\n",
        )

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9441",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        data = json.loads(out)
        assert data["template_placeholders"] == ["Implementation Steps: [Major phase 1]"]

    def test_research_shaped_token_not_repaired(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--fix must not touch a research-shaped token (ENH-3248: out of the
        fixer's frontmatter-derivable allowlist — needs content the tool
        cannot invent)."""
        path = self._write_placeholder_bug(
            format_check_dir,
            "BUG-9442",
            "P3-BUG-9442-test-bug.md",
            "\n\n## Integration Map\n\n### Files to Modify\n- TBD - requires codebase analysis\n",
        )
        before = path.read_text()

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9442",
                "--fix",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "template_placeholders" in out
        assert path.read_text() == before


# ---------------------------------------------------------------------------
# TestFormatCheckTemplatePlaceholdersFix (ENH-3248 — frontmatter-derivable tokens)
# ---------------------------------------------------------------------------


class TestFormatCheckTemplatePlaceholdersFix:
    """``--fix``/``--apply`` fills only the four frontmatter-derivable
    ``template_placeholders`` tokens; every other token is untouched."""

    def _write_placeholder_bug(
        self, format_check_dir: Path, bug_id: str, filename: str, *, priority: str = "P2"
    ) -> Path:
        body = "\n".join(
            [
                "---",
                f"id: {bug_id}",
                "type: BUG",
                f"priority: {priority}",
                "discovered_date: '2026-08-17'",
                "status: open",
                "---",
                "",
                f"# {bug_id}: Test bug",
                "",
                "## Summary",
                "A real problem happens under specific conditions.",
                "",
                "## Current Behavior",
                "It breaks in a specific way.",
                "",
                "## Expected Behavior",
                "It should not break.",
                "",
                "## Steps to Reproduce",
                "1. Do the thing.",
                "2. Observe failure.",
                "",
                "## Impact",
                "- **Priority**: [P0-P5] - [Justification]",
                "- **Effort**: [Small/Medium/Large] - [Justification]",
                "- **Risk**: [Low/Medium/High] - [Justification]",
                "- **Breaking Change**: [Yes/No]",
                "",
                "## Status",
                "**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]",
            ]
        )
        return _write_issue(format_check_dir, filename, body)

    def test_fix_apply_fills_derivable_tokens_and_leaves_judgment_tokens(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_placeholder_bug(
            format_check_dir, "BUG-9450", "P3-BUG-9450-test-bug.md", priority="P3"
        )

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9450",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()
        after = path.read_text()

        # Derivable tokens filled from frontmatter.
        assert "- **Priority**: P3 - [Justification]" in after
        assert "**Open** | Created: 2026-08-17 | Priority: P3" in after
        # Judgment tokens (not a pure function of frontmatter) untouched.
        assert "[Small/Medium/Large]" in after
        assert "[Low/Medium/High]" in after
        assert "[Yes/No]" in after
        assert "[Justification]" in after
        # Report still exits 1 — judgment tokens remain unfilled gaps.
        assert result == 1

    def test_fix_apply_sources_priority_from_resolved_value_not_stale_frontmatter(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """BUG-3286 Fix-order rule: a drifted file (filename prefix disagrees
        with frontmatter `priority:`) fills the body from the *resolved*
        (filename-wins) value, never the stale frontmatter one — otherwise
        `--fix` would bake drift into prose where no lint inspects it."""
        path = self._write_placeholder_bug(
            format_check_dir, "BUG-9455", "P3-BUG-9455-test-bug.md", priority="P1"
        )

        _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9455",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()
        after = path.read_text()

        assert "- **Priority**: P3 - [Justification]" in after
        assert "**Open** | Created: 2026-08-17 | Priority: P3" in after
        assert "- **Priority**: P1" not in after
        assert "Priority: P1" not in after

    def test_fix_without_apply_previews_and_does_not_write(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_placeholder_bug(format_check_dir, "BUG-9451", "P3-BUG-9451-test-bug.md")
        before = path.read_text()

        _invoke(
            ["ll-issues", "format-check", "BUG-9451", "--fix", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert "would fill" in out
        assert path.read_text() == before

    def test_fix_apply_is_idempotent(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_placeholder_bug(format_check_dir, "BUG-9452", "P3-BUG-9452-test-bug.md")

        _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9452",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()
        after_first = path.read_text()

        _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9452",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()

        assert path.read_text() == after_first

    def test_documenting_prose_naming_placeholder_is_untouched(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A section that quotes its own placeholder as inline-code documentation
        (e.g. `` `[P0-P5]` ``) is masked, matching detection's own masking rule."""
        path = self._write_placeholder_bug(format_check_dir, "BUG-9453", "P3-BUG-9453-test-bug.md")
        content = path.read_text()
        content = content.replace(
            "- **Priority**: [P0-P5] - [Justification]",
            "- **Priority**: `[P0-P5]` - [Justification]",
        )
        path.write_text(content)

        _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9453",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()
        after = path.read_text()

        assert "`[P0-P5]`" in after

    def test_sweep_mode_does_not_write_body(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_placeholder_bug(format_check_dir, "BUG-9454", "P3-BUG-9454-test-bug.md")
        before = path.read_text()

        _invoke(
            [
                "ll-issues",
                "format-check",
                "--all",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()

        assert path.read_text() == before


class TestTemplatePlaceholderFixableAllowlistInvariant:
    """Token-granularity capability invariant (ENH-3248 Tests section).

    A class-level ``routed-set ⊆ _REPAIR_DISPATCH.keys()`` check is
    necessary but not sufficient once ``template_placeholders`` is
    registered with a *partial* fixer — the routed granularity is the
    token, so the invariant is enforced at token granularity here: every
    allowlisted ``"{section}: {token}"`` entry must actually be a token
    ``_template_placeholder_patterns`` emits for at least one issue type,
    and every allowlisted frontmatter field must exist on a real issue.
    """

    def test_allowlist_tokens_are_real_template_tokens(self) -> None:
        from little_loops.cli.issues.format_check import _TEMPLATE_PLACEHOLDER_FIXABLE
        from little_loops.issue_parser import _template_placeholder_patterns

        all_tokens: set[str] = set()
        for issue_type in ("BUG", "ENH", "FEAT", "EPIC"):
            for section, tokens in _template_placeholder_patterns(issue_type).items():
                for token in tokens:
                    all_tokens.add(f"{section}: {token}")

        missing = set(_TEMPLATE_PLACEHOLDER_FIXABLE) - all_tokens
        assert not missing, f"allowlisted entries not emitted by any type's template: {missing}"

    def test_allowlist_frontmatter_fields_exist_on_a_real_issue(self) -> None:
        from little_loops.cli.issues.format_check import _TEMPLATE_PLACEHOLDER_FIXABLE
        from little_loops.frontmatter import parse_frontmatter

        real_issue = "\n".join(
            [
                "---",
                "id: BUG-9101",
                "type: BUG",
                "priority: P2",
                "discovered_date: '2026-08-17'",
                "status: open",
                "---",
                "",
                "# BUG-9101: Test bug",
            ]
        )
        fm = parse_frontmatter(real_issue)
        fields = set(_TEMPLATE_PLACEHOLDER_FIXABLE.values())
        missing = fields - set(fm)
        assert not missing, f"allowlisted fields absent from a real issue's frontmatter: {missing}"

    def test_allowlist_is_not_in_sweep_safe_repairs(self) -> None:
        from little_loops.cli.issues.format_check import _SWEEP_SAFE_REPAIRS

        assert "template_placeholders" not in _SWEEP_SAFE_REPAIRS, (
            "template_placeholders is body-rewriting and must stay single-issue-mode only"
        )


# ---------------------------------------------------------------------------
# TestFormatCheckDuplicateFindingsFix (ENH-3247 — dispatch table N=3)
# ---------------------------------------------------------------------------


class TestFormatCheckDuplicateFindingsFix:
    """``duplicate_findings_block`` registered into the new --fix dispatch table."""

    def _write_stacked_findings_bug(
        self, format_check_dir: Path, bug_id: str, filename: str
    ) -> Path:
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", f"id: {bug_id}")
        body += (
            "\n\n## Integration Map\n\n"
            "### Codebase Research Findings\n\n"
            "_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_\n\n"
            "- one\n\n"
            "### Codebase Research Findings\n\n"
            "_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_\n\n"
            "- two\n"
        )
        return _write_issue(format_check_dir, filename, body)

    def test_fix_apply_collapses_stacked_findings_and_is_idempotent(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        path = self._write_stacked_findings_bug(
            format_check_dir, "BUG-9430", "P3-BUG-9430-test-bug.md"
        )

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9430",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()
        after_first = path.read_text()

        assert result == 0
        assert after_first.count("### Codebase Research Findings") == 1
        assert "- one" in after_first
        assert "- two" in after_first

        result2 = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9430",
                "--fix",
                "--apply",
                "--config",
                str(temp_project_dir),
            ]
        )
        capsys.readouterr()

        assert result2 == 0
        assert path.read_text() == after_first


# ---------------------------------------------------------------------------
# TestFormatCheckProgramDesign (ENH-2852)
# ---------------------------------------------------------------------------


class TestFormatCheckProgramDesign:
    """The Program Design gate reaches the CLI, and is off in unstamped projects."""

    @staticmethod
    def _arm(temp_project_dir: Path, stamp_date: str) -> None:
        (temp_project_dir / ".ll" / "program-design-cutover.json").write_text(
            json.dumps({"sha": "0" * 40, "date": stamp_date})
        )

    def test_unstamped_project_reports_no_program_design_gap(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Fail open: the clean-bug fixture has no `## Program Design` and still passes."""
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9601")
        _write_issue(format_check_dir, "P3-BUG-9601-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9601", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0, out
        assert "Program Design" not in out

    def test_nonspecific_section_surfaces_in_text_output(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._arm(temp_project_dir, "2020-01-01")
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9602").replace(
            "## Status\nopen",
            "## Program Design\n\n### Types\n\nSome prose about the shape.\n\n"
            "### Signatures\n\nA function will be added.\n\n"
            "### Call Path\n\nThe CLI reaches the parser somehow.\n\n## Status\nopen",
        )
        _write_issue(format_check_dir, "P3-BUG-9602-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9602", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "program_design_nonspecific: Program Design:" in out

    def test_missing_section_surfaces_after_cutover(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._arm(temp_project_dir, "2020-01-01")
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9603")
        _write_issue(format_check_dir, "P3-BUG-9603-test-bug.md", body)

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9603",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "Program Design" in json.loads(out)["missing"]

    def test_escape_hatch_passes_after_cutover(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._arm(temp_project_dir, "2020-01-01")
        body = _CLEAN_BUG_BODY.replace(
            "id: BUG-9101", "id: BUG-9604\nprogram_design_not_applicable: true"
        )
        _write_issue(format_check_dir, "P3-BUG-9604-test-bug.md", body)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9604", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0, out

    def test_full_residue_caught_by_boilerplate_not_template_placeholders(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ENH-3244 Decision Rules › Masking part 3: excluding Program Design from
        the derived pattern set costs no coverage — a pure-template body is still
        caught, just by boilerplate (whole-section equality) rather than the new
        class."""
        self._arm(temp_project_dir, "2020-01-01")
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", "id: BUG-9605").replace(
            "## Status\nopen",
            "## Program Design\n\n### Types\n\n- `[FieldName]: [type]`\n\n"
            "### Signatures\n\n- `[function_name]([param]: [type]) -> [ReturnType]`\n\n"
            "### Call Path\n\n`[existing_caller]` -> `[new_function]` -> "
            "`[existing_callee]`\n\n## Status\nopen",
        )
        _write_issue(format_check_dir, "P3-BUG-9605-test-bug.md", body)

        result = _invoke(
            [
                "ll-issues",
                "format-check",
                "BUG-9605",
                "--format",
                "json",
                "--config",
                str(temp_project_dir),
            ]
        )
        out, _ = capsys.readouterr()

        assert result == 1
        data = json.loads(out)
        assert data["boilerplate"] == ["Program Design"]
        assert data["template_placeholders"] == []


# ---------------------------------------------------------------------------
# TestFormatCheckDeprecationSuppression (ENH-2961)
# ---------------------------------------------------------------------------


def _issue_body(issue_id: str, *, deprecated_parent: str | None = None) -> str:
    """Build a clean issue body for *issue_id*, optionally with a deprecated key."""
    body = _CLEAN_BUG_BODY.replace("BUG-9101", issue_id)
    if deprecated_parent is not None:
        body = body.replace(f"id: {issue_id}", f"id: {issue_id}\nparent_issue: {deprecated_parent}")
    return body


class TestFormatCheckDeprecationSuppression:
    """Single-ID ``format-check`` suppresses other issues' deprecation warnings."""

    def test_single_id_suppresses_other_issues_warnings(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
        caplog: Any,
    ) -> None:
        _write_issue(format_check_dir, "P3-BUG-9701-test-bug.md", _issue_body("BUG-9701"))
        _write_issue(
            format_check_dir,
            "P3-BUG-9702-test-bug.md",
            _issue_body("BUG-9702", deprecated_parent="BUG-1"),
        )
        _write_issue(
            format_check_dir,
            "P3-BUG-9703-test-bug.md",
            _issue_body("BUG-9703", deprecated_parent="BUG-1"),
        )

        with caplog.at_level(logging.WARNING, logger="little_loops.issue_parser"):
            result = _invoke(
                ["ll-issues", "format-check", "BUG-9701", "--config", str(temp_project_dir)]
            )
        out, err = capsys.readouterr()

        assert result == 0
        assert "BUG-9101" not in out  # sanity: template placeholder never leaks
        assert not any(
            "BUG-9702" in record.message or "BUG-9703" in record.message
            for record in caplog.records
        )
        assert "2 other issue(s) have deprecated frontmatter keys" in err
        assert "run `ll-issues format-check`" in err

    def test_single_id_still_warns_for_targets_own_deprecated_key(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
        caplog: Any,
    ) -> None:
        _write_issue(
            format_check_dir,
            "P3-BUG-9704-test-bug.md",
            _issue_body("BUG-9704", deprecated_parent="BUG-1"),
        )

        with caplog.at_level(logging.WARNING, logger="little_loops.issue_parser"):
            _invoke(["ll-issues", "format-check", "BUG-9704", "--config", str(temp_project_dir)])
        _, err = capsys.readouterr()

        assert any(
            "BUG-9704" in record.message and "parent_issue" in record.message
            for record in caplog.records
        )
        # No *other* deprecated-key files exist, so the tally line is silent.
        assert "have deprecated frontmatter keys" not in err

    def test_full_sweep_still_reports_deprecated_keys(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
        caplog: Any,
    ) -> None:
        _write_issue(
            format_check_dir,
            "P3-BUG-9705-test-bug.md",
            _issue_body("BUG-9705", deprecated_parent="BUG-1"),
        )
        _write_issue(
            format_check_dir,
            "P3-BUG-9706-test-bug.md",
            _issue_body("BUG-9706", deprecated_parent="BUG-1"),
        )

        with caplog.at_level(logging.WARNING, logger="little_loops.issue_parser"):
            result = _invoke(
                ["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)]
            )
        out, _ = capsys.readouterr()

        assert result == 1
        assert "BUG-9705" in out
        assert "BUG-9706" in out
        warned_ids = {
            record.args[0]
            for record in caplog.records
            if record.args and "parent_issue" in record.message
        }
        assert {"P3-BUG-9705-test-bug.md", "P3-BUG-9706-test-bug.md"} <= warned_ids


# ---------------------------------------------------------------------------
# TestFormatCheckTestableRendering
# ---------------------------------------------------------------------------


_DOC_ONLY_BODY = "\n".join(
    [
        "---",
        "id: BUG-9801",
        "status: open",
        "---",
        "",
        "# BUG-9801: Fix broken link in the docs guide",
        "",
        "## Summary",
        "The documentation guide has a broken link and a typo in the readme.",
        "",
        "## Current Behavior",
        "The docs link 404s.",
        "",
        "## Expected Behavior",
        "The documentation link resolves.",
        "",
        "## Steps to Reproduce",
        "1. Open the guide.",
        "2. Click the broken link.",
        "",
        "## Impact",
        "- **Priority**: P3 - Low",
        "- **Effort**: Small",
        "- **Risk**: Low",
        "- **Breaking Change**: No",
        "",
        "## Status",
        "open",
    ]
)


class TestFormatCheckTestableRendering:
    """The `testable` gap class renders in text mode, not just --format json.

    Regression: `testable` was added to FormatGaps (field, has_gaps, to_dict)
    without a matching loop in _print_gaps, so an issue whose only gap was
    `testable` exited 1 with a header and no body — undiagnosable for a human
    or a shell-out caller. Landed via a fallback commit for FEAT-2948; the
    class belongs to ENH-2946.

    ENH-2966 Option E demoted `testable` to an advisory (non-blocking) gap
    class: it still renders in every output surface (has_gaps, unaffected),
    but a testable-only issue now exits 0 (has_blocking_gaps, false) instead
    of 1 — that's what changed in the three exit-code assertions below.
    """

    def test_testable_gap_is_printed_in_text_mode(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_issue(format_check_dir, "P3-BUG-9801-fix-docs-link.md", _DOC_ONLY_BODY)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9801", "--config", str(temp_project_dir)]
        )
        out, _ = capsys.readouterr()

        assert result == 0
        assert "testable:" in out
        assert "P3-BUG-9801-fix-docs-link.md" in out

    def test_text_output_reports_every_class_json_reports(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Text mode must name every gap class `--format json` reports.

        Stated as json/text parity rather than "exit 1 prints something": the
        weaker form passes vacuously whenever the fixture happens to trip a
        second, rendered class, which is exactly how the regression survived.
        """
        _write_issue(
            format_check_dir,
            "P3-BUG-9802-fix-docs-link.md",
            _DOC_ONLY_BODY.replace("9801", "9802"),
        )
        argv = ["ll-issues", "format-check", "BUG-9802", "--config", str(temp_project_dir)]

        assert _invoke([*argv, "--format", "json"]) == 0
        payload = json.loads(capsys.readouterr()[0])
        reported = {name for name, entries in payload.items() if entries}
        assert "testable" in reported, "fixture no longer trips the testable gap"

        assert _invoke(argv) == 0
        out, _ = capsys.readouterr()

        unrendered = [name for name in reported if f"{name}:" not in out]
        assert not unrendered, f"classes in JSON but absent from text report: {unrendered}"

    def test_testable_only_issue_stays_visible_in_all_sweep_but_exits_zero(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """ENH-2966 Option E: advisory-only ≠ invisible — sweep still lists it."""
        _write_issue(
            format_check_dir,
            "P3-BUG-9803-fix-docs-link.md",
            _DOC_ONLY_BODY.replace("9801", "9803"),
        )

        result = _invoke(["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 0
        assert "BUG-9803" in out
        assert "testable:" in out

    # ENH-3280: unapplied_decision_detail is a structured (section, identifier)
    # projection of unapplied_decision for machine consumers only — it is not
    # counted by has_gaps (see FormatGaps.has_gaps), so it cannot trigger the
    # "counted but not rendered" regression this guard exists to catch, and
    # deliberately has no _print_gaps loop of its own.
    _TEXT_RENDER_EXEMPT = {"unapplied_decision_detail"}

    def test_every_format_gaps_field_is_rendered(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Every FormatGaps list field must have a loop in _print_gaps.

        Structural guard so a future gap class cannot repeat the regression:
        counted by has_gaps, absent from the text report. Exempts fields in
        `_TEXT_RENDER_EXEMPT` (machine-only projections not counted by has_gaps).
        """
        import dataclasses

        from little_loops.cli.issues.format_check import _print_gaps
        from little_loops.issue_parser import FormatGaps

        field_names = [
            f.name for f in dataclasses.fields(FormatGaps) if f.name not in self._TEXT_RENDER_EXEMPT
        ]
        gaps = FormatGaps(**{name: [f"sentinel-{name}"] for name in field_names})

        assert gaps.has_gaps
        _print_gaps(gaps)
        out, _ = capsys.readouterr()

        unrendered = [name for name in field_names if f"sentinel-{name}" not in out]
        assert not unrendered, f"FormatGaps fields not rendered by _print_gaps: {unrendered}"


# ---------------------------------------------------------------------------
# TestFormatCheckNext (ENH-2946)
# ---------------------------------------------------------------------------


class TestFormatCheckNext:
    """``format-check --next`` targets the highest-priority active issue."""

    def test_next_targets_highest_priority_issue(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_issue(format_check_dir, "P3-BUG-9101-test-bug.md", _CLEAN_BUG_BODY)
        higher_priority_body = _CLEAN_BUG_BODY.replace("BUG-9101", "BUG-9102").replace(
            "P3 - Low", "P0 - Critical"
        )
        _write_issue(format_check_dir, "P0-BUG-9102-test-bug.md", higher_priority_body)

        result = _invoke(["ll-issues", "format-check", "--next", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 0
        assert "BUG-9102" in out

    def test_next_mutually_exclusive_with_issue_id(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_issue(format_check_dir, "P3-BUG-9101-test-bug.md", _CLEAN_BUG_BODY)

        result = _invoke(
            ["ll-issues", "format-check", "BUG-9101", "--next", "--config", str(temp_project_dir)]
        )
        _, err = capsys.readouterr()

        assert result == 1
        assert "mutually exclusive" in err

    def test_next_mutually_exclusive_with_all(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = _invoke(
            ["ll-issues", "format-check", "--next", "--all", "--config", str(temp_project_dir)]
        )
        _, err = capsys.readouterr()

        assert result == 1
        assert "mutually exclusive" in err

    def test_next_on_empty_backlog_exits_1_with_message(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        result = _invoke(["ll-issues", "format-check", "--next", "--config", str(temp_project_dir)])
        _, err = capsys.readouterr()

        assert result == 1
        assert "No active issues found" in err


class TestDuplicateFindingsBlock:
    """``duplicate_findings_block`` gap class (ENH-2993).

    Reports one entry per H2 carrying more than one ``### Codebase Research
    Findings`` block. Evaluated **per H2**, not document-wide: an issue with one
    block under each of several H2s is compliant, and flagging it would train
    the model to skim past § 6.7's other keys.
    """

    def _write_with_sections(self, format_check_dir: Path, bug_id: str, block: str) -> Path:
        filename = f"P3-{bug_id}-test-bug.md"
        body = _CLEAN_BUG_BODY.replace("id: BUG-9101", f"id: {bug_id}") + "\n\n" + block
        return _write_issue(format_check_dir, filename, body)

    def test_stacked_blocks_under_one_h2_are_flagged(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        block = (
            "## Integration Map\n\n"
            "### Codebase Research Findings\n\n- one\n\n"
            "### Codebase Research Findings\n\n- two\n"
        )
        self._write_with_sections(format_check_dir, "BUG-9701", block)

        result = _invoke(["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert result == 1
        assert "duplicate_findings_block: Integration Map (2)" in out

    def test_one_block_per_h2_is_compliant(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        block = (
            "## Integration Map\n\n### Codebase Research Findings\n\n- one\n\n"
            "## Program Design\n\n### Codebase Research Findings\n\n- two\n"
        )
        self._write_with_sections(format_check_dir, "BUG-9702", block)

        result = _invoke(["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert "duplicate_findings_block" not in out
        assert result == 0

    def test_h2_level_variant_is_not_counted_as_a_duplicate(
        self,
        temp_project_dir: Path,
        format_check_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """``_heading_bodies()`` matches ``##`` too; this detector must not."""
        block = (
            "## Codebase Research Findings\n\n- stray H2 variant\n\n"
            "## Integration Map\n\n### Codebase Research Findings\n\n- one\n"
        )
        self._write_with_sections(format_check_dir, "BUG-9703", block)

        result = _invoke(["ll-issues", "format-check", "--all", "--config", str(temp_project_dir)])
        out, _ = capsys.readouterr()

        assert "duplicate_findings_block" not in out
        assert result == 0

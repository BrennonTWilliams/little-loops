"""Tests for ll-issues normalize sub-command (ENH-2944)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.cli.issues.normalize import AUTO_FIXABLE_KINDS, scan_normalize
from little_loops.config import BRConfig
from little_loops.frontmatter import parse_frontmatter

_NORMALIZE_CONFIG: dict[str, Any] = {
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
def normalize_dir(temp_project_dir: Path) -> Path:
    """Temp project with config and all four category directories."""
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(_NORMALIZE_CONFIG))
    issues_base = temp_project_dir / ".issues"
    for cat in ("bugs", "features", "enhancements", "epics"):
        (issues_base / cat).mkdir(parents=True, exist_ok=True)
    return issues_base


def _config(temp_project_dir: Path) -> BRConfig:
    return BRConfig(temp_project_dir)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _issue_body(
    *,
    id_: str | None = None,
    title: str = "Test issue",
    extra_fm: str = "",
    body: str = "",
    status: str = "open",
) -> str:
    fm_lines = ["---"]
    if id_ is not None:
        fm_lines.append(f"id: {id_}")
    fm_lines.append(f"status: {status}")
    if extra_fm:
        fm_lines.append(extra_fm.strip())
    fm_lines.append("---")
    return "\n".join(fm_lines) + f"\n\n# {title}\n\n{body}\n"


def _invoke(argv: list[str]) -> tuple[int, str]:
    import contextlib
    import io

    from little_loops.cli import main_issues

    with patch.object(sys, "argv", argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = main_issues()
        return result, buf.getvalue()


# ---------------------------------------------------------------------------
# missing_id
# ---------------------------------------------------------------------------


class TestMissingId:
    def test_missing_id_detected_and_check_fails(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        _write(normalize_dir / "bugs" / "fix-login-bug.md", _issue_body())

        result, out = _invoke(
            ["ll-issues", "normalize", "--check", "--config", str(temp_project_dir)]
        )
        assert result == 1
        assert "missing valid ID" in out

    def test_missing_id_auto_fix_renames_and_stamps_frontmatter(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        original = _write(normalize_dir / "bugs" / "fix-login-bug.md", _issue_body())

        config = _config(temp_project_dir)
        findings = scan_normalize(config)
        assert len(findings) == 1
        assert findings[0].kind == "missing_id"

        result, _ = _invoke(["ll-issues", "normalize", "--auto", "--config", str(temp_project_dir)])
        assert result == 0
        assert not original.exists()

        renamed = list((normalize_dir / "bugs").glob("P3-BUG-*-fix-login-bug.md"))
        assert len(renamed) == 1
        content = renamed[0].read_text()
        fm = parse_frontmatter(content)
        m = renamed[0].name.split("-")
        assert fm["id"] == f"BUG-{m[2]}"

    def test_no_phantom_duplicates_from_id_less_files(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        """Regression: two ID-less files (plus a stray-number slug) never
        produce a duplicate_id finding — grouping must key off the filename
        regex, not IssueInfo.issue_id's synthesized fallback (Design Decision 5).
        """
        _write(normalize_dir / "bugs" / "P2-BUG-050-real-issue.md", _issue_body(id_="BUG-050"))
        _write(normalize_dir / "bugs" / "fix-one.md", _issue_body())
        _write(normalize_dir / "bugs" / "fix-two.md", _issue_body())
        _write(normalize_dir / "bugs" / "release-050-notes.md", _issue_body())

        config = _config(temp_project_dir)
        findings = scan_normalize(config)

        assert not [f for f in findings if f.kind == "duplicate_id"]
        missing = [f for f in findings if f.kind == "missing_id"]
        assert len(missing) == 3

        _invoke(["ll-issues", "normalize", "--auto", "--config", str(temp_project_dir)])
        assigned_ids = set()
        for f in normalize_dir.rglob("*.md"):
            fm = parse_frontmatter(f.read_text())
            if fm.get("id"):
                assigned_ids.add(fm["id"])
        assert len(assigned_ids) == 4  # 1 real + 3 distinct freshly-assigned


# ---------------------------------------------------------------------------
# malformed_filename
# ---------------------------------------------------------------------------


class TestMalformedFilename:
    def test_missing_priority_prefix_defaults_to_p3_explicitly(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        _write(
            normalize_dir / "enhancements" / "ENH-050-improve-things.md",
            _issue_body(id_="ENH-050"),
        )

        config = _config(temp_project_dir)
        findings = scan_normalize(config)
        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "malformed_filename"
        assert f.priority_defaulted is True
        assert f.proposed_path is not None
        assert f.proposed_path.name.startswith("P3-ENH-050-")

        data = f.to_dict()
        assert data["priority_defaulted"] is True

    def test_underscored_slug_is_not_flagged(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        _write(
            normalize_dir / "bugs" / "P2-BUG-051-refresh_corpus-passes-quiet.md",
            _issue_body(id_="BUG-051"),
        )

        config = _config(temp_project_dir)
        findings = scan_normalize(config)
        assert [f for f in findings if f.kind == "malformed_filename"] == []


# ---------------------------------------------------------------------------
# duplicate_id
# ---------------------------------------------------------------------------


class TestDuplicateId:
    def test_cross_type_duplicate_reassigns_loser_and_syncs_frontmatter(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        _write(
            normalize_dir / "bugs" / "P2-BUG-100-first.md",
            _issue_body(id_="BUG-100", title="Keeper"),
        )
        loser = _write(
            normalize_dir / "features" / "P2-FEAT-100-second.md",
            _issue_body(id_="FEAT-100", title="Loser"),
        )

        config = _config(temp_project_dir)
        findings = scan_normalize(config)
        dup = [f for f in findings if f.kind == "duplicate_id"]
        assert len(dup) == 1
        assert dup[0].path.resolve() == loser.resolve()
        assert dup[0].proposed_id != "FEAT-100"

        result, _ = _invoke(["ll-issues", "normalize", "--auto", "--config", str(temp_project_dir)])
        assert result == 0

        # Keeper untouched.
        assert (normalize_dir / "bugs" / "P2-BUG-100-first.md").exists()
        assert not loser.exists()

        renamed = list((normalize_dir / "features").glob("P2-FEAT-*-second.md"))
        assert len(renamed) == 1
        assert renamed[0].name != "P2-FEAT-100-second.md"
        fm = parse_frontmatter(renamed[0].read_text())
        new_id = renamed[0].name.split("-")
        assert fm["id"] == f"FEAT-{new_id[2]}"

        # No malformed_id gap for the moved file (format-check sibling gate).
        result2, out2 = _invoke(
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
        gaps = json.loads(out2)
        moved_gaps = gaps.get(fm["id"], {})
        assert not moved_gaps.get("malformed_id")

    def test_duplicate_id_never_applied_by_auto_when_check_only(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        _write(normalize_dir / "bugs" / "P2-BUG-100-first.md", _issue_body(id_="BUG-100"))
        loser = _write(
            normalize_dir / "features" / "P2-FEAT-100-second.md", _issue_body(id_="FEAT-100")
        )

        result, out = _invoke(
            ["ll-issues", "normalize", "--check", "--config", str(temp_project_dir)]
        )
        assert result == 1
        assert loser.exists()  # --check never mutates


# ---------------------------------------------------------------------------
# inbound edge rewriting (mandatory regression)
# ---------------------------------------------------------------------------


class TestInboundEdgeRewrite:
    def test_reassigned_duplicate_repoints_blocked_by(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        _write(normalize_dir / "bugs" / "P2-BUG-100-first.md", _issue_body(id_="BUG-100"))
        loser = _write(
            normalize_dir / "features" / "P2-FEAT-100-second.md", _issue_body(id_="FEAT-100")
        )
        blocked = _write(
            normalize_dir / "enhancements" / "P2-ENH-200-depends.md",
            _issue_body(id_="ENH-200", extra_fm="blocked_by:\n  - FEAT-100"),
        )

        config = _config(temp_project_dir)
        findings = scan_normalize(config)
        dup = next(f for f in findings if f.kind == "duplicate_id")
        assert dup.inbound_refs == ["ENH-200"]

        _invoke(["ll-issues", "normalize", "--auto", "--config", str(temp_project_dir)])

        assert not loser.exists()
        renamed = list((normalize_dir / "features").glob("P2-FEAT-*-second.md"))[0]
        new_id = parse_frontmatter(renamed.read_text())["id"]
        assert new_id != "FEAT-100"

        blocked_fm = parse_frontmatter(blocked.read_text())
        assert blocked_fm["blocked_by"] == [new_id]


# ---------------------------------------------------------------------------
# legacy_dir
# ---------------------------------------------------------------------------


class TestLegacyDir:
    def test_legacy_dirs_detected_base_and_nested_never_auto_fixed(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        _write(normalize_dir / "completed" / "old.md", _issue_body(id_="BUG-999"))
        _write(normalize_dir / "bugs" / "completed" / "old2.md", _issue_body(id_="BUG-998"))

        config = _config(temp_project_dir)
        findings = scan_normalize(config)
        legacy = [f for f in findings if f.kind == "legacy_dir"]
        assert len(legacy) == 2
        assert "legacy_dir" not in AUTO_FIXABLE_KINDS

        result_default, _ = _invoke(
            ["ll-issues", "normalize", "--check", "--config", str(temp_project_dir)]
        )
        assert result_default == 0  # convergence: legacy_dir doesn't gate without --strict

        result_strict, _ = _invoke(
            ["ll-issues", "normalize", "--check", "--strict", "--config", str(temp_project_dir)]
        )
        assert result_strict == 1


# ---------------------------------------------------------------------------
# --check convergence
# ---------------------------------------------------------------------------


class TestCheckConvergence:
    def test_clean_corpus_exits_zero(self, temp_project_dir: Path, normalize_dir: Path) -> None:
        _write(normalize_dir / "bugs" / "P2-BUG-100-clean.md", _issue_body(id_="BUG-100"))

        result, out = _invoke(
            ["ll-issues", "normalize", "--check", "--config", str(temp_project_dir)]
        )
        assert result == 0
        assert "All issues normalized" in out


# ---------------------------------------------------------------------------
# scoping
# ---------------------------------------------------------------------------


class TestScoping:
    def test_positional_id_scopes_reported_findings(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        _write(
            normalize_dir / "enhancements" / "ENH-050-a.md",
            _issue_body(id_="ENH-050"),
        )
        _write(
            normalize_dir / "enhancements" / "ENH-060-b.md",
            _issue_body(id_="ENH-060"),
        )

        config = _config(temp_project_dir)
        scoped = scan_normalize(config, only_ids=["ENH-050"])
        assert len(scoped) == 1
        assert scoped[0].path.name == "ENH-050-a.md"


# ---------------------------------------------------------------------------
# type_mismatch (ENH-3053)
# ---------------------------------------------------------------------------


class TestTypeMismatch:
    def test_fires_on_epic_phrase_level_signal(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        body = (
            "## Summary\n\n"
            "This work should decompose into smaller pieces. It acts as a "
            "coordination container and umbrella issue, and should decompose "
            "into further sub-tasks.\n"
        )
        _write(
            normalize_dir / "bugs" / "P3-BUG-100-scope.md",
            _issue_body(id_="BUG-100", body=body),
        )

        config = _config(temp_project_dir)
        findings = scan_normalize(config)
        mismatches = [f for f in findings if f.kind == "type_mismatch"]
        assert len(mismatches) == 1
        assert mismatches[0].proposed_id == "EPIC-100"

    def test_no_fire_on_bare_epic_feature_area_mention(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        body = (
            "## Summary\n\n"
            "The bug is in the --group-by epic option of the EPIC schema; "
            "users see incorrect epic counts in epic-progress output.\n"
        )
        _write(
            normalize_dir / "bugs" / "P3-BUG-100-scope.md",
            _issue_body(id_="BUG-100", body=body),
        )

        config = _config(temp_project_dir)
        findings = scan_normalize(config)
        assert not [f for f in findings if f.kind == "type_mismatch"]

    def test_no_fire_on_closed_status_despite_signal(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        body = (
            "## Summary\n\n"
            "This is broken and causes a crash. The regression is an "
            "unexpected defect with incorrect, wrong behavior.\n"
        )
        _write(
            normalize_dir / "enhancements" / "P3-ENH-200-scope.md",
            _issue_body(id_="ENH-200", body=body, status="done"),
        )

        config = _config(temp_project_dir)
        findings = scan_normalize(config)
        assert not [f for f in findings if f.kind == "type_mismatch"]

    def test_fires_on_open_status_with_same_signal(
        self, temp_project_dir: Path, normalize_dir: Path
    ) -> None:
        body = (
            "## Summary\n\n"
            "This is broken and causes a crash. The regression is an "
            "unexpected defect with incorrect, wrong behavior.\n"
        )
        _write(
            normalize_dir / "enhancements" / "P3-ENH-200-scope.md",
            _issue_body(id_="ENH-200", body=body, status="open"),
        )

        config = _config(temp_project_dir)
        findings = scan_normalize(config)
        mismatches = [f for f in findings if f.kind == "type_mismatch"]
        assert len(mismatches) == 1
        assert mismatches[0].proposed_id == "BUG-200"


# ---------------------------------------------------------------------------
# --json output
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_json_shape(self, temp_project_dir: Path, normalize_dir: Path) -> None:
        _write(normalize_dir / "bugs" / "fix-login-bug.md", _issue_body())

        result, out = _invoke(
            ["ll-issues", "normalize", "--json", "--config", str(temp_project_dir)]
        )
        assert result == 0
        data = json.loads(out)
        assert set(data) == {"findings", "applied"}
        assert data["applied"] == []
        assert len(data["findings"]) == 1
        assert data["findings"][0]["kind"] == "missing_id"

    def test_apply_idempotent(self, temp_project_dir: Path, normalize_dir: Path) -> None:
        _write(normalize_dir / "bugs" / "fix-login-bug.md", _issue_body())

        _invoke(["ll-issues", "normalize", "--auto", "--config", str(temp_project_dir)])
        result2, out2 = _invoke(
            ["ll-issues", "normalize", "--json", "--config", str(temp_project_dir)]
        )
        data2 = json.loads(out2)
        assert data2["findings"] == []
        assert result2 == 0

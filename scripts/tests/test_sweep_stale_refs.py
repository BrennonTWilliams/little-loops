"""Python-direct tests for ``little_loops.hooks.sweep_stale_refs.handle`` (FEAT-1680).

Covers the session-end hook that sweeps open issue files for stale prose
references to done issue IDs.  Every path through ``handle()`` must return
``exit_code == 0`` — the hook is advisory and must never block session end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.hooks.sweep_stale_refs import _auto_fix_file, _scan_file, handle
from little_loops.hooks.types import LLHookEvent

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """chdir into ``tmp_path`` for the duration of one test, then restore."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _event(cwd: str | None = None) -> LLHookEvent:
    return LLHookEvent(host="claude-code", intent="session_end", payload={}, cwd=cwd)


def _write_config(tmp_path: Path, stale_ref_fix: str = "report") -> None:
    """Write a minimal ``.ll/ll-config.json`` with ``hooks.stale_ref_fix``."""
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"hooks": {"stale_ref_fix": stale_ref_fix}}),
        encoding="utf-8",
    )


def _write_issues(tmp_path: Path, files: dict[str, str]) -> None:
    """Create issue files under ``.issues/`` subdirs.

    ``files`` maps a relative path like ``"features/P1-FEAT-1.md"`` to file
    content.  The ``.issues/`` prefix is prepended automatically.
    """
    for rel_path, content in files.items():
        full_path = tmp_path / ".issues" / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")


def _minimal_issue(issue_id: str, status: str, body: str = "") -> str:
    """Return minimal YAML-frontmatter issue content."""
    type_prefix = issue_id.split("-")[0]
    return f"---\nid: {issue_id}\nstatus: {status}\n---\n\n# {type_prefix}: {issue_id}\n\n{body}"


# ---------------------------------------------------------------------------
# TestSweepStaleRefsBaseline
# ---------------------------------------------------------------------------


class TestSweepStaleRefsBaseline:
    def test_no_config_exits_zero(self, in_tmp: Path) -> None:
        """No config at all → handler skips all work and exits 0."""
        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_no_issues_dir_exits_zero(self, in_tmp: Path) -> None:
        """Config present but no ``.issues/`` directory → exits 0."""
        _write_config(in_tmp)
        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_no_done_issues_exits_zero(self, in_tmp: Path) -> None:
        """Issues exist but none are done → no IDs to sweep → exits 0."""
        _write_config(in_tmp)
        _write_issues(
            in_tmp,
            {
                "features/P3-FEAT-1001-alpha.md": _minimal_issue("FEAT-1001", "open"),
                "enhancements/P3-ENH-2002-beta.md": _minimal_issue("ENH-2002", "in_progress"),
            },
        )
        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0
        assert result.feedback is None


# ---------------------------------------------------------------------------
# TestSweepStaleRefsDetection
# ---------------------------------------------------------------------------


class TestSweepStaleRefsDetection:
    def _setup(
        self,
        tmp_path: Path,
        *,
        done_id: str = "FEAT-1000",
        open_body: str,
        open_subdir: str = "enhancements",
        open_id: str = "ENH-2000",
    ) -> None:
        _write_config(tmp_path)
        # Write a done issue
        _write_issues(
            tmp_path,
            {
                f"features/P3-{done_id}-done-thing.md": _minimal_issue(done_id, "done"),
                f"{open_subdir}/P3-{open_id}-checker.md": _minimal_issue(
                    open_id, "open", body=open_body
                ),
            },
        )

    def test_detects_is_open_phrase(self, in_tmp: Path) -> None:
        """'FEAT-1000 is open' in an open issue triggers a finding."""
        self._setup(in_tmp, open_body="FEAT-1000 is open and we need to wait.")
        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "FEAT-1000" in result.feedback

    def test_detects_is_still_open(self, in_tmp: Path) -> None:
        """'FEAT-1000 is still open' matches the stale-status pattern."""
        self._setup(in_tmp, open_body="FEAT-1000 is still open, not resolved.")
        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "FEAT-1000" in result.feedback

    def test_detects_blocked_by(self, in_tmp: Path) -> None:
        """'blocked by FEAT-1000' where FEAT-1000 is done is stale."""
        self._setup(in_tmp, open_body="This work is blocked by FEAT-1000 right now.")
        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "FEAT-1000" in result.feedback

    def test_no_false_positive_when_id_not_done(self, in_tmp: Path) -> None:
        """A stale-phrase pattern should not fire when the referenced ID is NOT done."""
        _write_config(in_tmp)
        # FEAT-1000 is open (not done), so no stale ref should be reported
        _write_issues(
            in_tmp,
            {
                "features/P3-FEAT-1000-alive.md": _minimal_issue("FEAT-1000", "open"),
                "enhancements/P3-ENH-2000-checker.md": _minimal_issue(
                    "ENH-2000", "open", body="FEAT-1000 is still open, holding us back."
                ),
            },
        )
        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_multiple_files_multiple_findings(self, in_tmp: Path) -> None:
        """Multiple open files with stale refs all appear in feedback."""
        _write_config(in_tmp)
        _write_issues(
            in_tmp,
            {
                "features/P3-FEAT-1000-done.md": _minimal_issue("FEAT-1000", "done"),
                "enhancements/P3-ENH-2001-a.md": _minimal_issue(
                    "ENH-2001", "open", body="FEAT-1000 is open still."
                ),
                "enhancements/P3-ENH-2002-b.md": _minimal_issue(
                    "ENH-2002", "open", body="blocked by FEAT-1000 somewhere."
                ),
            },
        )
        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "ENH-2001" in result.feedback or "P3-ENH-2001" in result.feedback
        assert "ENH-2002" in result.feedback or "P3-ENH-2002" in result.feedback

    def test_report_includes_line_number(self, in_tmp: Path) -> None:
        """Each finding in feedback includes a ':N:' line-number marker."""
        self._setup(in_tmp, open_body="FEAT-1000 is open still.\n")
        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0
        assert result.feedback is not None
        # Feedback lines look like "  /path/to/file.md:5: [FEAT-1000] ..."
        assert ":5:" in result.feedback or any(f":{n}:" in result.feedback for n in range(1, 20))

    def test_skips_code_fence_region(self, in_tmp: Path) -> None:
        """An ID inside a triple-backtick code block must NOT be flagged."""
        body = "```\nFEAT-1000 is open in this example\n```\n"
        self._setup(in_tmp, open_body=body)
        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0
        # Inside a code fence → no finding
        assert result.feedback is None


# ---------------------------------------------------------------------------
# TestSweepStaleRefsAutoFix
# ---------------------------------------------------------------------------


class TestSweepStaleRefsAutoFix:
    def test_auto_fix_rewrites_is_open(self, in_tmp: Path) -> None:
        """auto mode rewrites 'is open' to 'is done' in the file on disk."""
        _write_config(in_tmp, stale_ref_fix="auto")
        open_file_path = in_tmp / ".issues" / "enhancements" / "P3-ENH-2000-checker.md"
        open_file_path.parent.mkdir(parents=True, exist_ok=True)
        open_file_path.write_text(
            _minimal_issue("ENH-2000", "open", body="FEAT-1000 is open, blocking work.\n"),
            encoding="utf-8",
        )
        _write_issues(
            in_tmp,
            {"features/P3-FEAT-1000-done.md": _minimal_issue("FEAT-1000", "done")},
        )

        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0

        new_content = open_file_path.read_text(encoding="utf-8")
        assert "is done" in new_content
        assert "is open" not in new_content

    def test_auto_fix_no_remaining_findings(self, in_tmp: Path) -> None:
        """After auto-fix rewrites all stale refs, feedback is None (no findings)."""
        _write_config(in_tmp, stale_ref_fix="auto")
        _write_issues(
            in_tmp,
            {
                "features/P3-FEAT-1000-done.md": _minimal_issue("FEAT-1000", "done"),
                "enhancements/P3-ENH-2000-checker.md": _minimal_issue(
                    "ENH-2000", "open", body="FEAT-1000 is open.\n"
                ),
            },
        )

        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0
        # After auto-fix the file no longer has stale refs, so feedback is None
        assert result.feedback is None


# ---------------------------------------------------------------------------
# TestSweepStaleRefsGracefulDegradation
# ---------------------------------------------------------------------------


class TestSweepStaleRefsGracefulDegradation:
    def test_exits_zero_with_no_cwd(self) -> None:
        """Handler must not raise and must return exit_code=0 when cwd is empty."""
        event = LLHookEvent(host="claude-code", intent="session_end", payload={}, cwd=None)
        result = handle(event)
        assert result.exit_code == 0

    def test_exits_zero_with_broken_config(self, in_tmp: Path) -> None:
        """Malformed JSON config is silently ignored; handler returns exit_code=0."""
        ll_dir = in_tmp / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        (ll_dir / "ll-config.json").write_text("{not valid json{{", encoding="utf-8")
        result = handle(_event(cwd=str(in_tmp)))
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# TestScanFile — unit tests for _scan_file helper
# ---------------------------------------------------------------------------


class TestScanFile:
    def _write(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "issue.md"
        p.write_text(content, encoding="utf-8")
        return p

    def test_no_done_ids_returns_empty(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "FEAT-1000 is open.\n")
        findings = _scan_file(p, done_ids=set())
        assert findings == []

    def test_detects_is_open(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "FEAT-1000 is open and blocking.\n")
        findings = _scan_file(p, done_ids={"FEAT-1000"})
        assert len(findings) == 1
        lineno, issue_id, snippet = findings[0]
        assert lineno == 1
        assert issue_id == "FEAT-1000"
        assert "FEAT-1000" in snippet

    def test_detects_is_still_open(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "ENH-42 is still open.\n")
        findings = _scan_file(p, done_ids={"ENH-42"})
        assert len(findings) == 1
        assert findings[0][1] == "ENH-42"

    def test_detects_blocked_by(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "Work is blocked by BUG-7 right now.\n")
        findings = _scan_file(p, done_ids={"BUG-7"})
        assert len(findings) == 1
        assert findings[0][1] == "BUG-7"

    def test_skips_code_fence(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "```\nFEAT-1000 is open\n```\n")
        findings = _scan_file(p, done_ids={"FEAT-1000"})
        assert findings == []

    def test_no_false_positive_on_plain_mention(self, tmp_path: Path) -> None:
        """A line mentioning a done ID without a stale phrase must not flag."""
        p = self._write(tmp_path, "See FEAT-1000 for more context.\n")
        findings = _scan_file(p, done_ids={"FEAT-1000"})
        assert findings == []

    def test_returns_correct_line_number(self, tmp_path: Path) -> None:
        content = "line one\nline two\nFEAT-1000 is open here\nline four\n"
        p = self._write(tmp_path, content)
        findings = _scan_file(p, done_ids={"FEAT-1000"})
        assert len(findings) == 1
        assert findings[0][0] == 3  # 1-based line number

    def test_handles_unreadable_file(self, tmp_path: Path) -> None:
        """If the file cannot be read, _scan_file returns an empty list."""
        p = tmp_path / "nonexistent.md"
        findings = _scan_file(p, done_ids={"FEAT-1000"})
        assert findings == []

    def test_is_active_phrase(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "FEAT-1000 is active.\n")
        findings = _scan_file(p, done_ids={"FEAT-1000"})
        assert len(findings) == 1

    def test_id_not_in_done_ids_not_flagged(self, tmp_path: Path) -> None:
        """A stale phrase mentioning an ID not in done_ids must not fire."""
        p = self._write(tmp_path, "ENH-99 is still open.\n")
        findings = _scan_file(p, done_ids={"FEAT-1000"})
        assert findings == []


# ---------------------------------------------------------------------------
# TestAutoFixFile — unit tests for _auto_fix_file helper
# ---------------------------------------------------------------------------


class TestAutoFixFile:
    def _write(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "issue.md"
        p.write_text(content, encoding="utf-8")
        return p

    def test_rewrites_is_open_to_is_done(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "FEAT-1000 is open.\n")
        modified = _auto_fix_file(p, done_ids={"FEAT-1000"})
        assert modified is True
        assert "is done" in p.read_text(encoding="utf-8")

    def test_rewrites_is_still_open(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "ENH-42 is still open.\n")
        modified = _auto_fix_file(p, done_ids={"ENH-42"})
        assert modified is True
        new = p.read_text(encoding="utf-8")
        assert "is done" in new
        assert "still open" not in new

    def test_no_modification_when_no_stale_phrase(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "See FEAT-1000 for context.\n")
        modified = _auto_fix_file(p, done_ids={"FEAT-1000"})
        assert modified is False
        assert p.read_text(encoding="utf-8") == "See FEAT-1000 for context.\n"

    def test_preserves_code_fence_content(self, tmp_path: Path) -> None:
        content = "```\nFEAT-1000 is open\n```\nFEAT-1000 is open outside.\n"
        p = self._write(tmp_path, content)
        _auto_fix_file(p, done_ids={"FEAT-1000"})
        new = p.read_text(encoding="utf-8")
        # The code-fence line must remain unchanged
        assert "```\nFEAT-1000 is open\n```" in new
        # The line outside the fence must be rewritten
        assert "FEAT-1000 is done outside." in new

    def test_returns_false_for_nonexistent_file(self, tmp_path: Path) -> None:
        p = tmp_path / "does_not_exist.md"
        modified = _auto_fix_file(p, done_ids={"FEAT-1000"})
        assert modified is False

    def test_no_modification_when_id_not_in_done_ids(self, tmp_path: Path) -> None:
        p = self._write(tmp_path, "ENH-99 is open.\n")
        modified = _auto_fix_file(p, done_ids={"FEAT-1000"})
        assert modified is False

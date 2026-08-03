"""End-to-end tests for `ll-issues fold-findings` (ENH-2993).

Uses the `_invoke(argv)` + real `.issues/` fixture shape from
`test_ll_issues_research_triage.py` — a CLI round-trip through `main_issues()`,
not a direct call to the command function, because the stdin contract and the
exit-code table are the parts most likely to ship broken.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.issue_parser import count_enumerable_options


def _invoke(argv: list[str], stdin: str = "") -> int:
    """Invoke main_issues() with given argv and stdin payload."""
    with patch.object(sys, "argv", argv), patch.object(sys, "stdin", io.StringIO(stdin)):
        from little_loops.cli import main_issues

        return main_issues()


BODY = """---
id: ENH-1
status: open
priority: P3
---

# ENH-1: Sample

## Summary

A sample issue.

## Integration Map

### Files to Modify
- `pkg/mod.py` — change it

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-01-01 — based on codebase analysis:_

- pre-existing finding one

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-01-02 — based on codebase analysis:_

- pre-existing finding two

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-01-03 — based on codebase analysis:_

- pre-existing finding three

## Impact

- **Priority**: P3

## Session Log
- `/ll:capture-issue` - 2026-01-01T00:00:00 - `x.jsonl`

---

## Status

- **Status**: open
"""


@pytest.fixture
def fold_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    (root / ".ll").mkdir(parents=True)
    (root / ".issues" / "enhancements").mkdir(parents=True)
    (root / ".issues" / "enhancements" / "P3-ENH-1-sample.md").write_text(BODY, encoding="utf-8")
    monkeypatch.chdir(root)
    return root


def _issue(root: Path) -> Path:
    return root / ".issues" / "enhancements" / "P3-ENH-1-sample.md"


class TestExitCodes:
    def test_unresolvable_issue_exits_1(self, fold_project: Path) -> None:
        assert _invoke(["ll-issues", "fold-findings", "ENH-999", "--section", "Impact"], "- x") == 1

    def test_empty_stdin_exits_1(self, fold_project: Path) -> None:
        before = _issue(fold_project).read_bytes()
        assert _invoke(["ll-issues", "fold-findings", "ENH-1", "--section", "Impact"], "   \n") == 1
        assert _issue(fold_project).read_bytes() == before

    def test_absent_section_with_no_create_exits_2_and_writes_nothing(
        self, fold_project: Path
    ) -> None:
        before = _issue(fold_project).read_bytes()
        code = _invoke(
            ["ll-issues", "fold-findings", "ENH-1", "--section", "Program Design", "--no-create"],
            "- x",
        )
        assert code == 2
        assert _issue(fold_project).read_bytes() == before

    def test_absent_section_is_created_by_default(self, fold_project: Path) -> None:
        code = _invoke(
            ["ll-issues", "fold-findings", "ENH-1", "--section", "Program Design"], "- designed"
        )
        assert code == 0
        content = _issue(fold_project).read_text()
        assert "## Program Design" in content
        assert "- designed" in content
        # v2.0 template order: Program Design sits between Integration Map and Impact.
        assert content.index("## Integration Map") < content.index("## Program Design")
        assert content.index("## Program Design") < content.index("## Impact")


class TestFoldOnTouch:
    def test_collapses_pre_existing_stack(self, fold_project: Path) -> None:
        assert (
            _invoke(
                ["ll-issues", "fold-findings", "ENH-1", "--section", "Integration Map"],
                "- brand new finding",
            )
            == 0
        )
        content = _issue(fold_project).read_text()
        assert content.count("### Codebase Research Findings") == 1
        for text in ("finding one", "finding two", "finding three", "brand new finding"):
            assert text in content
        # Per-batch provenance survives: 3 pre-existing + 1 new.
        assert content.count("_Added by `/ll:refine-issue`") == 4
        # Sibling H3s and the footer are untouched.
        assert content.count("### Files to Modify") == 1
        assert "## Status" in content

    def test_frontmatter_preserved(self, fold_project: Path) -> None:
        _invoke(["ll-issues", "fold-findings", "ENH-1", "--section", "Integration Map"], "- new")
        assert _issue(fold_project).read_text().startswith("---\nid: ENH-1\n")

    def test_new_provenance_line_is_dated(self, fold_project: Path) -> None:
        _invoke(["ll-issues", "fold-findings", "ENH-1", "--section", "Impact"], "- new")
        content = _issue(fold_project).read_text()
        import re

        assert re.search(
            r"_Added by `/ll:refine-issue` — \d{4}-\d{2}-\d{2} — based on codebase analysis:_",
            content,
        )


class TestDryRun:
    def test_dry_run_writes_nothing_and_prints_block(
        self, fold_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        before = _issue(fold_project).read_bytes()
        code = _invoke(
            ["ll-issues", "fold-findings", "ENH-1", "--section", "Impact", "--dry-run"],
            "- would be added",
        )
        assert code == 0
        assert _issue(fold_project).read_bytes() == before
        out = capsys.readouterr().out
        assert "- would be added" in out
        assert "### Codebase Research Findings" in out

    def test_dry_run_does_not_collapse_a_stack(self, fold_project: Path) -> None:
        before = _issue(fold_project).read_bytes()
        _invoke(
            ["ll-issues", "fold-findings", "ENH-1", "--section", "Integration Map", "--dry-run"],
            "- x",
        )
        assert _issue(fold_project).read_bytes() == before
        assert _issue(fold_project).read_text().count("### Codebase Research Findings") == 3


class TestStdinVerbatim:
    def test_shell_metacharacters_and_wrapping_survive(self, fold_project: Path) -> None:
        payload = (
            "- `re.finditer($1)` costs $5 — really! see `pkg/mod.py:12`\n"
            "  continuation line two\n"
            "  continuation line three\n"
            "- second bullet"
        )
        assert _invoke(["ll-issues", "fold-findings", "ENH-1", "--section", "Impact"], payload) == 0
        assert payload in _issue(fold_project).read_text()

    def test_option_block_lands_verbatim_and_stays_countable(self, fold_project: Path) -> None:
        payload = (
            "**Option A**: keep the existing regex\n\n"
            "**Option B**: switch to a parser\n\n"
            "**Recommended**: Option A — cheaper"
        )
        code = _invoke(
            ["ll-issues", "fold-findings", "ENH-1", "--section", "Proposed Solution"], payload
        )
        assert code == 0
        content = _issue(fold_project).read_text()
        assert payload in content
        assert count_enumerable_options(content) == 2

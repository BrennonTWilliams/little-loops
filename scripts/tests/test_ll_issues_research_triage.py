"""End-to-end tests for `ll-issues research-triage` (ENH-2971).

Uses the `_invoke(argv)` + `capsys` + `json.loads` shape from
`test_ll_issues_format_check.py` — a real CLI round-trip through
`main_issues()`, not a direct call to the command function.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def _invoke(argv: list[str]) -> int:
    """Invoke main_issues() with given argv."""
    with patch.object(sys, "argv", argv):
        from little_loops.cli import main_issues

        return main_issues()


@pytest.fixture
def triage_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal project root with one enhancement issue and one source file.

    A *real* git repo, not a stub `.git` directory: references resolve against
    ENH-2983's tracked-file `RefIndex`, so an uncommitted file never resolves.
    """
    root = tmp_path / "proj"
    (root / ".ll").mkdir(parents=True)
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "mod.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (root / ".issues" / "enhancements").mkdir(parents=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "seed"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)
    monkeypatch.chdir(root)
    return root


def _write(root: Path, body: str, name: str = "P3-ENH-1-sample.md") -> Path:
    path = root / ".issues" / "enhancements" / name
    path.write_text(body, encoding="utf-8")
    return path


SPARSE = """---
id: ENH-1
type: ENH
status: open
---

# ENH-1: Sample

## Summary

Nothing resolvable here.
"""


class TestResearchTriageJson:
    """--json emits the three-key axis map."""

    def test_all_axes_unmet_exits_zero(
        self, triage_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(triage_project, SPARSE)

        code = _invoke(["ll-issues", "research-triage", "ENH-1", "--json"])
        payload = json.loads(capsys.readouterr().out)

        assert code == 0, "an unmet issue is the common case, not an error"
        assert set(payload) == {"locator", "analyzer", "pattern_finder"}
        for axis in payload.values():
            assert axis == {"covered": False, "evidence": ""}

    def test_covered_axis_reports_evidence(
        self, triage_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(
            triage_project,
            SPARSE + "\n## Integration Map\n\n- `pkg/mod.py` — the file\n",
        )

        code = _invoke(["ll-issues", "research-triage", "ENH-1", "--json"])
        payload = json.loads(capsys.readouterr().out)

        assert code == 0
        assert payload["locator"]["covered"] is True
        assert "pkg/mod.py" in payload["locator"]["evidence"]
        assert payload["analyzer"]["covered"] is False


class TestResearchTriageText:
    """The default (non-JSON) rendering is one line per axis."""

    def test_text_output_lists_every_axis(
        self, triage_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(triage_project, SPARSE)

        code = _invoke(["ll-issues", "research-triage", "ENH-1"])
        out = capsys.readouterr().out

        assert code == 0
        for axis in ("locator", "analyzer", "pattern_finder"):
            assert f"{axis}" in out
        assert out.count("unmet") == 3


class TestResearchTriageProgramDesignGate:
    """BUG-3003: a failing Program Design gate is visible in the `--json` surface."""

    def test_gate_active_missing_section_uncovers_analyzer(
        self, triage_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (triage_project / ".ll" / "program-design-cutover.json").write_text(
            json.dumps({"sha": "0" * 40, "date": "2026-01-01"}), encoding="utf-8"
        )
        body = (
            "---\nid: ENH-1\ntype: ENH\nstatus: open\ndiscovered_date: 2026-07-01\n---\n\n"
            "# ENH-1: Sample\n\n## Root Cause\n\n`helper()` in `pkg/mod.py` is wrong.\n"
        )
        _write(triage_project, body)

        code = _invoke(["ll-issues", "research-triage", "ENH-1", "--json"])
        payload = json.loads(capsys.readouterr().out)

        assert code == 0
        assert payload["analyzer"]["covered"] is False
        assert "Program Design gate" in payload["analyzer"]["evidence"]


class TestResearchTriageErrors:
    """Only an unresolvable issue ID is an error."""

    def test_unknown_issue_exits_nonzero(
        self, triage_project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(triage_project, SPARSE)

        code = _invoke(["ll-issues", "research-triage", "ENH-9999", "--json"])

        assert code != 0
        assert "not found" in capsys.readouterr().err

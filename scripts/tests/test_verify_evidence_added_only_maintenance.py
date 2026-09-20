"""ENH-3520: --added-only behavior on maintenance operations and staged-diff failure.

Records the *current* contract that keeps the pre-commit hook warn-only:
a pure rename re-exposes every line (the diff is pathspec-limited to the new
path, so git cannot pair it with the old one), a rewrite re-exposes grandfathered evidence as
"added", and a staged-diff failure silently degrades to a whole-file scan.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import little_loops.cli.verify_evidence as ve
from little_loops.config import BRConfig

GIT_TIMEOUT = 60
ARTIFACT = ".issues/enhancements/target.md"
BAD_QUOTE = "this fabricated sentence appears nowhere in the artifact"
OLD = ".issues/bugs/P3-BUG-9001-old.md"
NEW = ".issues/bugs/P3-BUG-9001-new.md"


def _git(cwd: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, timeout=GIT_TIMEOUT
    )


def _issue(extra: str = "") -> str:
    return (
        "---\nid: BUG-9001\ntype: BUG\nstatus: open\n---\n\n# BUG-9001: t\n\n"
        f"## Current Behavior\n\nThe target says `{BAD_QUOTE}` (`{ARTIFACT}`).\n{extra}"
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo whose HEAD already contains one grandfathered invalid quote."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".ll").mkdir()
    (tmp_path / ".ll" / "ll-config.json").write_text("{}\n")
    for d in ("bugs", "enhancements"):
        (tmp_path / ".issues" / d).mkdir(parents=True)
    (tmp_path / ARTIFACT).write_text("The verifier keeps a warm cache of span verdicts.\n")
    (tmp_path / OLD).write_text(_issue())
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _scan(repo: Path, rel: str) -> list[ve.EvidenceFinding]:
    return ve.scan_paths(repo, [Path(rel)], BRConfig(repo), added_only=True)


def test_pure_rename_reexposes_grandfathered_evidence(repo: Path) -> None:
    """Observed: a rename would block a blocking hook on evidence it never authored."""
    _git(repo, "mv", OLD, NEW)
    assert [f.line for f in _scan(repo, NEW)]


def test_rewrite_reexposes_grandfathered_evidence_as_added(repo: Path) -> None:
    """Editing the line that carries the old quote makes it an added line."""
    (repo / OLD).write_text(_issue().replace("The target says", "The target still says"))
    _git(repo, "add", OLD)
    findings = _scan(repo, OLD)
    assert [f.line for f in findings] and BAD_QUOTE in findings[0].span


def test_unrelated_edit_leaves_grandfathered_evidence_alone(repo: Path) -> None:
    (repo / OLD).write_text(_issue("\nUnrelated appended note.\n"))
    _git(repo, "add", OLD)
    assert _scan(repo, OLD) == []


def test_staged_diff_failure_silently_falls_back_to_whole_file_scan(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Current contract: git failure -> ``None`` -> whole-file scan, no diagnostic.

    This surfaces grandfathered findings and is why the hook stays warn-only.
    """
    (repo / OLD).write_text(_issue("\nUnrelated appended note.\n"))
    _git(repo, "add", OLD)

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("git unavailable")

    monkeypatch.setattr(ve.subprocess, "run", boom)
    assert ve.staged_added_lines(repo, [Path(OLD)]) is None
    monkeypatch.undo()
    monkeypatch.setattr(ve, "staged_added_lines", lambda *_a, **_k: None)
    assert _scan(repo, OLD), "whole-file fallback should surface the grandfathered finding"

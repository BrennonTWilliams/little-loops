"""Tests for the HEAD-blob issue-corpus reader (ENH-3697)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from little_loops.config.core import BRConfig
from little_loops.issue_parser import check_format_gaps, find_issues
from little_loops.issue_progress import _ALL_STATUSES
from tests import test_prose_dep_sweep_gate as sweep
from tests.head_corpus import (
    CORPUS_GATE_ENV,
    BlobPath,
    corpus_gate_at_head,
    head_issue_blobs,
    head_issue_infos,
)
from tests.helpers import copy_git_template

CLEAN = "---\nid: BUG-002\ntype: BUG\nstatus: open\n---\n\n# BUG-002: dep\n\n## Summary\n\nok\n"
DRIFTING = (
    "---\nid: BUG-001\ntype: BUG\nstatus: open\n---\n\n# BUG-001: x\n\n"
    "## Summary\n\nBlocked by BUG-002 before this can land.\n"
)
NON_DRIFTING = DRIFTING.replace("Blocked by BUG-002 before this can land.", "Standalone.")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _write(repo: Path, rel: str, text: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    copy_git_template(tmp_path)
    _write(tmp_path, ".issues/bugs/P3-BUG-001-x.md", NON_DRIFTING)
    _write(tmp_path, ".issues/bugs/P3-BUG-002-dep.md", CLEAN)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "seed")
    return tmp_path


def _sweep(monkeypatch: pytest.MonkeyPatch, repo: Path, *, at_head: bool) -> None:
    monkeypatch.setattr(sweep, "_REPO_ROOT", repo)
    if at_head:
        monkeypatch.setenv(CORPUS_GATE_ENV, "1")
    else:
        monkeypatch.delenv(CORPUS_GATE_ENV, raising=False)
    sweep.test_no_prose_dependency_drift_in_repo()


class TestFlag:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(None, False), ("", False), ("0", False), ("false", False), ("1", True), ("yes", True)],
    )
    def test_corpus_gate_at_head(
        self, monkeypatch: pytest.MonkeyPatch, value: str | None, expected: bool
    ) -> None:
        if value is None:
            monkeypatch.delenv(CORPUS_GATE_ENV, raising=False)
        else:
            monkeypatch.setenv(CORPUS_GATE_ENV, value)
        assert corpus_gate_at_head() is expected


class TestHeadBlobs:
    def test_blobs_are_committed_text_not_working_tree(self, repo: Path) -> None:
        _write(repo, ".issues/bugs/P3-BUG-001-x.md", DRIFTING)
        _write(repo, ".issues/bugs/P3-BUG-003-new.md", CLEAN)  # untracked
        blobs = head_issue_blobs(BRConfig(repo))
        assert blobs is not None
        assert set(blobs) == {
            ".issues/bugs/P3-BUG-001-x.md",
            ".issues/bugs/P3-BUG-002-dep.md",
        }
        assert blobs[".issues/bugs/P3-BUG-001-x.md"] == NON_DRIFTING.encode()

    def test_parity_with_find_issues_on_clean_tree(self, repo: Path) -> None:
        config = BRConfig(repo)
        blobs = head_issue_blobs(config)
        assert blobs is not None
        head = {i.issue_id: i.status for i, _ in head_issue_infos(config, blobs)}
        tree = {i.issue_id: i.status for i in find_issues(config, status_filter=set(_ALL_STATUSES))}
        assert head == tree and head

    def test_no_head_returns_none(self, tmp_path: Path) -> None:
        copy_git_template(tmp_path)  # commitless repo
        _write(tmp_path, ".issues/bugs/P3-BUG-001-x.md", NON_DRIFTING)
        assert head_issue_blobs(BRConfig(tmp_path)) is None

    def test_not_a_git_repo_returns_none(self, tmp_path: Path) -> None:
        _write(tmp_path, ".issues/bugs/P3-BUG-001-x.md", NON_DRIFTING)
        assert head_issue_blobs(BRConfig(tmp_path)) is None


class TestBlobPath:
    def test_stamped_repo_and_deprecated_key(self, repo: Path) -> None:
        """check_format_gaps walks resolve()/parents on its path argument."""
        _write(
            repo,
            ".ll/program-design-cutover.json",
            '{"sha": "0000000000000000000000000000000000000000", "date": "2026-01-01"}',
        )
        _write(
            repo,
            ".issues/bugs/P3-BUG-004-old.md",
            "---\nid: BUG-004\ntype: BUG\nstatus: open\nsuperseded_by: BUG-002\n---\n\n"
            "# BUG-004: old\n\n## Summary\n\nx\n",
        )
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "stamp")
        config = BRConfig(repo)
        blobs = head_issue_blobs(config)
        assert blobs is not None
        pairs = {i.issue_id: p for i, p in head_issue_infos(config, blobs)}
        gaps = check_format_gaps(pairs["BUG-004"], issue_statuses={"BUG-004": "open"})
        assert any(g.startswith("superseded_by") for g in gaps.deprecated_key)

    def test_reads_blob_not_disk(self, tmp_path: Path) -> None:
        on_disk = _write(tmp_path, "a.md", "disk")
        bp = BlobPath(on_disk, b"blob")
        assert bp.read_text() == "blob"
        assert bp.read_bytes() == b"blob"
        assert bp.name == "a.md"
        assert bp.parent == tmp_path


class TestSweepAtHead:
    def test_flag_set_uncommitted_drift_passes(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(repo, ".issues/bugs/P3-BUG-001-x.md", DRIFTING)
        _sweep(monkeypatch, repo, at_head=True)

    def test_flag_set_committed_drift_fails(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(repo, ".issues/bugs/P3-BUG-001-x.md", DRIFTING)
        _git(repo, "commit", "-qam", "drift")
        with pytest.raises(AssertionError, match="BUG-001"):
            _sweep(monkeypatch, repo, at_head=True)

    def test_flag_unset_uncommitted_drift_fails(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(repo, ".issues/bugs/P3-BUG-001-x.md", DRIFTING)
        with pytest.raises(AssertionError, match="BUG-001"):
            _sweep(monkeypatch, repo, at_head=False)

    def test_flag_set_without_head_falls_back_to_working_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        copy_git_template(tmp_path)  # no commits -> no HEAD
        _write(tmp_path, ".issues/bugs/P3-BUG-001-x.md", DRIFTING)
        _write(tmp_path, ".issues/bugs/P3-BUG-002-dep.md", CLEAN)
        with pytest.raises(AssertionError, match="BUG-001"):
            _sweep(monkeypatch, tmp_path, at_head=True)

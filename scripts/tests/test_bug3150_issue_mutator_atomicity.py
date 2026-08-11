"""Tests for BUG-3150: issue-file mutators write unlocked and non-atomically.

`set-status` and `link` did read-modify-write via bare `Path.write_text`, which
truncates before writing — an interleaved or interrupted write could leave a torn
or empty issue file. `append-log` was already atomic but unlocked, so two
concurrent appends could each read the pre-entry content and lose one.

The fix wraps each mutator's read-modify-write in `file_utils.acquire_lock` on a
tree-wide `.issues/.mutate.lock` and routes every write through
`file_utils.atomic_write`.

Scope note: the lock makes the mutation atomic with respect to *other lock-taking
writers*. It does not make `link`'s two-file write crash-atomic — a process killed
between the source and reciprocal writes still leaves a half-linked pair. That
needs a journal, not a lock, and is out of scope here; see the issue's AC 5.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.file_utils import issue_lock_path


def _write_config(temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
    (temp_project_dir / ".ll" / "ll-config.json").write_text(json.dumps(sample_config))


def _run_issues(*argv: str) -> int:
    from little_loops.cli import main_issues

    with patch.object(sys, "argv", ["ll-issues", *argv]):
        return main_issues()


class TestIssueLockPath:
    """The shared lock-path derivation every mutator agrees on."""

    def test_lock_is_tree_wide_not_per_type_directory(self, tmp_path: Path) -> None:
        """A features/ issue and a bugs/ issue resolve to the SAME lock file.

        A per-directory lock would let `set-status` on a FEAT run concurrently
        with `link` on a BUG in the same tree, which is the race this fixes.
        """
        feat = tmp_path / ".issues" / "features" / "P3-FEAT-1-a.md"
        bug = tmp_path / ".issues" / "bugs" / "P2-BUG-2-b.md"
        for p in (feat, bug):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("---\nid: X\n---\n")

        assert issue_lock_path(feat) == issue_lock_path(bug)
        assert issue_lock_path(feat).name == ".mutate.lock"
        assert issue_lock_path(feat).parent == (tmp_path / ".issues").resolve()

    def test_lock_never_escapes_the_directory_when_no_issues_ancestor(self, tmp_path: Path) -> None:
        """A bare path outside an issue tree locks in its OWN directory.

        Deriving the lock positionally (``parent.parent``) put it one level above
        the caller's directory, so every unrelated caller under a shared parent —
        e.g. every pytest ``tmp_path`` under one session root — contended on a
        single lock file.
        """
        stray = tmp_path / "issue.md"
        stray.write_text("---\nid: X\n---\n")

        lock = issue_lock_path(stray)
        assert lock.parent == tmp_path.resolve(), f"lock escaped its directory: {lock}"
        assert tmp_path.resolve() in lock.parents or lock.parent == tmp_path.resolve()

    def test_custom_base_dir_is_honoured(self, tmp_path: Path) -> None:
        """A project configuring a non-default issues base_dir still gets one tree lock."""
        issue = tmp_path / "tickets" / "bugs" / "P2-BUG-1-x.md"
        issue.parent.mkdir(parents=True, exist_ok=True)
        issue.write_text("---\nid: BUG-1\n---\n")

        assert (
            issue_lock_path(issue, "tickets") == (tmp_path / "tickets").resolve() / ".mutate.lock"
        )

    def test_lock_is_distinct_from_id_allocation_lock(self, tmp_path: Path) -> None:
        """ID allocation and issue mutation must not serialize against each other."""
        issue = tmp_path / ".issues" / "features" / "P3-FEAT-1-a.md"
        issue.parent.mkdir(parents=True, exist_ok=True)
        issue.write_text("---\nid: X\n---\n")

        assert issue_lock_path(issue).name != ".id-alloc.lock"


class TestAtomicWrites:
    """AC 1: no mutation path leaves a torn file — every write goes via os.replace."""

    def test_set_status_writes_via_os_replace(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        _write_config(temp_project_dir, sample_config)
        issue = issues_dir / "bugs" / "P0-BUG-001-crash.md"
        issue.write_text("---\nid: BUG-001\nstatus: open\n---\n# BUG-001: Crash\n")

        replaced: list[Path] = []
        original = os.replace

        def capture(src, dst):  # noqa: ANN001
            replaced.append(Path(dst).resolve())
            original(src, dst)

        with patch("os.replace", side_effect=capture):
            rc = _run_issues(
                "set-status", "BUG-001", "in_progress", "--config", str(temp_project_dir)
            )

        assert rc == 0
        assert issue.resolve() in replaced, (
            "set-status must write the issue file via atomic_write/os.replace"
        )
        assert "status: in_progress" in issue.read_text()

    def test_link_writes_via_os_replace(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        _write_config(temp_project_dir, sample_config)
        src = issues_dir / "features" / "P3-FEAT-010-src.md"
        dst = issues_dir / "features" / "P3-FEAT-011-dst.md"
        src.write_text("---\nid: FEAT-010\nstatus: open\n---\n# FEAT-010: Src\n")
        dst.write_text("---\nid: FEAT-011\nstatus: open\n---\n# FEAT-011: Dst\n")

        replaced: list[Path] = []
        original = os.replace

        def capture(s, d):  # noqa: ANN001
            replaced.append(Path(d).resolve())
            original(s, d)

        with patch("os.replace", side_effect=capture):
            rc = _run_issues(
                "link", "FEAT-010", "--depends-on", "FEAT-011", "--config", str(temp_project_dir)
            )

        assert rc == 0
        assert src.resolve() in replaced, (
            "link must write the source file via atomic_write/os.replace"
        )
        assert "FEAT-011" in src.read_text()

    def test_no_orphan_tmp_files_left_behind(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """atomic_write's sibling tempfile must never survive a successful write."""
        _write_config(temp_project_dir, sample_config)
        issue = issues_dir / "bugs" / "P0-BUG-002-x.md"
        issue.write_text("---\nid: BUG-002\nstatus: open\n---\n# BUG-002: X\n")

        assert _run_issues("set-status", "BUG-002", "done", "--config", str(temp_project_dir)) == 0
        assert list(issue.parent.glob("*.tmp")) == []


class TestLockIsTaken:
    """AC 2/3: each mutator holds the tree lock across its read-modify-write."""

    def test_set_status_acquires_the_issue_lock(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        _write_config(temp_project_dir, sample_config)
        issue = issues_dir / "bugs" / "P0-BUG-003-y.md"
        issue.write_text("---\nid: BUG-003\nstatus: open\n---\n# BUG-003: Y\n")

        seen: list[Path] = []
        from little_loops import file_utils

        original = file_utils.acquire_lock

        def spy(path, timeout=10.0):  # noqa: ANN001
            seen.append(Path(path))
            return original(path, timeout)

        with patch("little_loops.file_utils.acquire_lock", side_effect=spy):
            rc = _run_issues("set-status", "BUG-003", "done", "--config", str(temp_project_dir))

        assert rc == 0
        assert issue_lock_path(issue) in seen

    def test_link_holds_a_single_lock_across_source_and_reciprocal(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """AC 3: one hold spans both writes.

        Two separate holds would be the half-linked-graph window; it would also
        deadlock, since flock contends within a single process.
        """
        _write_config(temp_project_dir, sample_config)
        src = issues_dir / "features" / "P3-FEAT-020-src.md"
        dst = issues_dir / "features" / "P3-FEAT-021-dst.md"
        src.write_text("---\nid: FEAT-020\nstatus: open\n---\n# FEAT-020: Src\n")
        dst.write_text("---\nid: FEAT-021\nstatus: open\n---\n# FEAT-021: Dst\n")

        acquisitions: list[Path] = []
        from little_loops import file_utils

        original = file_utils.acquire_lock

        def spy(path, timeout=10.0):  # noqa: ANN001
            acquisitions.append(Path(path))
            return original(path, timeout)

        with patch("little_loops.file_utils.acquire_lock", side_effect=spy):
            rc = _run_issues(
                "link",
                "FEAT-020",
                "--relates-to",
                "FEAT-021",
                "--reciprocal",
                "--config",
                str(temp_project_dir),
            )

        assert rc == 0
        assert acquisitions.count(issue_lock_path(src)) == 1, (
            f"link must take the mutation lock exactly once, got {acquisitions}"
        )
        # Both edges written under that single hold.
        assert "FEAT-021" in src.read_text()
        assert "FEAT-020" in dst.read_text()

    def test_append_log_acquires_the_issue_lock(self, tmp_path: Path) -> None:
        """append-log was already atomic but unlocked — two appends could lose one."""
        from little_loops.session_log import append_session_log_entry

        issue = tmp_path / ".issues" / "bugs" / "P0-BUG-004-z.md"
        issue.parent.mkdir(parents=True, exist_ok=True)
        issue.write_text("---\nid: BUG-004\n---\n# BUG-004: Z\n")
        jsonl = tmp_path / "session.jsonl"

        seen: list[Path] = []
        from little_loops import file_utils

        original = file_utils.acquire_lock

        def spy(path, timeout=10.0):  # noqa: ANN001
            seen.append(Path(path))
            return original(path, timeout)

        # session_log binds acquire_lock at module import (unlike set_status/link,
        # which import it inside the function), so the spy must target that name.
        with patch("little_loops.session_log.acquire_lock", side_effect=spy):
            assert append_session_log_entry(issue, "/ll:test", session_jsonl=jsonl) is True

        assert issue_lock_path(issue) in seen


class TestConcurrency:
    """AC 4: concurrent writers leave a valid file, never a torn or empty one."""

    def test_concurrent_set_status_leaves_one_valid_winning_status(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        """N threads flip the same issue between two statuses.

        flock contends within a process as well as across processes, so threads
        exercise the same serialization a second `ll-issues` process would.
        """
        from little_loops.config import BRConfig
        from little_loops.frontmatter import parse_frontmatter

        _write_config(temp_project_dir, sample_config)
        issue = issues_dir / "bugs" / "P0-BUG-005-race.md"
        issue.write_text("---\nid: BUG-005\nstatus: open\n---\n# BUG-005: Race\n" + "body\n" * 200)

        from little_loops.cli.issues.set_status import cmd_set_status

        config = BRConfig(temp_project_dir)
        barrier = threading.Barrier(8)
        errors: list[BaseException] = []

        def flip(status: str) -> None:
            class Args:
                issue_id = "BUG-005"
                cascade = False
                cascade_to = "done"
                reason = None
                by = None

            Args.status = status  # type: ignore[attr-defined]
            try:
                barrier.wait(timeout=30)
                cmd_set_status(config, Args())  # type: ignore[arg-type]
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=flip, args=("in_progress" if i % 2 else "blocked",))
            for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert not errors, f"concurrent set-status raised: {errors}"

        content = issue.read_text()
        assert content.strip(), "issue file must not be left empty (torn write)"
        fm = parse_frontmatter(content)
        assert fm.get("id") == "BUG-005", f"frontmatter must still parse, got: {content[:200]!r}"
        assert fm.get("status") in {"in_progress", "blocked"}
        assert "body" in content, "body must survive; a torn write would truncate it"
        assert list(issue.parent.glob("*.tmp")) == []


class TestNoBareWriteTextRemains:
    """AC 1, enforced at the source level so a future edit can't silently regress."""

    @pytest.mark.parametrize(
        "module",
        [
            "little_loops/cli/issues/set_status.py",
            "little_loops/cli/issues/link.py",
            "little_loops/session_log.py",
        ],
    )
    def test_mutation_module_has_no_write_text_call(self, module: str) -> None:
        source_root = Path(__file__).resolve().parent.parent
        text = (source_root / module).read_text()
        offenders = [
            line.strip()
            for line in text.splitlines()
            if re.search(r"\.write_text\s*\(", line) and not line.strip().startswith("#")
        ]
        assert not offenders, (
            f"{module} must write issue files via file_utils.atomic_write, "
            f"not Path.write_text (BUG-3150). Offending lines: {offenders}"
        )

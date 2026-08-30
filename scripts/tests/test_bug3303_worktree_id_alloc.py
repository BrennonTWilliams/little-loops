"""Tests for BUG-3303: issue ID allocation inside worktrees collides with main tree IDs.

Real ``git init`` + ``git worktree add`` fixtures (precedent:
``test_worktree_utils.py``'s ``_init_repo``/``copy_git_template``), since the fix
resolves the main checkout from a linked worktree's ``.git`` file.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from little_loops.config import BRConfig
from little_loops.issue_parser import (
    get_next_issue_number,
    id_alloc_highwater_path,
    read_id_alloc_highwater,
    write_id_alloc_highwater,
)
from little_loops.paths import resolve_main_worktree_root
from tests.helpers import copy_git_template


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _init_main_repo(path: Path, sample_config: dict[str, Any]) -> Path:
    """Initialize a git repo with a commit and a `.ll`/`.issues` tree."""
    copy_git_template(path)
    ll_dir = path / ".ll"
    ll_dir.mkdir(exist_ok=True)
    (ll_dir / "ll-config.json").write_text(json.dumps(sample_config))
    (path / "README.md").write_text("main\n")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial commit")
    return path


def _add_worktree(main_repo: Path, worktree_path: Path, branch: str) -> Path:
    _git(main_repo, "worktree", "add", "-b", branch, str(worktree_path))
    return worktree_path


class TestResolveMainWorktreeRoot:
    def test_primary_checkout_returns_none(
        self, tmp_path: Path, sample_config: dict[str, Any]
    ) -> None:
        """A primary checkout (`.git` is a directory) needs no redirect."""
        main = _init_main_repo(tmp_path / "main", sample_config)
        assert resolve_main_worktree_root(main) is None

    def test_non_git_directory_returns_none(self, tmp_path: Path) -> None:
        assert resolve_main_worktree_root(tmp_path / "not-a-repo") is None

    def test_linked_worktree_resolves_main_root(
        self, tmp_path: Path, sample_config: dict[str, Any]
    ) -> None:
        main = _init_main_repo(tmp_path / "main", sample_config)
        worktree = _add_worktree(main, tmp_path / "wt", "feature")

        resolved = resolve_main_worktree_root(worktree)

        assert resolved == main.resolve()

    def test_main_tree_deleted_returns_none(
        self, tmp_path: Path, sample_config: dict[str, Any]
    ) -> None:
        """Graceful degradation: main tree gone (e.g. `.git` file dangling)."""
        main = _init_main_repo(tmp_path / "main", sample_config)
        worktree = _add_worktree(main, tmp_path / "wt", "feature")
        # Corrupt the gitdir pointer to simulate an unreachable main tree.
        (worktree / ".git").write_text("gitdir: /nonexistent/.git/worktrees/wt\n")

        assert resolve_main_worktree_root(worktree) is None


class TestGetNextIssueNumberWorktreeUnion:
    def test_worktree_scan_includes_main_tree_issues(
        self, tmp_path: Path, sample_config: dict[str, Any]
    ) -> None:
        """A stale worktree must never allocate an ID <= main's max (AC1)."""
        main = _init_main_repo(tmp_path / "main", sample_config)
        worktree = _add_worktree(main, tmp_path / "wt", "stale-branch")

        # Worktree's own .issues tree is empty/stale.
        (worktree / ".issues" / "bugs").mkdir(parents=True, exist_ok=True)

        # Main tree advances past the worktree's fork point.
        main_bugs = main / ".issues" / "bugs"
        main_bugs.mkdir(parents=True, exist_ok=True)
        (main_bugs / "P2-BUG-3117-existing.md").write_text("# BUG-3117")

        wt_config = BRConfig(worktree)
        next_num = get_next_issue_number(wt_config, "bugs")

        assert next_num == 3118

    def test_primary_checkout_unaffected(
        self, tmp_path: Path, sample_config: dict[str, Any]
    ) -> None:
        """Behavior unchanged in the primary checkout (AC5)."""
        main = _init_main_repo(tmp_path / "main", sample_config)
        bugs_dir = main / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        (bugs_dir / "P2-BUG-005-existing.md").write_text("# BUG-005")

        config = BRConfig(main)
        assert get_next_issue_number(config, "bugs") == 6

    def test_main_tree_missing_issues_dir_degrades_gracefully(
        self, tmp_path: Path, sample_config: dict[str, Any]
    ) -> None:
        """A worktree whose main tree lacks `.issues/` degrades to local-only (AC5)."""
        main = _init_main_repo(tmp_path / "main", sample_config)
        worktree = _add_worktree(main, tmp_path / "wt", "feature")

        wt_bugs = worktree / ".issues" / "bugs"
        wt_bugs.mkdir(parents=True, exist_ok=True)
        (wt_bugs / "P2-BUG-002-local.md").write_text("# BUG-002")

        wt_config = BRConfig(worktree)
        assert get_next_issue_number(wt_config, "bugs") == 3

    def test_sibling_worktrees_use_highwater_to_avoid_collision(
        self, tmp_path: Path, sample_config: dict[str, Any]
    ) -> None:
        """Two sibling worktrees allocating without merging never collide (AC2)."""
        main = _init_main_repo(tmp_path / "main", sample_config)
        wt_a = _add_worktree(main, tmp_path / "wt-a", "feature-a")
        wt_b = _add_worktree(main, tmp_path / "wt-b", "feature-b")
        (wt_a / ".issues" / "bugs").mkdir(parents=True, exist_ok=True)
        (wt_b / ".issues" / "bugs").mkdir(parents=True, exist_ok=True)

        config_a = BRConfig(wt_a)
        num_a = get_next_issue_number(config_a, "bugs")
        # Simulate wt-a's allocation completing: the file lands only in A's
        # tree, but the highwater mark in main is durably advanced.
        (wt_a / ".issues" / "bugs" / f"P2-BUG-{num_a:03d}-a.md").write_text("# a")
        write_id_alloc_highwater(id_alloc_highwater_path(config_a), num_a)

        config_b = BRConfig(wt_b)
        num_b = get_next_issue_number(config_b, "bugs")

        assert num_b > num_a

    def test_highwater_recovery_on_corrupt_file(
        self, tmp_path: Path, sample_config: dict[str, Any]
    ) -> None:
        main = _init_main_repo(tmp_path / "main", sample_config)
        (main / ".issues" / "bugs").mkdir(parents=True, exist_ok=True)
        highwater = main / ".issues" / ".id-alloc-highwater"
        highwater.write_text("not-a-number")

        assert read_id_alloc_highwater(highwater) == 0

        config = BRConfig(main)
        assert get_next_issue_number(config, "bugs") == 1


class TestCreateIssueCrossTreeLock:
    def test_create_issue_from_worktree_avoids_main_collision(
        self, tmp_path: Path, sample_config: dict[str, Any]
    ) -> None:
        from little_loops.cli.issues.create import IssueSpec, create_issue

        main = _init_main_repo(tmp_path / "main", sample_config)
        worktree = _add_worktree(main, tmp_path / "wt", "stale-branch")
        (worktree / ".issues" / "bugs").mkdir(parents=True, exist_ok=True)

        main_bugs = main / ".issues" / "bugs"
        main_bugs.mkdir(parents=True, exist_ok=True)
        (main_bugs / "P2-BUG-020-existing.md").write_text("# BUG-020")

        wt_config = BRConfig(worktree)
        created = create_issue(wt_config, IssueSpec(type="BUG", title="New bug", priority="P2"))

        assert created.id == "BUG-021"
        # The highwater file is written to the *main* tree's .issues/, not the
        # worktree's, so it's visible to any other tree resolving the same main.
        assert (main / ".issues" / ".id-alloc-highwater").read_text().strip() == "21"

    def test_next_id_preview_matches_create(
        self, tmp_path: Path, sample_config: dict[str, Any]
    ) -> None:
        """`ll-issues next-id` must preview the same ID `create` then allocates (AC4)."""
        from little_loops.cli.issues.create import IssueSpec, create_issue

        main = _init_main_repo(tmp_path / "main", sample_config)
        worktree = _add_worktree(main, tmp_path / "wt", "feature")
        (worktree / ".issues" / "bugs").mkdir(parents=True, exist_ok=True)
        (main / ".issues" / "bugs").mkdir(parents=True, exist_ok=True)

        wt_config = BRConfig(worktree)
        preview = get_next_issue_number(wt_config)
        created = create_issue(
            wt_config, IssueSpec(type="BUG", title="Preview parity", priority="P2")
        )

        assert f"BUG-{preview:03d}" == created.id

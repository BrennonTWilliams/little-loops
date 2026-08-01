"""Tests for git_operations module - specifically get_untracked_files."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.git_operations import get_untracked_files

pytestmark = pytest.mark.integration


class TestGetUntrackedFiles:
    """Tests for get_untracked_files function."""

    def test_returns_empty_list_when_no_untracked_files(self, tmp_path: Path) -> None:
        """Returns empty list when git status shows no untracked files."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            result = get_untracked_files(tmp_path)

        assert result == []

    def test_returns_untracked_files(self, tmp_path: Path) -> None:
        """Returns list of untracked files from git status."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="?? file1.txt\n?? file2.py\n?? dir/file3.md\n",
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert result == ["dir/file3.md", "file1.txt", "file2.py"]

    def test_handles_files_with_spaces(self, tmp_path: Path) -> None:
        """Handles quoted filenames containing spaces."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            # Git quotes filenames with spaces
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='?? "file with spaces.txt"\n?? normal.txt\n',
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert "file with spaces.txt" in result
        assert "normal.txt" in result

    def test_handles_special_characters(self, tmp_path: Path) -> None:
        """Handles files with special characters in names."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="?? file-with-dash.txt\n?? file_underscore.py\n?? file.multiple.dots.md\n",
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert "file-with-dash.txt" in result
        assert "file_underscore.py" in result
        assert "file.multiple.dots.md" in result

    def test_ignores_non_untracked_status(self, tmp_path: Path) -> None:
        """Only extracts files with ?? status (untracked), ignores others."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            # Git porcelain format includes various status codes:
            # M = modified, A = added, D = deleted, ?? = untracked
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=" M modified.txt\nA  staged.txt\n D deleted.txt\n?? untracked.txt\nAM both.py\n",
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert result == ["untracked.txt"]

    def test_returns_empty_on_git_failure(self, tmp_path: Path) -> None:
        """Returns empty list when git command fails."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=128, cmd=["git", "status", "--porcelain"]
            )

            result = get_untracked_files(tmp_path)

        assert result == []

    def test_returns_empty_on_file_not_found(self, tmp_path: Path) -> None:
        """Returns empty list when git executable is not found."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")

            result = get_untracked_files(tmp_path)

        assert result == []

    def test_returns_sorted_files(self, tmp_path: Path) -> None:
        """Returns files in sorted order."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="?? zebra.txt\n?? alpha.txt\n?? middle.txt\n",
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert result == ["alpha.txt", "middle.txt", "zebra.txt"]

    def test_uses_correct_cwd(self, tmp_path: Path) -> None:
        """Verifies repo_root is used as the working directory."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            get_untracked_files(tmp_path)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == tmp_path.resolve()

    def test_handles_empty_lines_in_output(self, tmp_path: Path) -> None:
        """Handles empty lines in git output gracefully."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="\n?? file.txt\n\n?? other.txt\n\n",
                stderr="",
            )

            result = get_untracked_files(tmp_path)

        assert result == ["file.txt", "other.txt"]

    def test_default_repo_root(self) -> None:
        """Uses current directory when repo_root not specified."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            get_untracked_files()

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == Path(".").resolve()

    def test_correct_git_command(self, tmp_path: Path) -> None:
        """Verifies correct git command is executed."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            get_untracked_files(tmp_path)

        call_args = mock_run.call_args[0][0]
        assert call_args == ["git", "status", "--porcelain"]

    @pytest.mark.parametrize(
        "stdout,expected",
        [
            ("", []),
            ("?? single.txt\n", ["single.txt"]),
            ("?? a.txt\n?? b.txt\n", ["a.txt", "b.txt"]),
            ('?? "has spaces.txt"\n', ["has spaces.txt"]),
            (" M modified.txt\n", []),
        ],
        ids=["empty", "single", "multiple", "quoted", "modified_only"],
    )
    def test_various_outputs(self, tmp_path: Path, stdout: str, expected: list[str]) -> None:
        """Parametrized test for various git output scenarios."""
        with patch("little_loops.git_operations.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=stdout, stderr=""
            )

            result = get_untracked_files(tmp_path)

        assert result == expected


class TestPorcelainPaths:
    """BUG-2963: NUL-delimited porcelain parsing, promoted from codegraph."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("", []),
            ("?? new.py\x00", ["new.py"]),
            (" M mod.py\x00?? new.py\x00", ["mod.py", "new.py"]),
            # A rename record is two fields: new path, then old path. Only the
            # new path is returned, and the old path must not leak through as a
            # phantom entry.
            ("R  new.py\x00old.py\x00", ["new.py"]),
            ("C  copy.py\x00src.py\x00?? other.py\x00", ["copy.py", "other.py"]),
            # Paths with spaces need no quoting under -z.
            ("?? has spaces.py\x00", ["has spaces.py"]),
            # Non-ASCII survives intact rather than arriving octal-escaped.
            ("?? café.py\x00", ["café.py"]),
            # A path containing the newline-format arrow is unambiguous here.
            ("?? weird -> name.py\x00", ["weird -> name.py"]),
        ],
        ids=[
            "empty",
            "untracked",
            "mixed",
            "rename_skips_old_path",
            "copy_then_untracked",
            "spaces",
            "non_ascii",
            "arrow_in_filename",
        ],
    )
    def test_parsing(self, raw: str, expected: list[str]) -> None:
        from little_loops.git_operations import porcelain_paths

        assert porcelain_paths(raw) == expected


class TestSnapshotAndPreserve:
    """BUG-2963: pre-run snapshot + non-destructive dirty-tree preservation."""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        from tests.helpers import copy_git_template

        copy_git_template(tmp_path)
        (tmp_path / "seed.txt").write_text("seed\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)
        return tmp_path

    def test_snapshot_is_empty_on_clean_tree(self, repo: Path) -> None:
        from little_loops.git_operations import snapshot_dirty_paths

        assert snapshot_dirty_paths(repo) == frozenset()

    def test_snapshot_captures_dirty_paths(self, repo: Path) -> None:
        from little_loops.git_operations import snapshot_dirty_paths

        (repo / "wip.py").write_text("x = 1\n")
        assert snapshot_dirty_paths(repo) == frozenset({"wip.py"})

    def test_snapshot_fails_closed_to_empty_outside_a_repo(self, tmp_path: Path) -> None:
        """A git failure yields an empty set — the direction that preserves more."""
        from little_loops.git_operations import snapshot_dirty_paths

        assert snapshot_dirty_paths(tmp_path / "nonexistent") == frozenset()

    def test_preserve_writes_ref_without_touching_the_tree(self, repo: Path) -> None:
        from little_loops.git_operations import abandoned_ref_name, preserve_dirty_tree

        (repo / "wip.py").write_text("x = 1\n")
        status_before = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
        ).stdout
        index_before = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], cwd=repo, capture_output=True, text=True
        ).stdout

        ref = abandoned_ref_name("BUG-001")
        sha = preserve_dirty_tree(repo, ref)

        assert sha, "expected a preservation commit SHA"
        assert (
            subprocess.run(
                ["git", "show", f"{ref}:wip.py"], cwd=repo, capture_output=True, text=True
            ).stdout
            == "x = 1\n"
        )
        # AC #5: working tree and index byte-identical afterwards.
        status_after = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
        ).stdout
        index_after = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], cwd=repo, capture_output=True, text=True
        ).stdout
        assert status_after == status_before
        assert index_after == index_before
        assert (repo / "wip.py").read_text() == "x = 1\n"

    def test_preserve_is_a_noop_on_a_clean_tree(self, repo: Path) -> None:
        from little_loops.git_operations import abandoned_ref_name, preserve_dirty_tree

        assert preserve_dirty_tree(repo, abandoned_ref_name("BUG-001")) is None

    def test_no_code_path_invokes_git_stash(self) -> None:
        """AC #5: `git stash` is forbidden — it removes what it claims to preserve.

        In the ``ll-auto`` case there is no worktree: the tree being preserved
        is the user's own, and stash would sweep away the pre-existing WIP that
        BUG-2421's guarantee exists to leave untouched. Pinned as a source-level
        assertion because the failure is silent and destructive.
        """
        from pathlib import Path as _Path

        import little_loops.git_operations as gitops

        source = _Path(gitops.__file__).read_text()
        assert '"stash"' not in source, "git stash must never appear in a subprocess argv"
        assert "'stash'" not in source, "git stash must never appear in a subprocess argv"


class TestPreserveBeforeTeardown:
    """BUG-2963 #8 / AC #7: the worktree-teardown preservation backstop.

    The per-issue run-window discriminator rescues only the first orphan: work
    that survives one issue's close is pre-existing WIP from the next issue's
    point of view, so it is left alone by design and destroyed at teardown.
    This backstop closes that gap, independent of whether any issue closed.
    """

    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        from tests.helpers import copy_git_template

        root = tmp_path / "main"
        root.mkdir()
        copy_git_template(root)
        (root / "seed.txt").write_text("seed\n")
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=root, capture_output=True)
        return root

    @staticmethod
    def _add_worktree(repo: Path, name: str) -> Path:
        wt = repo.parent / name
        subprocess.run(
            ["git", "worktree", "add", "-b", f"branch-{name}", str(wt)],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        return wt

    def test_clean_worktree_is_a_noop(self, repo: Path) -> None:
        from little_loops.git_operations import preserve_before_teardown

        wt = self._add_worktree(repo, "wt-clean")
        assert preserve_before_teardown(wt) is None

    def test_noise_only_dirt_is_a_noop(self, repo: Path) -> None:
        """AC #8: `.ll/`-only dirt is not worth a preservation ref."""
        from little_loops.git_operations import preserve_before_teardown

        wt = self._add_worktree(repo, "wt-noise")
        (wt / ".ll").mkdir(parents=True, exist_ok=True)
        (wt / ".ll" / "scratch.json").write_text("{}\n")
        assert preserve_before_teardown(wt) is None

    def test_orphaned_work_survives_forced_removal(self, repo: Path) -> None:
        """AC #6/#7: the backstop makes the P1 unreachable at teardown."""
        from little_loops.git_operations import preserve_before_teardown

        wt = self._add_worktree(repo, "wt-orphan")
        (wt / "orphan.py").write_text("def orphaned(): ...\n")

        sha = preserve_before_teardown(wt)
        assert sha, "non-noise dirt at teardown must be preserved"

        subprocess.run(
            ["git", "worktree", "remove", "--force", str(wt)],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        assert not wt.exists()

        recovered = subprocess.run(
            ["git", "show", f"{sha}:orphan.py"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert recovered.stdout == "def orphaned(): ...\n"

    def test_cleanup_worktree_preserves_before_removing(self, repo: Path) -> None:
        """The backstop is actually wired into `cleanup_worktree`, not just available."""
        from unittest.mock import MagicMock

        from little_loops.logger import Logger
        from little_loops.parallel.git_lock import GitLock
        from little_loops.worktree_utils import cleanup_worktree

        wt = self._add_worktree(repo, "wt-cleanup")
        (wt / "orphan.py").write_text("def orphaned(): ...\n")

        cleanup_worktree(wt, repo, MagicMock(spec=Logger), GitLock())

        assert not wt.exists()
        refs = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname)", "refs/ll/abandoned/"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        assert len(refs) == 1, f"cleanup_worktree must preserve dirt first, got refs={refs}"
        assert (
            subprocess.run(
                ["git", "show", f"{refs[0]}:orphan.py"], cwd=repo, capture_output=True, text=True
            ).stdout
            == "def orphaned(): ...\n"
        )

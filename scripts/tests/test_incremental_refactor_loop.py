"""Behavioural shell-execution tests for incremental-refactor.yaml (BUG-3276).

Extracts the raw shell scripts from check_preconditions/verify_tests/revert and
runs them via subprocess against controlled tmp_path git repos, mirroring the
pattern in test_general_task_loop.py's TestCheckBaselineTestsShellAction.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

LOOP_FILE = Path(__file__).parent.parent / "little_loops" / "loops" / "incremental-refactor.yaml"


def _load_state_script(state_name: str) -> str:
    with open(LOOP_FILE) as f:
        data = yaml.safe_load(f)
    return data["states"][state_name]["action"]


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


def _init_git_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("baseline\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=tmp_path, check=True)


class TestVerifyTestsExitCodeContract:
    """BUG-3276 Tests subsection: verify_tests must own the exit-code space so a
    resolution failure (3) never lands on the same edge (1) as a real test
    failure -- pytest's own exit codes (2/3/4/5) must be normalized to 1."""

    def _run(
        self, tmp_path: Path, *, context_test_cmd: str = "", config_test_cmd: str | None = "SKIP"
    ) -> subprocess.CompletedProcess[str]:
        if config_test_cmd != "SKIP":
            (tmp_path / ".ll").mkdir(exist_ok=True)
            (tmp_path / ".ll" / "ll-config.json").write_text(
                yaml.dump({"project": {"test_cmd": config_test_cmd}})
            )
        script = _load_state_script("verify_tests")
        script = script.replace("${context.test_cmd}", context_test_cmd)
        return _bash(script, cwd=tmp_path)

    def test_empty_unresolvable_exits_3(self, tmp_path: Path) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text('{"project": {"test_cmd": null}}')
        result = self._run(tmp_path, config_test_cmd="SKIP")
        assert result.returncode == 3, result.stderr

    def test_passing_command_exits_0(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, context_test_cmd="true")
        assert result.returncode == 0, result.stderr

    def test_failing_command_exits_1(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, context_test_cmd="false")
        assert result.returncode == 1, result.stderr

    def test_pytest_usage_error_exit_4_maps_to_1_not_3(self, tmp_path: Path) -> None:
        """This bug's own failure mode: a command that exits 4 must revert (1),
        not be mistaken for an unresolvable command (3)."""
        result = self._run(tmp_path, context_test_cmd="exit 4")
        assert result.returncode == 1, result.stderr

    def test_context_override_wins_over_config(self, tmp_path: Path) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text('{"project": {"test_cmd": "false"}}')
        result = self._run(tmp_path, context_test_cmd="true", config_test_cmd="SKIP")
        assert result.returncode == 0, result.stderr

    def test_falls_back_to_config_test_cmd(self, tmp_path: Path) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text('{"project": {"test_cmd": "true"}}')
        result = self._run(tmp_path, context_test_cmd="", config_test_cmd="SKIP")
        assert result.returncode == 0, result.stderr


class TestCheckPreconditionsShellAction:
    """BUG-3276 AC 4: refuses to start on unresolvable test_cmd or a dirty tree
    (untracked files included), .loops excluded so the gate is runnable in
    every consuming project even though ll-init doesn't gitignore it.

    Post-implementation review: the gate also runs the resolved command once,
    so a non-empty-but-wrong test_cmd or an already-red suite refuses to start
    rather than reverting every step.
    """

    def _run(
        self,
        tmp_path: Path,
        *,
        context_test_cmd: str = "true",
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        run_dir = tmp_path / "run_dir"
        run_dir.mkdir(parents=True, exist_ok=True)
        script = _load_state_script("check_preconditions")
        script = script.replace("${context.test_cmd}", context_test_cmd)
        script = script.replace("${context.run_dir}", str(run_dir))
        return _bash(script, cwd=cwd or tmp_path)

    def test_clean_tree_and_resolvable_cmd_passes(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        result = self._run(tmp_path)
        assert result.returncode == 0, result.stderr

    def test_untracked_loops_dir_alone_does_not_refuse(self, tmp_path: Path) -> None:
        """The blocker fix: an untracked .loops/runs/x/ must not trip the gate,
        or the loop can never start in any consuming project."""
        _init_git_repo(tmp_path)
        loops_run = tmp_path / ".loops" / "runs" / "x"
        loops_run.mkdir(parents=True)
        (loops_run / "state.json").write_text("{}")
        result = self._run(tmp_path)
        assert result.returncode == 0, result.stderr

    def test_untracked_file_outside_loops_refuses(self, tmp_path: Path) -> None:
        """Mirror case: an untracked file alongside .loops/ must still refuse."""
        _init_git_repo(tmp_path)
        loops_run = tmp_path / ".loops" / "runs" / "x"
        loops_run.mkdir(parents=True)
        (loops_run / "state.json").write_text("{}")
        (tmp_path / "src.py").write_text("x = 1\n")
        result = self._run(tmp_path)
        assert result.returncode == 1, result.stderr

    def test_untracked_only_status_refuses(self, tmp_path: Path) -> None:
        """A ??-only status (no modified tracked files) must still refuse --
        untracked files are exactly the too-narrow half of the original bug."""
        _init_git_repo(tmp_path)
        (tmp_path / "new_module.py").write_text("y = 2\n")
        result = self._run(tmp_path)
        assert result.returncode == 1, result.stderr

    def test_dirty_tracked_file_refuses(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        (tmp_path / "README.md").write_text("modified\n")
        result = self._run(tmp_path)
        assert result.returncode == 1, result.stderr

    def test_unresolvable_test_cmd_refuses_even_on_clean_tree(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text('{"project": {"test_cmd": null}}')
        result = self._run(tmp_path, context_test_cmd="")
        assert result.returncode == 1, result.stderr

    def test_dirty_tree_message_names_the_tree_and_the_remedy(self, tmp_path: Path) -> None:
        """Per-cause messages: a dirty tree must not lecture about test_cmd."""
        _init_git_repo(tmp_path)
        (tmp_path / "src.py").write_text("x = 1\n")
        run_dir = tmp_path / "run_dir"
        run_dir.mkdir(parents=True, exist_ok=True)
        result = self._run(tmp_path)
        assert result.returncode == 1, result.stderr
        message = (run_dir / "precondition-failure.txt").read_text()
        assert "working tree is not clean" in message
        assert "stash" in message
        assert "project.test_cmd" not in message

    def test_unresolvable_message_names_test_cmd_and_config_path(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-config.json").write_text('{"project": {"test_cmd": null}}')
        run_dir = tmp_path / "run_dir"
        run_dir.mkdir(parents=True, exist_ok=True)
        result = self._run(tmp_path, context_test_cmd="")
        assert result.returncode == 1, result.stderr
        message = (run_dir / "precondition-failure.txt").read_text()
        assert "project.test_cmd" in message
        assert ".ll/ll-config.json" in message

    def test_failure_message_also_goes_to_stderr(self, tmp_path: Path) -> None:
        """A file-only message leaves a user watching the run with a bare
        `failed` terminal and no reason."""
        _init_git_repo(tmp_path)
        (tmp_path / "src.py").write_text("x = 1\n")
        result = self._run(tmp_path)
        assert result.returncode == 1
        assert "refused to start" in result.stderr

    def test_red_baseline_refuses_to_start(self, tmp_path: Path) -> None:
        """A resolvable command whose suite is already failing must refuse --
        otherwise every step reverts through no fault of the step."""
        _init_git_repo(tmp_path)
        result = self._run(tmp_path, context_test_cmd="false")
        assert result.returncode == 1, result.stderr
        message = (tmp_path / "run_dir" / "precondition-failure.txt").read_text()
        assert "baseline test run already fails" in message

    def test_pytest_usage_error_baseline_refuses_to_start(self, tmp_path: Path) -> None:
        """This bug's original failure code (pytest exit 4, missing test dir)
        reached through a wrong config value instead of a hardcoded literal."""
        _init_git_repo(tmp_path)
        result = self._run(tmp_path, context_test_cmd="exit 4")
        assert result.returncode == 1, result.stderr

    def test_unrunnable_command_reported_distinctly_from_red_suite(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        result = self._run(tmp_path, context_test_cmd="ll-no-such-binary-xyz")
        assert result.returncode == 1, result.stderr
        message = (tmp_path / "run_dir" / "precondition-failure.txt").read_text()
        assert "not runnable here" in message

    def test_baseline_output_captured_to_run_dir(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        self._run(tmp_path, context_test_cmd="echo BASELINE_MARKER; exit 1")
        output = (tmp_path / "run_dir" / "baseline-test-output.txt").read_text()
        assert "BASELINE_MARKER" in output

    def test_gate_is_cwd_independent(self, tmp_path: Path) -> None:
        """Run from a subdirectory: the .loops exclusion is top-anchored, so an
        untracked .loops/ at the repo root must still not trip the gate."""
        _init_git_repo(tmp_path)
        loops_run = tmp_path / ".loops" / "runs" / "x"
        loops_run.mkdir(parents=True)
        (loops_run / "state.json").write_text("{}")
        subdir = tmp_path / "pkg"
        subdir.mkdir()
        result = self._run(tmp_path, cwd=subdir)
        assert result.returncode == 0, result.stderr


class TestRevertShellAction:
    """BUG-3276 AC 5: revert closes both halves of the original defect -- the
    too-broad half (git checkout -- .) and the too-narrow half (git clean -fd),
    while excluding .loops so the active run directory survives."""

    def test_reverts_tracked_changes_removes_untracked_preserves_loops(
        self, tmp_path: Path
    ) -> None:
        _init_git_repo(tmp_path)
        loops_run = tmp_path / ".loops" / "runs" / "x"
        loops_run.mkdir(parents=True)
        (loops_run / "state.json").write_text('{"current_state": "execute_step"}')

        # Simulate a failed step: modifies a tracked file and creates a new one.
        (tmp_path / "README.md").write_text("modified by step\n")
        (tmp_path / "new_module.py").write_text("z = 3\n")

        script = _load_state_script("revert")
        result = _bash(script, cwd=tmp_path)
        assert result.returncode == 0, result.stderr

        assert (tmp_path / "README.md").read_text() == "baseline\n"
        assert not (tmp_path / "new_module.py").exists()
        assert (loops_run / "state.json").exists(), (
            "revert must not delete the active run directory (-e .loops)"
        )

    def test_revert_is_cwd_independent(self, tmp_path: Path) -> None:
        """Run from a subdirectory: `git checkout -- .` must still cover the
        whole repo, and `.loops` must still resolve at the repo root."""
        _init_git_repo(tmp_path)
        subdir = tmp_path / "pkg"
        subdir.mkdir()
        (subdir / "__init__.py").write_text("")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "pkg"], cwd=tmp_path, check=True)

        loops_run = tmp_path / ".loops" / "runs" / "x"
        loops_run.mkdir(parents=True)
        (loops_run / "state.json").write_text("{}")
        (tmp_path / "README.md").write_text("modified by step\n")
        (tmp_path / "new_module.py").write_text("z = 3\n")

        result = _bash(_load_state_script("revert"), cwd=subdir)
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "README.md").read_text() == "baseline\n"
        assert not (tmp_path / "new_module.py").exists()
        assert (loops_run / "state.json").exists()

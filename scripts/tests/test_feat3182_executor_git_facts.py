"""FSMExecutor run-time git-fact capture (FEAT-3182 Implementation Steps 3, 3h).

`ll-loop evidence` needs `head_sha`/`branch`/`worktree_digest` recorded at the
moment the loop actually ran, not derived independently at export time (which
would attest to whatever HEAD is when the exporter runs). These tests cover
the opt-in `capture_git_facts` constructor kwarg and `loop_yaml_path` hashing
on `FSMExecutor`, both wired at `loop_start`/`loop_complete`/`_finish()`.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from little_loops.fsm.executor import FSMExecutor
from little_loops.fsm.schema import FSMLoop, StateConfig

from .helpers import copy_git_template


@dataclass
class _MockActionRunner:
    def run(self, action: str, timeout: int, is_slash_command: bool, **kwargs: Any) -> Any:
        from little_loops.fsm.executor import ActionResult

        return ActionResult(output="", stderr="", exit_code=0, duration_ms=1)


def _single_state_fsm(name: str = "git-facts-test") -> FSMLoop:
    return FSMLoop(
        name=name,
        initial="done",
        states={"done": StateConfig(terminal=True)},
    )


def _git_commit(repo: Path, message: str = "init") -> None:
    (repo / "tracked.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", message], cwd=repo, capture_output=True, check=True
    )


class TestCaptureDisabledByDefault:
    def test_default_construction_makes_zero_git_subprocess_calls(self, tmp_path: Path) -> None:
        fsm = _single_state_fsm()
        events: list[dict] = []
        executor = FSMExecutor(
            fsm,
            action_runner=_MockActionRunner(),
            event_callback=events.append,
            working_dir=tmp_path,
        )
        with patch("subprocess.run") as mock_run:
            executor.run()
        mock_run.assert_not_called()

    def test_loop_start_has_no_git_fact_keys_when_disabled(self, tmp_path: Path) -> None:
        fsm = _single_state_fsm()
        events: list[dict] = []
        executor = FSMExecutor(
            fsm,
            action_runner=_MockActionRunner(),
            event_callback=events.append,
            working_dir=tmp_path,
        )
        executor.run()
        loop_start = next(e for e in events if e["event"] == "loop_start")
        assert "head_sha" not in loop_start
        assert "branch" not in loop_start
        assert "worktree_digest" not in loop_start


class TestCaptureEnabled:
    def test_loop_start_includes_head_sha_branch_worktree_digest(self, tmp_path: Path) -> None:
        repo = copy_git_template(tmp_path)
        _git_commit(repo)
        fsm = _single_state_fsm()
        events: list[dict] = []
        executor = FSMExecutor(
            fsm,
            action_runner=_MockActionRunner(),
            event_callback=events.append,
            working_dir=repo,
            capture_git_facts=True,
        )
        executor.run()
        loop_start = next(e for e in events if e["event"] == "loop_start")
        assert loop_start["branch"] == "main"
        assert isinstance(loop_start["head_sha"], str) and len(loop_start["head_sha"]) == 40
        assert isinstance(loop_start["worktree_digest"], str)

    def test_loop_complete_carries_a_worktree_digest_too(self, tmp_path: Path) -> None:
        repo = copy_git_template(tmp_path)
        _git_commit(repo)
        fsm = _single_state_fsm()
        events: list[dict] = []
        executor = FSMExecutor(
            fsm,
            action_runner=_MockActionRunner(),
            event_callback=events.append,
            working_dir=repo,
            capture_git_facts=True,
        )
        executor.run()
        loop_complete = next(e for e in events if e["event"] == "loop_complete")
        assert isinstance(loop_complete["worktree_digest"], str)

    def test_worktree_digest_changes_when_tracked_file_edited(self, tmp_path: Path) -> None:
        repo = copy_git_template(tmp_path)
        _git_commit(repo)
        fsm = _single_state_fsm()
        executor = FSMExecutor(
            fsm, action_runner=_MockActionRunner(), working_dir=repo, capture_git_facts=True
        )
        before = executor._compute_worktree_digest(repo)
        (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
        after = executor._compute_worktree_digest(repo)
        assert before != after

    def test_outside_git_repo_facts_are_none_no_exception(self, tmp_path: Path) -> None:
        fsm = _single_state_fsm()
        events: list[dict] = []
        executor = FSMExecutor(
            fsm,
            action_runner=_MockActionRunner(),
            event_callback=events.append,
            working_dir=tmp_path,
            capture_git_facts=True,
        )
        executor.run()  # must not raise, even though tmp_path is not a git repo
        loop_start = next(e for e in events if e["event"] == "loop_start")
        assert loop_start["head_sha"] is None
        assert loop_start["branch"] is None
        assert loop_start["worktree_digest"] is None

    def test_head_sha_and_branch_passed_to_record_loop_run_summary(self, tmp_path: Path) -> None:
        repo = copy_git_template(tmp_path)
        _git_commit(repo)
        fsm = _single_state_fsm()
        executor = FSMExecutor(
            fsm, action_runner=_MockActionRunner(), working_dir=repo, capture_git_facts=True
        )
        with patch("little_loops.session_store.record_loop_run_summary") as mock_record:
            executor.run()
        assert mock_record.call_args.kwargs["branch"] == "main"
        assert len(mock_record.call_args.kwargs["head_sha"]) == 40


class TestLoopYamlPathHashing:
    def test_recorded_independent_of_capture_git_facts(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "loop.yaml"
        yaml_path.write_text("name: x\n", encoding="utf-8")
        fsm = _single_state_fsm()
        events: list[dict] = []
        executor = FSMExecutor(
            fsm,
            action_runner=_MockActionRunner(),
            event_callback=events.append,
            loop_yaml_path=yaml_path,
        )
        executor.run()
        loop_start = next(e for e in events if e["event"] == "loop_start")
        assert loop_start["loop_yaml_path"] == str(yaml_path)
        assert loop_start["loop_yaml_sha256"] == hashlib.sha256(yaml_path.read_bytes()).hexdigest()
        assert "head_sha" not in loop_start  # capture_git_facts still False

    def test_missing_yaml_file_is_silently_skipped(self, tmp_path: Path) -> None:
        fsm = _single_state_fsm()
        events: list[dict] = []
        executor = FSMExecutor(
            fsm,
            action_runner=_MockActionRunner(),
            event_callback=events.append,
            loop_yaml_path=tmp_path / "does-not-exist.yaml",
        )
        executor.run()
        loop_start = next(e for e in events if e["event"] == "loop_start")
        assert "loop_yaml_path" not in loop_start
        assert "loop_yaml_sha256" not in loop_start

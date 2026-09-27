"""FEAT-3594: continue-task loop — load_prompt, run_tests, stall_check, read_verdict, re-entry."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

LOOP = Path(__file__).parent.parent / "little_loops" / "loops" / "continue-task.yaml"


def _data() -> dict[str, Any]:
    return yaml.safe_load(LOOP.read_text())


def _action(state: str) -> str:
    return _data()["states"][state]["action"]


def _bash(
    state: str,
    proj: Path,
    run_dir: Path,
    *,
    input_text: str = "",
    test_cmd: str = "",
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    script = _action(state)
    script = script.replace("${context.run_dir}", str(run_dir))
    script = script.replace("${context.input}", input_text)
    script = script.replace(
        "${context.test_cmd:shell}", shlex.quote(test_cmd) if test_cmd else "''"
    )
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        ["bash", "-c", script], cwd=proj, env=env, capture_output=True, text=True, timeout=60
    )


@pytest.fixture
def stubbed(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """(project, run_dir, env) with a stub ll-config first on PATH (no real suite runs)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".ll").mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "ll-config"
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(0o755)
    return proj, run_dir, {"PATH": f"{bin_dir}:{os.environ['PATH']}"}


def _git(proj: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=proj,
        check=True,
        capture_output=True,
    )


class TestLoadPrompt:
    def test_explicit_input(self, stubbed: Any) -> None:
        proj, run, env = stubbed
        r = _bash(
            "load_prompt", proj, run, input_text="do the thing", test_cmd="true", env_extra=env
        )
        assert r.returncode == 0, r.stderr
        assert "PROMPT_SOURCE: input" in r.stdout
        assert "do the thing" in (run / "goal.md").read_text()

    def test_fresh_handoff_with_empty_input(self, stubbed: Any) -> None:
        proj, run, env = stubbed
        (proj / ".ll" / "ll-continue-prompt.md").write_text("# Handoff\nresume me\n")
        r = _bash("load_prompt", proj, run, test_cmd="true", env_extra=env)
        assert r.returncode == 0, r.stderr
        assert "PROMPT_SOURCE: .ll/ll-continue-prompt.md" in r.stdout
        assert "PROMPT_MTIME:" in r.stdout
        assert "PROMPT_FIRST_LINE: # Handoff" in r.stdout
        assert "resume me" in (run / "goal.md").read_text()

    def test_whitespace_input_falls_through(self, stubbed: Any) -> None:
        proj, run, env = stubbed
        (proj / ".ll" / "ll-continue-prompt.md").write_text("from handoff\n")
        r = _bash("load_prompt", proj, run, input_text="   ", test_cmd="true", env_extra=env)
        assert r.returncode == 0
        assert "PROMPT_SOURCE: .ll/ll-continue-prompt.md" in r.stdout

    def test_stale_handoff_rejected(self, stubbed: Any) -> None:
        proj, run, env = stubbed
        f = proj / ".ll" / "ll-continue-prompt.md"
        f.write_text("old\n")
        old = time.time() - 72 * 3600
        os.utime(f, (old, old))
        r = _bash("load_prompt", proj, run, test_cmd="true", env_extra=env)
        assert r.returncode == 1
        assert "continuation.prompt_expiry_hours" in r.stdout

    def test_no_source(self, stubbed: Any) -> None:
        proj, run, env = stubbed
        r = _bash("load_prompt", proj, run, env_extra=env)
        assert r.returncode == 1
        assert "Usage:" in r.stdout

    def test_baseline_127_is_skip(self, stubbed: Any) -> None:
        proj, run, env = stubbed
        r = _bash("load_prompt", proj, run, input_text="x", test_cmd="exit 127", env_extra=env)
        assert r.returncode == 0
        assert (run / "baseline-exit.txt").read_text().strip() == "SKIP"

    def test_baseline_exit_recorded(self, stubbed: Any) -> None:
        proj, run, env = stubbed
        _bash("load_prompt", proj, run, input_text="x", test_cmd="exit 3", env_extra=env)
        assert (run / "baseline-exit.txt").read_text().strip() == "3"

    def test_baseline_ref_recorded_in_git(self, stubbed: Any) -> None:
        proj, run, env = stubbed
        _git(proj, "init", "-q")
        _git(proj, "commit", "-q", "--allow-empty", "-m", "c")
        _bash("load_prompt", proj, run, input_text="x", test_cmd="true", env_extra=env)
        assert len((run / "baseline-ref.txt").read_text().strip()) >= 40

    def test_no_baseline_ref_outside_git(self, stubbed: Any) -> None:
        proj, run, env = stubbed
        _bash(
            "load_prompt",
            proj,
            run,
            input_text="x",
            test_cmd="true",
            env_extra={**env, "GIT_CEILING_DIRECTORIES": str(proj.parent)},
        )
        assert not (run / "baseline-ref.txt").exists()


class TestRunTests:
    def _setup(self, run: Path, cmd: str, base: str) -> None:
        (run / "resolved-test-cmd.txt").write_text(cmd + "\n")
        (run / "baseline-exit.txt").write_text(base + "\n")

    def test_regression(self, stubbed: Any) -> None:
        proj, run, _ = stubbed
        self._setup(run, "echo boom; exit 1", "0")
        r = _bash("run_tests", proj, run)
        assert r.returncode == 1
        assert "TEST_STATUS: REGRESSED" in r.stdout
        assert "boom" in (run / "done-check.md").read_text()

    def test_pre_existing_failure_is_advisory(self, stubbed: Any) -> None:
        proj, run, _ = stubbed
        self._setup(run, "exit 1", "1")
        r = _bash("run_tests", proj, run)
        assert r.returncode == 0
        assert "FAILING" in r.stdout and "pre-existing" in r.stdout

    def test_no_command_skips(self, stubbed: Any) -> None:
        proj, run, _ = stubbed
        self._setup(run, "", "SKIP")
        r = _bash("run_tests", proj, run)
        assert r.returncode == 0
        assert "SKIP" in r.stdout

    def test_pass(self, stubbed: Any) -> None:
        proj, run, _ = stubbed
        self._setup(run, "true", "0")
        r = _bash("run_tests", proj, run)
        assert r.returncode == 0
        assert "TEST_STATUS: PASS" in r.stdout

    def test_removes_stale_verdict_and_tests(self, stubbed: Any) -> None:
        proj, run, _ = stubbed
        self._setup(run, "", "SKIP")
        (run / "verdict.txt").write_text("DONE\n")
        (run / "tests.txt").write_text("TEST_STATUS: PASS\n")
        _bash("run_tests", proj, run)
        assert not (run / "verdict.txt").exists()
        assert "SKIP" in (run / "tests.txt").read_text()

    def test_stale_tests_removed_before_command_runs(self, stubbed: Any) -> None:
        proj, run, _ = stubbed
        self._setup(run, "test ! -e " + str(run / "tests.txt"), "0")
        (run / "tests.txt").write_text("TEST_STATUS: PASS\n")
        assert _bash("run_tests", proj, run).returncode == 0


class TestStallCheck:
    @pytest.fixture
    def repo(self, stubbed: Any) -> tuple[Path, Path]:
        proj, run, _ = stubbed
        _git(proj, "init", "-q")
        (proj / "a.txt").write_text("one\n")
        _git(proj, "add", ".")
        _git(proj, "commit", "-q", "-m", "init")
        ref = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=proj, capture_output=True, text=True, check=True
        ).stdout
        (run / "baseline-ref.txt").write_text(ref)
        return proj, run

    def _count(self, proj: Path, run: Path) -> str:
        r = _bash("stall_check", proj, run)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    def test_identical_passes_count_up(self, repo: Any) -> None:
        proj, run = repo
        assert [self._count(proj, run) for _ in range(4)] == ["0", "1", "2", "3"]

    def test_commit_only_is_progress(self, repo: Any) -> None:
        proj, run = repo
        self._count(proj, run)
        assert self._count(proj, run) == "1"
        (proj / "a.txt").write_text("two\n")
        _git(proj, "commit", "-q", "-am", "edit")
        assert self._count(proj, run) == "0"

    def test_untracked_file_is_progress(self, repo: Any) -> None:
        proj, run = repo
        self._count(proj, run)
        (proj / "new.txt").write_text("x\n")
        assert self._count(proj, run) == "0"
        assert self._count(proj, run) == "1"

    def test_same_line_count_edit_is_progress(self, repo: Any) -> None:
        proj, run = repo
        (proj / "a.txt").write_text("aaa\n")
        self._count(proj, run)
        (proj / "a.txt").write_text("bbb\n")
        assert self._count(proj, run) == "0"

    def test_loops_dir_changes_ignored(self, repo: Any) -> None:
        proj, run = repo
        self._count(proj, run)
        (proj / ".loops").mkdir()
        (proj / ".loops" / "x").write_text("churn\n")
        assert self._count(proj, run) == "1"

    def test_non_git_is_progress(self, stubbed: Any) -> None:
        proj, run, _ = stubbed
        r = _bash("stall_check", proj, run, env_extra={"GIT_CEILING_DIRECTORIES": str(proj.parent)})
        assert r.stdout.strip() == "0"

    def test_gate_config(self) -> None:
        st = _data()["states"]["stall_check"]
        assert st["evaluate"] == {"type": "output_numeric", "operator": "lt", "target": 3}
        assert (st["on_yes"], st["on_no"], st["on_error"]) == (
            "run_tests",
            "summarize_partial",
            "run_tests",
        )
        assert "fragment" not in st


class TestReadVerdict:
    @pytest.mark.parametrize(
        "content,expected",
        [("DONE\n", 0), ("NOT_DONE\n", 1), ("  DONE\n", 1), ("done\n", 1), (None, 2)],
    )
    def test_gate(self, stubbed: Any, content: str | None, expected: int) -> None:
        proj, run, _ = stubbed
        if content is not None:
            (run / "verdict.txt").write_text(content)
        assert _bash("read_verdict", proj, run).returncode == expected


class TestStructure:
    def test_no_required_inputs(self) -> None:
        assert not _data().get("required_inputs")

    def test_work_reentry_guard_and_handoff_instruction(self) -> None:
        action = _action("work")
        assert "grep -qF '${context.run_dir}' .ll/ll-continue-prompt.md" in action
        assert "literal path ${context.run_dir}" in action

    def test_check_done_missing_tests_line(self) -> None:
        assert "If tests.txt is missing" in _action("check_done")

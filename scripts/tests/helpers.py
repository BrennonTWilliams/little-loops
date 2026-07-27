"""Shared test helpers.

Includes helpers for FSM loop tests, previously duplicated across 6 test
files, plus general-purpose test utilities such as ``sgr_codes()``.
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    RouteConfig,
    StateConfig,
)

# Hypothesis fuzz depth. Fast by default: an interactive full-suite run
# otherwise generates ~3,600 examples across the fuzz/property files, a real
# chunk of wall-clock and (for file-writing fuzz tests) filesystem churn.
# LL_FUZZ=full restores each test's full depth; the automated verify gate
# (worktree_utils.verify_epic_branch_before_merge) sets it, so the enforced
# gate always runs at full depth. See also the profile registration in
# conftest.py, which throttles tests WITHOUT an explicit @settings decorator.
FUZZ_FULL = os.environ.get("LL_FUZZ") == "full"


def fuzz_max_examples(full_depth: int, fast: int = 25) -> int:
    """Per-test hypothesis ``max_examples``: *full_depth* under ``LL_FUZZ=full``,
    else ``min(full_depth, fast)``."""
    return full_depth if FUZZ_FULL else min(full_depth, fast)


# Cached commitless git-repo template, built once per (xdist worker) process.
_git_template_cache: Path | None = None


def copy_git_template(dst: Path, initial_branch: str = "main") -> Path:
    """Copy a pre-initialized, commitless git repo into *dst* and return it.

    Replaces the ``git init`` + 2x ``git config`` subprocess spawns that a dozen
    repo fixtures each ran per test with a single in-process ``copytree`` of a
    per-process cached template (branch ``main``, test user configured, no
    commits). Callers seed files and commit on top exactly as before, so test
    semantics are unchanged — only the per-test fork/exec churn goes away.

    ``dst`` may already exist (``tmp_path`` itself is a valid target).
    """
    global _git_template_cache
    if _git_template_cache is None or not _git_template_cache.exists():
        base = Path(tempfile.mkdtemp(prefix="ll-git-template-"))
        atexit.register(shutil.rmtree, base, True)
        repo = base / "repo"
        repo.mkdir()
        for args in (
            ("init", "-q", "--initial-branch", "main"),
            ("config", "user.email", "test@example.com"),
            ("config", "user.name", "Test User"),
        ):
            subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)
        _git_template_cache = repo
    shutil.copytree(_git_template_cache, dst, dirs_exist_ok=True)
    if initial_branch != "main":
        subprocess.run(
            ["git", "symbolic-ref", "HEAD", f"refs/heads/{initial_branch}"],
            cwd=dst,
            capture_output=True,
            check=True,
        )
    return dst


# ``[0-9;]*`` matches the production ``_ANSI_RE`` in
# ``little_loops.cli.output.strip_ansi`` — the same grammar, but capturing
# the parameter group instead of discarding it.
_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")


def sgr_codes(text: str) -> set[str]:
    """Return the distinct SGR parameter strings (e.g. ``"38;5;240;1"``) in *text*.

    Use in assertions instead of hand-rolled regexes, which are prone to
    silently under-matching multi-segment indexed-256 codes (e.g. matching
    ``\\d+`` against a code like ``38;5;240;1``): ``assert "38;5;240;1" in
    sgr_codes(result)``.
    """
    return set(_SGR_RE.findall(text))


def make_test_state(
    action: str | None = None,
    on_yes: str | None = None,
    on_no: str | None = None,
    on_error: str | None = None,
    next: str | None = None,
    terminal: bool = False,
    evaluate: EvaluateConfig | None = None,
    route: RouteConfig | None = None,
    capture: str | None = None,
    timeout: int | None = None,
    on_maintain: str | None = None,
    model: str | None = None,
    effort: str | None = None,
) -> StateConfig:
    """Create a StateConfig for testing.

    Provides sensible defaults so individual tests only specify the
    fields they care about.
    """
    return StateConfig(
        action=action,
        on_yes=on_yes,
        on_no=on_no,
        on_error=on_error,
        next=next,
        terminal=terminal,
        evaluate=evaluate,
        route=route,
        capture=capture,
        timeout=timeout,
        on_maintain=on_maintain,
        model=model,
        effort=effort,
    )


def make_test_fsm(
    name: str = "test-loop",
    initial: str = "start",
    states: dict[str, StateConfig] | None = None,
    max_steps: int = 50,
    timeout: int | None = None,
) -> FSMLoop:
    """Create an FSMLoop for testing.

    If no states are provided, creates a minimal two-state loop
    (start → done).
    """
    if states is None:
        states = {
            "start": make_test_state(action="echo start", on_yes="done", on_no="done"),
            "done": make_test_state(terminal=True),
        }
    return FSMLoop(
        name=name,
        initial=initial,
        states=states,
        max_steps=max_steps,
        timeout=timeout,
    )

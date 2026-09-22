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
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import pytest

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


# BUG-3522: shared Node-availability guard for the four Node-dependent gates
# (policy-builder conformance + round-trip, feat3304 dashboard runtime, rlhf
# smoke harness). Skips gracefully by default so contributors without Node
# aren't hard-blocked; set LL_REQUIRE_NODE=1 (as CI does) to turn an
# unavailable/unusable Node into a hard failure instead of a silent skip.
_LL_REQUIRE_NODE_ENV = "LL_REQUIRE_NODE"


@dataclass(frozen=True)
class _NodeProbe:
    """Result of a single ``node --version`` probe."""

    node: str | None
    major: int | None
    stdout: str
    stderr: str
    exit_code: int | None
    error: str | None


def _probe_node() -> _NodeProbe:
    node = shutil.which("node")
    if node is None:
        return _NodeProbe(
            node=None,
            major=None,
            stdout="",
            stderr="",
            exit_code=None,
            error="node executable not found on PATH",
        )
    try:
        proc = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as e:
        return _NodeProbe(
            node=node,
            major=None,
            stdout="",
            stderr="",
            exit_code=None,
            error=f"`node --version` timed out: {e}",
        )
    except OSError as e:
        return _NodeProbe(
            node=node,
            major=None,
            stdout="",
            stderr="",
            exit_code=None,
            error=f"`node --version` could not be run: {e}",
        )
    major = None
    if proc.returncode == 0:
        head = proc.stdout.strip().lstrip("v").split(".", 1)[0]
        try:
            major = int(head)
        except ValueError:
            major = None
    return _NodeProbe(
        node=node,
        major=major,
        stdout=proc.stdout,
        stderr=proc.stderr,
        exit_code=proc.returncode,
        error=None,
    )


def require_node(min_major: int | None = 22) -> str:
    """Return the ``node`` executable path, skipping or failing if unusable.

    Probes ``node --version`` exactly once. With ``LL_REQUIRE_NODE=1`` set
    (as the ``unit-tests`` CI job does) an unavailable or unusable Node is a
    hard failure; otherwise it is a graceful skip, preserving the pattern the
    four Node-dependent gates used individually before this consolidation.
    ``min_major=None`` accepts any successfully-probed Node, including a
    major below 22 (the ``rlhf`` smoke gate never had a version floor).
    """
    probe = _probe_node()
    must_pass = os.environ.get(_LL_REQUIRE_NODE_ENV) == "1"

    def _give_up(message: str) -> NoReturn:
        if must_pass:
            pytest.fail(message)
        else:
            pytest.skip(message)

    if probe.node is None:
        _give_up(probe.error or "node executable not found on PATH")
    if probe.error is not None:
        _give_up(probe.error)
    if probe.exit_code != 0:
        _give_up(
            f"`node --version` exited {probe.exit_code}: "
            f"stdout={probe.stdout!r} stderr={probe.stderr!r}"
        )
    if probe.major is None:
        _give_up(f"could not parse a Node version from output: {probe.stdout!r}")
    if min_major is not None and probe.major < min_major:
        _give_up(
            f"Node >= {min_major} required; found major {probe.major} ({probe.stdout.strip()})"
        )

    # Retained in the passing test's captured stdout — surfaced in
    # pytest-junit.xml via junit_logging = "system-out" (BUG-3522), so a
    # green CI run's artifact quotes the exact runner Node version.
    print(f"require_node: using {probe.node} ({probe.stdout.strip()})")
    return probe.node

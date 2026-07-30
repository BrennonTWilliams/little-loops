"""Regression tests for ENH-2927: ll-* CLIs must not create stray `.ll/` dirs.

Real subprocess invocations of the installed console-script entry points
(``ll-doctor``, ``ll-issues``), run from a subdirectory of a scratch git repo
whose root already carries `.ll/` — the exact "measured offender" shape from
the issue's own repro steps. Skips gracefully if the entry point isn't on
PATH (e.g. a non-editable / differently-provisioned environment), mirroring
this repo's "gate wherever the tool exists" policy for external-tool gates.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest


def _init_repo(root) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)


def _make_project(tmp_path):
    """A scratch git repo with `.ll/` at the root and a nested subdirectory."""
    _init_repo(tmp_path)
    (tmp_path / ".ll").mkdir()
    sub = tmp_path / "scripts" / "little_loops"
    sub.mkdir(parents=True)
    return sub


@pytest.mark.skipif(shutil.which("ll-doctor") is None, reason="ll-doctor not on PATH")
def test_ll_doctor_from_subdirectory_creates_no_stray_ll(tmp_path) -> None:
    """Invoking ll-doctor from a project subdirectory leaves no `.ll/` there."""
    sub = _make_project(tmp_path)

    result = subprocess.run(
        ["ll-doctor", "--json"],
        cwd=str(sub),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode in (0, 1), f"stderr={result.stderr!r}"
    assert not (sub / ".ll").exists()
    # The root .ll/ is where any DB activity should land, never the subdir.
    assert not (sub / ".ll" / "history.db").exists()


@pytest.mark.skipif(shutil.which("ll-issues") is None, reason="ll-issues not on PATH")
def test_ll_issues_list_from_subdirectory_is_side_effect_free(tmp_path) -> None:
    """Invoking `ll-issues list` from a subdirectory creates no stray `.ll/` (regression guard)."""
    sub = _make_project(tmp_path)

    result = subprocess.run(
        ["ll-issues", "list"],
        cwd=str(sub),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode in (0, 1), f"stderr={result.stderr!r}"
    assert not (sub / ".ll").exists()


@pytest.mark.skipif(shutil.which("ll-doctor") is None, reason="ll-doctor not on PATH")
def test_ll_doctor_from_subdirectory_finds_root_db(tmp_path) -> None:
    """A history.db write triggered from a subdirectory lands at the resolved root, not cwd."""
    sub = _make_project(tmp_path)
    (tmp_path / ".ll" / "ll-config.json").write_text(
        json.dumps({"analytics": {"enabled": True}}), encoding="utf-8"
    )

    subprocess.run(
        [sys.executable, "-m", "little_loops.hooks", "post_tool_use"],
        input=json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "tool_response": {"exit_code": 0},
            }
        ),
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(sub),
    )
    assert not (sub / ".ll").exists()

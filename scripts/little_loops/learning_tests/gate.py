"""Shared gate utilities for learning-test staleness checks (ENH-2208).

Exposes ``is_record_stale()`` and ``format_nudge_message()`` as standalone
importable helpers consumed by the discoverability gate hook, the install
learning gate hook (ENH-2212), and downstream sprint/release gates
(ENH-2209, ENH-2210, ENH-2214, ENH-2217).

Also exposes ``run_learning_gate_for_issue()`` — the shared subprocess wrapper
for the ``proof-first-task`` loop used by ll-auto (ENH-2319).
"""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from little_loops.learning_tests import LearnTestRecord


def format_nudge_message(pkg: str, stale: bool = False) -> str:
    """Return a nudge message for a package with no proven or stale learning test.

    Args:
        pkg: The package name (already normalized).
        stale: If True, the record exists but is stale; otherwise it is absent.
    """
    if stale:
        body = f'Learning test for "{pkg}" is stale.'
    else:
        body = f'No learning test for "{pkg}".'
    return f'[ll: new dependency] {body} Consider: /ll:explore-api "{pkg}"'


def is_record_stale(record: LearnTestRecord, stale_after_days: int) -> bool:
    """Return True if the record's proof date exceeds the staleness threshold.

    Args:
        record: A LearnTestRecord with a ``date`` field (ISO 8601: YYYY-MM-DD).
        stale_after_days: Age threshold in days. Clamped to minimum 1 to
            prevent ``stale_after_days=0`` from being a footgun that passes
            all records whose date is exactly today.

    Returns:
        True if age in days exceeds the threshold; False if fresh or unparseable.
    """
    threshold = max(1, stale_after_days)
    try:
        record_date = datetime.date.fromisoformat(record.date)
    except (ValueError, TypeError, AttributeError):
        return False
    age_days = (datetime.date.today() - record_date).days
    return age_days > threshold


def _read_loop_final_state(cwd: Path, loop_name: str) -> str | None:
    """Read the terminal state from a completed loop's running state file.

    After ``ll-loop run`` exits, the state file remains at
    ``<cwd>/.loops/.running/<loop_name>.state.json``. The ``current_state``
    field holds the terminal state name (e.g. ``"done"``, ``"blocked"``).
    """
    state_file = cwd / ".loops" / ".running" / f"{loop_name}.state.json"
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text())
        return data.get("current_state")
    except (json.JSONDecodeError, OSError):
        return None


def run_learning_gate_for_issue(
    issue_path: Path,
    *,
    skip: bool = False,
    cwd: Path | None = None,
) -> Literal["passed", "blocked", "skipped"]:
    """Invoke proof-first-task loop for an issue and return the gate verdict.

    ``skip=True`` short-circuits to "skipped" (honours --skip-learning-gate).
    All terminal states (done, blocked, impl_failed) exit 0 — blocked is
    distinguished from done by reading the loop state file left after execution.

    Args:
        issue_path: Absolute path to the issue file.
        skip: If True, return "skipped" immediately without running the loop.
        cwd: Working directory for the subprocess (and state-file lookup).
            Defaults to ``Path.cwd()`` when None.
    """
    if skip:
        return "skipped"

    working_dir = cwd or Path.cwd()
    subprocess.run(
        [
            "ll-loop",
            "run",
            "proof-first-task",
            "--context",
            f"issue_file={issue_path}",
        ],
        capture_output=True,
        text=True,
        cwd=working_dir,
    )

    final_state = _read_loop_final_state(working_dir, "proof-first-task")
    if final_state == "blocked":
        return "blocked"
    return "passed"

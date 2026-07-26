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


def run_learning_gate_for_issue(
    issue_path: Path,
    *,
    skip: bool = False,
    cwd: Path | None = None,
    targets: list[str] | None = None,
) -> Literal["passed", "blocked", "skipped"]:
    """Invoke proof-first-task loop for an issue and return the gate verdict.

    ``skip=True`` short-circuits to "skipped" (honours --skip-learning-gate).
    ENH-2814: the loop's failure terminals (``blocked``, ``impl_failed``) carry
    ``failure: true``, so a blocked gate is read straight off the subprocess
    exit code (``FAILURE_TERMINAL_EXIT_CODE``) instead of the state file left
    behind on disk.

    Args:
        issue_path: Absolute path to the issue file.
        skip: If True, return "skipped" immediately without running the loop.
        cwd: Working directory for the subprocess (and state-file lookup).
            Defaults to ``Path.cwd()`` when None.
        targets: The already-resolved ``learning_tests_required`` registry
            (ENH-2209). When non-empty, forwarded as a ``targets_csv``
            context input so ``proof-first-task`` proves this exact list
            instead of re-extracting one via ``assumption-firewall``
            (ENH-2405). ``None``/empty preserves the JIT extraction fallback.
    """
    if skip:
        return "skipped"

    working_dir = cwd or Path.cwd()
    cmd = [
        "ll-loop",
        "run",
        "proof-first-task",
        "--context",
        f"issue_file={issue_path}",
    ]
    if targets:
        cmd += ["--context", f"targets_csv={','.join(targets)}"]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=working_dir,
    )

    # Function-local import: little_loops.fsm's package __init__ pulls in the
    # executor, which imports little_loops.config — a cycle at module scope.
    from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE

    if proc.returncode == FAILURE_TERMINAL_EXIT_CODE:
        return "blocked"
    return "passed"

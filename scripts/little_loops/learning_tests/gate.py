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
) -> Literal["passed", "blocked", "impl_failed", "skipped"]:
    """Invoke proof-first-task loop for an issue and return the gate verdict.

    ``skip=True`` short-circuits to "skipped" (honours --skip-learning-gate).
    ``proof-first-task``'s two failure terminals (``blocked``, ``impl_failed``)
    both carry ``failure: true`` and share the same subprocess exit code
    (``FAILURE_TERMINAL_EXIT_CODE``), so the exit code alone cannot
    discriminate a genuine registry-gate block from a delegated impl-loop
    crash (BUG-2833). On a failure exit, the archived ``LoopState`` for the
    just-completed run is consulted via ``list_run_history()`` to read the
    actual terminal name; only the ``blocked`` terminal yields ``"blocked"``
    (autodev's unproven-external-API-deps remedy path). Any other terminal
    (including ``impl_failed``, or an unreadable/missing history) yields
    ``"impl_failed"`` so the caller treats it as a generic implementation
    failure rather than misrouting it to the learning-gate remedy.

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
    from little_loops.fsm.persistence import list_run_history
    from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE

    if proc.returncode == FAILURE_TERMINAL_EXIT_CODE:
        history = list_run_history("proof-first-task", loops_dir=working_dir / ".loops")
        if history and history[0].current_state == "blocked":
            return "blocked"
        return "impl_failed"
    return "passed"

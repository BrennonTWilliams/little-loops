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
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from little_loops.learning_tests import LearnTestRecord

logger = logging.getLogger(__name__)

# Slack added on top of the child's own queue-wait budget (BUG-3085) so the
# outer subprocess.run(timeout=...) only fires as a backstop against a
# genuinely wedged child, never as the normal exit path for a clean timeout.
_QUEUE_WAIT_BACKSTOP_SLACK_SECONDS = 60


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
    """Determine the learning-gate verdict for an issue and return it.

    ``skip=True`` short-circuits to "skipped" (honours --skip-learning-gate).

    When ``targets`` is non-empty (ENH-2834), the ``learning_tests_required``
    registry has already been resolved by the caller, so this invokes
    ``ready-to-implement-gate`` directly instead of chaining through
    ``proof-first-task``'s redundant impl-loop delegation (any impl work
    there is thrown away — ``issue_manager.py`` implements the issue itself
    afterwards). ``ready-to-implement-gate`` has exactly two terminals
    (``done``/``blocked``), and the subprocess exit code alone discriminates
    between the two — but a non-``FAILURE_TERMINAL_EXIT_CODE`` non-zero exit
    (e.g. a scope-lock conflict, BUG-2864) is neither: it means the loop
    never ran to a terminal at all, so it is reported as ``"impl_failed"``
    (infra failure) rather than misdiagnosed as a genuine refuted-target
    ``"blocked"``. This mirrors the proven
    ``_run_learning_gate_preflight()`` pattern in
    ``little_loops.cli.sprint.run``.

    When ``targets`` is empty, the JIT-extraction fallback (assumption-firewall
    path) is still needed, so this falls back to ``proof-first-task``.
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
            (ENH-2209). When non-empty, proves this exact list directly via
            ``ready-to-implement-gate`` (ENH-2834). ``None``/empty preserves
            the JIT extraction fallback through ``proof-first-task``.
    """
    if skip:
        return "skipped"

    working_dir = cwd or Path.cwd()

    if targets:
        # BUG-3085: pass the configured queue-wait budget down explicitly so
        # the child's --queue wait *is* the caller's budget, rather than
        # racing it against an independent hard-coded outer timeout. The
        # outer subprocess.run timeout is set above this budget purely as a
        # backstop for a genuinely wedged child.
        from little_loops.config import BRConfig

        _queue_wait_budget = BRConfig(working_dir).loops.queue_wait_timeout_seconds

        cmd = [
            "ll-loop",
            "run",
            "ready-to-implement-gate",
            "--context",
            f"targets={','.join(targets)}",
            # ENH-3073 follow-up: refine-to-ready-issue and the other
            # issue-management loops are now scoped to .issues/ +
            # ${context.run_dir} (BUG-3087), so this no longer conflicts on
            # the whole repo — but a genuine .issues/ overlap with a
            # concurrent ll-auto issue can still occur. --queue waits for the
            # conflicting loop to release the lock instead of instantly
            # collapsing to impl_failed.
            "--queue",
            "--queue-timeout",
            str(_queue_wait_budget),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=working_dir,
                timeout=_queue_wait_budget + _QUEUE_WAIT_BACKSTOP_SLACK_SECONDS,
            )
        except subprocess.TimeoutExpired:
            logger.error(
                "ready-to-implement-gate did not clear a scope-lock conflict "
                "within its %ds queue-wait budget; treating as an infra "
                "failure (not a refuted target)",
                _queue_wait_budget,
            )
            return "impl_failed"

        # Function-local import: little_loops.fsm's package __init__ pulls in
        # the executor, which imports little_loops.config — a cycle at
        # module scope.
        from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE

        if proc.returncode == 0:
            return "passed"
        if proc.returncode == FAILURE_TERMINAL_EXIT_CODE:
            return "blocked"
        # Infra failure (scope-lock conflict, crash, missing binary) — not a
        # refuted target (BUG-2864). Log the captured output so the reason
        # is recoverable instead of silently collapsing to "blocked".
        logger.error(
            "ready-to-implement-gate failed with exit %d (not a refuted target)\n"
            "stdout: %s\nstderr: %s",
            proc.returncode,
            proc.stdout,
            proc.stderr,
        )
        return "impl_failed"

    cmd = [
        "ll-loop",
        "run",
        "proof-first-task",
        "--context",
        f"issue_file={issue_path}",
    ]
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

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
import sys
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


def resolve_target_version(target: str) -> tuple[str, str] | None:
    """Resolve *target* to an ``(distribution_name, installed_version)`` pair.

    Returns ``None`` — meaning "no comparable version, use the age-based
    path" — for every case that is not an installed third-party distribution:

    - stdlib targets, checked against :data:`sys.stdlib_module_names`
      **before** any ``importlib.metadata`` call. This ordering is load-bearing
      (ENH-3125): ``importlib.metadata.version("asyncio")`` resolves to an
      abandoned PyPI backport whose version has nothing to do with stdlib
      ``asyncio``, which would pin the record to a version that never drifts.
    - targets that are not installed distributions (``PackageNotFoundError``) —
      the common case, since ``LearnTestRecord.target`` is free text
      ("Anthropic SDK streaming", "Python pathlib") rather than an installable
      identifier.

    Never raises: any unexpected ``importlib.metadata`` failure degrades to
    ``None`` so a resolver problem falls back to today's age-based staleness
    rather than breaking a gate.
    """
    try:
        # Same first-token reduction normalize_target() uses, so both sides of
        # every "which package is this?" question share one convention.
        parts = target.split() if target else []
        if not parts:
            return None
        name = parts[0].lower()
        if name.split(".")[0] in sys.stdlib_module_names:
            return None

        from little_loops.init.install_check import installed_package_version

        version = installed_package_version(name)
    except Exception:  # noqa: BLE001 — resolver failure must degrade, never propagate
        logger.debug("version resolution failed for target %r", target, exc_info=True)
        return None
    if version is None:
        return None
    return name, version


def _installed_version_for(record: LearnTestRecord, installed_version: str | None) -> str | None:
    """Return the version to compare *record* against, or None if incomparable."""
    if installed_version is not None:
        return installed_version
    if not record.proven_package:
        return None
    resolved = resolve_target_version(record.proven_package)
    return resolved[1] if resolved else None


def is_record_stale(
    record: LearnTestRecord,
    stale_after_days: int,
    *,
    installed_version: str | None = None,
    version_aware: bool = True,
    backstop_multiplier: int = 12,
) -> bool:
    """Return True if the record's proof is stale.

    Staleness is **version drift OR age past a threshold** (ENH-3125), not age
    alone. Concretely, True when any of:

    - a version was captured for the record and the currently installed version
      of the same distribution differs (**drift** — fires regardless of age, so
      a record can go stale the day after it was proven);
    - no comparable version is available (nothing captured, the package no
      longer resolves, or the target is stdlib/not a distribution) **and**
      ``age_days > stale_after_days`` — the pre-ENH-3125 behavior, and the path
      every un-backfilled record still takes;
    - a version was captured and **matches**, and ``age_days >
      stale_after_days * backstop_multiplier``. A matching version buys a
      longer leash, not an unlimited one: proof also decays when *our* usage of
      an API changes, and a hard-pinned dependency would otherwise never be
      re-verified.

    Args:
        record: A LearnTestRecord with a ``date`` field (ISO 8601: YYYY-MM-DD).
        stale_after_days: Age threshold in days. Clamped to minimum 1 to
            prevent ``stale_after_days=0`` from being a footgun that passes
            all records whose date is exactly today.
        installed_version: Pre-resolved installed version, for callers that
            already have one (and for tests). When omitted, this resolves
            ``record.proven_package`` itself — callers that loop over many
            records would otherwise each duplicate that resolution.
        version_aware: When False, restores pure age-based staleness exactly as
            it behaved before ENH-3125 (``learning_tests.version_aware_staleness``).
        backstop_multiplier: Multiplier applied to ``stale_after_days`` for the
            version-matches case (``learning_tests.version_match_backstop_multiplier``).

    Returns:
        True if the record is stale; False if fresh or the date is unparseable
        and no drift was detected.
    """
    # A manual `ll-learning-tests mark-stale` outranks everything (ENH-3125
    # AC-6): a matching installed version must never rescue a record an
    # operator explicitly staled. Call sites that already OR on
    # ``status == "stale"`` are unaffected; this closes the sites that don't.
    if record.status == "stale":
        return True

    threshold = max(1, stale_after_days)

    if version_aware and record.proven_version:
        current = _installed_version_for(record, installed_version)
        if current is not None:
            if current != record.proven_version:
                # Drift short-circuits: it is independent of age, so it must be
                # decided before the date parse (which returns False on a
                # malformed date).
                return True
            threshold = threshold * max(1, backstop_multiplier)

    try:
        record_date = datetime.date.fromisoformat(record.date)
    except (ValueError, TypeError, AttributeError):
        return False
    age_days = (datetime.date.today() - record_date).days
    return age_days > threshold


def describe_staleness(
    record: LearnTestRecord,
    stale_after_days: int,
    *,
    installed_version: str | None = None,
    version_aware: bool = True,
    backstop_multiplier: int = 12,
) -> str | None:
    """Return a short reason a record is stale, or None if it is fresh.

    Keeps nudge text truthful about *why* a record went stale (ENH-3125 AC-8):
    a record staled by version drift on the day it was proven must not render
    as ``"stale: 0 days old"``. Argument semantics match
    :func:`is_record_stale`.
    """
    if record.status == "stale":
        return "stale: marked stale"

    if version_aware and record.proven_version:
        current = _installed_version_for(record, installed_version)
        if current is not None and current != record.proven_version:
            pkg = record.proven_package or record.target
            return f"stale: {pkg} {record.proven_version} → {current}"

    if not is_record_stale(
        record,
        stale_after_days,
        installed_version=installed_version,
        version_aware=version_aware,
        backstop_multiplier=backstop_multiplier,
    ):
        return None

    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(record.date)).days
    except (ValueError, TypeError, AttributeError):
        return "stale"
    return f"stale: {age} days old"


def run_learning_gate_for_issue(
    issue_path: Path,
    *,
    skip: bool = False,
    cwd: Path | None = None,
    targets: list[str] | None = None,
) -> Literal["passed", "blocked", "impl_failed", "infra_failed", "skipped"]:
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
    (e.g. a scope-lock conflict, BUG-2864), a backstop ``TimeoutExpired``
    (a genuinely wedged child, BUG-3085), or a missing ``ll-loop`` binary
    (``FileNotFoundError``, ENH-3084) is neither: the loop never ran to a
    terminal at all. These are reported as ``"infra_failed"`` (ENH-3084) —
    distinct from both a genuine refuted-target ``"blocked"`` and BUG-2833's
    delegated-impl ``"impl_failed"`` — so callers can retry/skip instead of
    consuming a remediation cycle. This mirrors the proven
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
            # BUG-3085: the child carries its own --queue-timeout budget, so a
            # parent-side TimeoutExpired only fires as the backstop for a
            # genuinely wedged child — NOT a scope-lock wait that exhausted its
            # budget (that exits non-zero on its own and lands in the
            # returncode branch below). Report it as an infra failure either way.
            logger.error(
                "ready-to-implement-gate child wedged past its %ds queue-wait "
                "budget backstop; treating as an infra failure (not a refuted "
                "target)",
                _queue_wait_budget,
            )
            return "infra_failed"
        except FileNotFoundError:
            # ENH-3084: ll-loop binary missing — the gate could not run at all.
            logger.error(
                "ready-to-implement-gate could not start (ll-loop binary not "
                "found); treating as an infra failure (not a refuted target)",
                exc_info=True,
            )
            return "infra_failed"

        # Function-local import: little_loops.fsm's package __init__ pulls in
        # the executor, which imports little_loops.config — a cycle at
        # module scope.
        from little_loops.fsm.types import FAILURE_TERMINAL_EXIT_CODE

        if proc.returncode == 0:
            return "passed"
        if proc.returncode == FAILURE_TERMINAL_EXIT_CODE:
            return "blocked"
        # Infra failure (scope-lock contention, queue-wait exhaustion, crash,
        # missing binary) — not a refuted target (BUG-2864) and not a genuine
        # delegated-impl failure (BUG-2833). Log the captured output so the
        # reason is recoverable instead of silently collapsing to "blocked"
        # or being misrouted as an implementation failure (ENH-3084).
        logger.error(
            "ready-to-implement-gate failed with exit %d (not a refuted target)\n"
            "stdout: %s\nstderr: %s",
            proc.returncode,
            proc.stdout,
            proc.stderr,
        )
        return "infra_failed"

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

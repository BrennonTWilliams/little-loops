"""ll-issues set-status: Transition an issue to a new status value."""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from little_loops.issue_lifecycle import ClosureReason, DeferReason

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pathlib import Path

    from little_loops.config import BRConfig

# ENH-2870: derived from DeferReason so the two can't drift out of lockstep
# (previously a hardcoded literal set duplicating the enum).
_DEFERRAL_REASON_CODES = frozenset(r.value for r in DeferReason)
# ENH-2969: derived from ClosureReason, same rationale as _DEFERRAL_REASON_CODES.
_CLOSED_REASON_CODES = frozenset(r.value for r in ClosureReason)


@dataclass
class StatusTransition:
    """Outcome of :func:`apply_status_transition` — what changed, for the caller to render.

    Returned rather than printed so non-CLI callers (the FEAT-3149 `issue_set_status`
    MCP tool) can reuse the same write path. `ll-mcp` speaks JSON-RPC over stdout on the
    stdio transport, where a stray `print()` corrupts the protocol frame.
    """

    issue_id: str
    path: Path
    old_status: str
    new_status: str
    updates: dict[str, str]
    cascaded: list[tuple[str, str]] = field(default_factory=list)
    skipped: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)


def status_frontmatter_updates(
    status: str, *, reason: str | None = None, by: str | None = None
) -> dict[str, str]:
    """Frontmatter updates for a status transition.

    Stamps ``completed_at`` when moving to ``done`` so manual CLI
    completions carry a timestamp — matching the lifecycle/parallel/sync
    paths. Without it, release notes and history queries that filter on
    ``completed_at`` silently drop CLI-completed issues (BUG-942 family).

    Stamps ``deferred_by``/``deferred_reason``/``deferred_date`` when moving
    to ``deferred`` so downstream tooling (FEAT-2665's resurfacing sweep) can
    distinguish an automation circuit-breaker deferral from a deliberate
    human one (ENH-2664). Reuses the ``deferred_reason``/``deferred_date``
    keys ENH-2535 already introduced for closure-context display; under
    ``deferred_by: automation`` the value is a machine enum code instead of
    free-text prose.

    Writes ``closed_reason`` when moving to ``done``/``cancelled`` and a
    ``--reason`` closure code was given, mirroring the deferral stamping
    above so automation can record *why* an issue closed (e.g.
    ``already_fixed``) the same way it records why one was deferred
    (ENH-2749).

    Module-level (FEAT-3149) rather than a closure inside :func:`cmd_set_status`, so
    the MCP `issue_set_status` tool can compute the same update set for its dry-run
    preview without duplicating — and therefore drifting from — these rules.
    """
    from little_loops.issue_lifecycle import _completed_at_now

    updates = {"status": status}
    if status == "done":
        updates["completed_at"] = _completed_at_now()
        if reason:
            updates["closed_reason"] = reason
    elif status == "cancelled":
        if reason:
            updates["closed_reason"] = reason
    elif status == "deferred":
        updates["deferred_by"] = by or "human"
        updates["deferred_date"] = _completed_at_now()
        if reason:
            updates["deferred_reason"] = reason
    return updates


def apply_status_transition(
    config: BRConfig,
    path: Path,
    issue_id: str,
    status: str,
    *,
    reason: str | None = None,
    by: str | None = None,
    cascade_to: str | None = None,
) -> StatusTransition:
    """Write a new status into an issue's frontmatter, optionally cascading to children.

    The non-printing core of :func:`cmd_set_status`, extracted (FEAT-3149) so the MCP
    `issue_set_status` tool can perform exactly the mutation the CLI performs instead of
    reimplementing it. Validation of ``status``/``reason``/``cascade`` combinations stays
    in :func:`cmd_set_status` (it is argparse-shaped and user-facing); this function
    assumes an already-valid transition.

    Args:
        config: Project configuration.
        path: Resolved issue file path.
        issue_id: Issue ID, used for the returned record and history rows.
        status: Target status value.
        reason: Optional deferral/closure reason code.
        by: Optional ``deferred_by`` actor for a ``deferred`` transition.
        cascade_to: When set, the status to propagate to active parent-children.

    Returns:
        A :class:`StatusTransition` describing what was written.
    """
    from little_loops.file_utils import acquire_lock, atomic_write, issue_lock_path
    from little_loops.frontmatter import parse_frontmatter, update_frontmatter
    from little_loops.issue_progress import _OPEN_STATUSES

    updates = status_frontmatter_updates(status, reason=reason, by=by)

    # BUG-3150: read-modify-write under one lock, written atomically. The
    # cascade below shares this hold — releasing between the parent write and
    # the child writes would let a concurrent writer observe (or interleave
    # with) a half-applied cascade. `atomic_write` replaces `write_text`, whose
    # truncate-then-write could leave a torn or empty issue file.
    with acquire_lock(issue_lock_path(path, config.issues.base_dir)):
        content = path.read_text()
        old_status = parse_frontmatter(content).get("status", "unknown")
        new_content = update_frontmatter(content, updates)
        atomic_write(path, new_content)

        result = StatusTransition(
            issue_id=issue_id,
            path=path,
            old_status=old_status,
            new_status=status,
            updates=updates,
        )

        # Capture content snapshot on status transition (Decision 2: Option C — direct call,
        # same pattern as user_prompt_submit.py calling record_correction() without EventBus).
        try:
            from little_loops.session_store import (
                record_issue_event,
                record_issue_snapshot,
                resolve_history_db,
            )

            db_path = resolve_history_db()
            record_issue_snapshot(db_path, issue_id, status, str(path))

            # Also write the issue_events row (BUG-2770): record_issue_snapshot alone
            # left issue_sessions/issue_effort() with no rows to join against, since
            # both are rooted in issue_events, which was previously written only by
            # the EventBus SQLiteTransport path (not exercised by set-status).
            from little_loops.issue_lifecycle import _session_id_or_none

            fm = parse_frontmatter(new_content)
            record_issue_event(
                db_path,
                issue_id,
                status,
                session_id=_session_id_or_none(),
                issue_type=fm.get("type"),
                priority=fm.get("priority"),
                discovered_by=fm.get("discovered_by"),
                captured_at=fm.get("captured_at"),
                completed_at=fm.get("completed_at"),
            )
        except (sqlite3.Error, ImportError, OSError):
            logger.warning(
                "%s: failed to record issue_events/issue_snapshots row for status %s",
                issue_id,
                status,
                exc_info=True,
            )

        # Cascade to children
        if cascade_to is not None:
            fm = parse_frontmatter(content)
            epic_id = fm.get("id", issue_id).upper()

            from little_loops.issue_parser import find_issues

            all_issues = find_issues(config)

            # Cascade follows parent: → child edges ONLY, transitively. relates_to:
            # and blocked_by: are non-hierarchical association edges; cascading
            # through them silently flipped the status of unrelated issues —
            # including sibling epics — during routine epic closure (BUG-2265).
            children_by_parent: dict[str, list] = {}
            for i in all_issues:
                if i.parent:
                    children_by_parent.setdefault(i.parent.upper(), []).append(i)

            # Transitive closure over parent edges, breadth-first from the epic.
            descendants: list = []
            seen: set[str] = {epic_id}
            queue = list(children_by_parent.get(epic_id, []))
            while queue:
                child = queue.pop(0)
                cid = child.issue_id.upper()
                if cid in seen:
                    continue
                seen.add(cid)
                descendants.append(child)
                queue.extend(children_by_parent.get(cid, []))

            active = [c for c in descendants if c.status in _OPEN_STATUSES]
            result.skipped = len(descendants) - len(active)

            child_updates = status_frontmatter_updates(cascade_to, reason=reason, by=by)
            for child in active:
                try:
                    child_content = child.path.read_text()
                    child_new = update_frontmatter(child_content, child_updates)
                    atomic_write(child.path, child_new)
                    result.cascaded.append((child.issue_id, cascade_to))
                except OSError as exc:
                    result.failures.append((child.issue_id, str(exc)))

    return result


def cmd_set_status(config: BRConfig, args: argparse.Namespace) -> int:
    """Write a new status value into an issue's YAML frontmatter.

    Validates the target status against the canonical enum before writing.
    Prints the before→after transition to stdout on success.

    When ``--cascade`` is set, also propagates the status to active children
    (those with status ``open``, ``in_progress``, or ``blocked``). Child
    resolution follows ``parent:`` edges **only**, transitively. Association
    edges (``relates_to:``, ``blocked_by:``) are non-hierarchical and never
    trigger a cascade — cascading through them silently mutated unrelated
    issues, including sibling epics (BUG-2265).

    This function owns argument validation and all printing; the locked
    read-modify-write itself lives in :func:`apply_status_transition`
    (FEAT-3149), which the MCP ``issue_set_status`` tool shares.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id, .status, .cascade, .cascade_to

    Returns:
        Exit code (0 = success, 1 = error); exit 1 if any child update fails.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.issue_progress import _TERMINAL_STATUSES

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    # Validate cascade before making any changes
    cascade = getattr(args, "cascade", False)
    if cascade:
        if args.status not in _TERMINAL_STATUSES:
            print(
                f"Error: --cascade is only valid when target status is done or "
                f"cancelled, got '{args.status}'.",
                file=sys.stderr,
            )
            return 1

    # Validate --reason against the target status: deferral codes only apply to
    # a `deferred` transition, closure codes only apply to `done`/`cancelled`.
    reason = getattr(args, "reason", None)
    if reason:
        if reason in _DEFERRAL_REASON_CODES and args.status != "deferred":
            print(
                f"Error: --reason '{reason}' is a deferral reason code and only "
                f"valid when target status is deferred, got '{args.status}'.",
                file=sys.stderr,
            )
            return 1
        if reason in _CLOSED_REASON_CODES and args.status not in ("done", "cancelled"):
            print(
                f"Error: --reason '{reason}' is a closure reason code and only "
                f"valid when target status is done or cancelled, got '{args.status}'.",
                file=sys.stderr,
            )
            return 1

    result = apply_status_transition(
        config,
        path,
        args.issue_id,
        args.status,
        reason=reason,
        by=getattr(args, "by", None),
        cascade_to=args.cascade_to if cascade else None,
    )

    print(f"{args.issue_id}: {result.old_status} → {args.status}")

    if cascade:
        total = len(result.cascaded) + len(result.failures)
        print(f"  Cascading to {total} active parent-children (default: {args.cascade_to}):")
        for child_id, child_status in result.cascaded:
            print(f"    {child_id} → {child_status}")
        for child_id, error in result.failures:
            print(f"    {child_id}: FAILED ({error})", file=sys.stderr)
        if result.skipped:
            print(f"  ({result.skipped} children already terminal/other — unchanged)")
        if result.failures:
            return 1

    return 0

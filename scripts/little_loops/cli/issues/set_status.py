"""ll-issues set-status: Transition an issue to a new status value."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig

_DEFERRAL_REASON_CODES = frozenset(
    {
        "blocked_by_unmet",
        "remediation_stalled",
        "low_readiness",
        "gate_blocked",
        "decision_unresolved",
        "oversized_atomic",
    }
)
_CLOSED_REASON_CODES = frozenset({"already_fixed"})


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

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id, .status, .cascade, .cascade_to

    Returns:
        Exit code (0 = success, 1 = error); exit 1 if any child update fails.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter, update_frontmatter
    from little_loops.issue_lifecycle import _completed_at_now
    from little_loops.issue_progress import _OPEN_STATUSES, _TERMINAL_STATUSES

    def _status_updates(status: str) -> dict[str, str]:
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
        """
        updates = {"status": status}
        if status == "done":
            updates["completed_at"] = _completed_at_now()
            reason = getattr(args, "reason", None)
            if reason:
                updates["closed_reason"] = reason
        elif status == "cancelled":
            reason = getattr(args, "reason", None)
            if reason:
                updates["closed_reason"] = reason
        elif status == "deferred":
            updates["deferred_by"] = getattr(args, "by", None) or "human"
            updates["deferred_date"] = _completed_at_now()
            reason = getattr(args, "reason", None)
            if reason:
                updates["deferred_reason"] = reason
        return updates

    path = _resolve_issue_id(config, args.issue_id)
    if path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    # Validate cascade before making any changes
    if getattr(args, "cascade", False):
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

    content = path.read_text()
    old_status = parse_frontmatter(content).get("status", "unknown")
    new_content = update_frontmatter(content, _status_updates(args.status))
    path.write_text(new_content)
    print(f"{args.issue_id}: {old_status} → {args.status}")

    # Capture content snapshot on status transition (Decision 2: Option C — direct call,
    # same pattern as user_prompt_submit.py calling record_correction() without EventBus).
    try:
        from little_loops.session_store import record_issue_snapshot, resolve_history_db

        db_path = resolve_history_db()
        record_issue_snapshot(db_path, args.issue_id, args.status, str(path))
    except Exception:
        pass

    # Cascade to children
    if getattr(args, "cascade", False):
        fm = parse_frontmatter(content)
        epic_id = fm.get("id", args.issue_id).upper()

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
        skipped = [c for c in descendants if c not in active]

        print(f"  Cascading to {len(active)} active parent-children (default: {args.cascade_to}):")

        failures = 0
        for child in active:
            try:
                child_content = child.path.read_text()
                child_new = update_frontmatter(child_content, _status_updates(args.cascade_to))
                child.path.write_text(child_new)
                print(f"    {child.issue_id} → {args.cascade_to}")
            except OSError as exc:
                print(f"    {child.issue_id}: FAILED ({exc})", file=sys.stderr)
                failures += 1

        if skipped:
            print(f"  ({len(skipped)} children already terminal/other — unchanged)")

        if failures:
            return 1

    return 0

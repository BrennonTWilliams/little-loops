"""ll-issues link: idempotent dependency-edge writer for issue frontmatter."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from little_loops.cli.output import print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig

_FIELD_FLAGS = ("blocked_by", "depends_on", "relates_to")


@dataclass
class LinkResult:
    """Outcome of :func:`apply_link` — the report payload, unrendered.

    Returned rather than printed so non-CLI callers (the FEAT-3149 ``issue_link``
    MCP tool) can reuse the same write path. ``ll-mcp`` speaks JSON-RPC over stdout on
    the stdio transport, where a stray ``print()`` corrupts the protocol frame.

    ``status`` is one of ``unchanged``/``linked``/``unlinked``/``would_link``/
    ``would_unlink`` — the same vocabulary ``--json`` already emits.
    """

    issue_id: str
    field: str
    target_id: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "issue_id": self.issue_id,
            "field": self.field,
            "target_id": self.target_id,
            "status": self.status,
        }


@dataclass
class ParentLinkResult:
    """Outcome of :func:`apply_parent_link` — the unrendered report payload.

    ``status`` is ``assigned``/``would_assign``/``unchanged``/``rejected``/
    ``partial_failure``. ``child_would_change``/``epic_would_change`` are the
    computed plan (also set on a real run); ``child_written``/``epic_written``
    record only writes that actually completed. ``epic_body_status`` is
    ``updated``/``already_present``/``missing_heading`` (empty on rejection).
    """

    issue_id: str
    target_id: str
    status: str
    reason: str = ""
    detail: str = ""
    child_would_change: bool = False
    epic_would_change: bool = False
    child_written: bool = False
    epic_written: bool = False
    epic_body_status: str = ""
    previous_parents: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    repair: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "issue_id": self.issue_id,
            "target_id": self.target_id,
            "status": self.status,
            "reason": self.reason,
            "detail": self.detail,
            "child_would_change": self.child_would_change,
            "epic_would_change": self.epic_would_change,
            "child_written": self.child_written,
            "epic_written": self.epic_written,
            "epic_body_status": self.epic_body_status,
            "previous_parents": list(self.previous_parents),
            "warnings": list(self.warnings),
            "repair": self.repair,
        }


def add_link_parser(subs: argparse._SubParsersAction) -> None:
    """Register the ``link`` sub-command parser.

    Args:
        subs: The subparsers action returned by ``parser.add_subparsers()``
    """
    from little_loops.cli_args import add_config_arg

    lk = subs.add_parser(
        "link",
        aliases=["lk"],
        help="Write or remove a dependency edge, or assign an issue to an EPIC (--parent)",
    )
    lk.set_defaults(command="link")
    lk.add_argument("issue_id", help="Issue ID (e.g., 518, FEAT-518, P3-FEAT-518)")

    group = lk.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--blocked-by",
        dest="blocked_by",
        metavar="ID",
        help="Target issue that hard-blocks issue_id",
    )
    group.add_argument(
        "--depends-on",
        dest="depends_on",
        metavar="ID",
        help="Target issue that is a soft prerequisite of issue_id",
    )
    group.add_argument(
        "--relates-to",
        dest="relates_to",
        metavar="ID",
        help="Target issue that is related to issue_id",
    )
    group.add_argument(
        "--parent",
        dest="parent",
        metavar="EPIC",
        help="Assign issue_id (a BUG/FEAT/ENH) to this EPIC: set parent:, sync an existing "
        "epic: key, and add it to the EPIC's ## Children list",
    )

    lk.add_argument(
        "--reparent",
        action="store_true",
        default=False,
        dest="reparent",
        help="With --parent: replace an existing, different parent instead of rejecting it",
    )
    lk.add_argument(
        "--unlink",
        "--remove",
        action="store_true",
        default=False,
        dest="unlink",
        help="Remove the edge instead of adding it",
    )
    lk.add_argument(
        "--reciprocal",
        action="store_true",
        default=False,
        dest="reciprocal",
        help="Also write the matching reverse edge on the target issue",
    )
    lk.add_argument(
        "--force",
        action="store_true",
        default=False,
        dest="force",
        help="Skip target-existence validation",
    )
    lk.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json_output",
        help="Output result as JSON",
    )
    lk.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run",
        help="Report what would change without writing",
    )
    add_config_arg(lk)


def apply_link(
    config: BRConfig,
    *,
    issue_id: str,
    field: str,
    target: str,
    unlink: bool = False,
    reciprocal: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> LinkResult:
    """Add or remove a dependency edge in an issue's frontmatter.

    The non-printing core of :func:`cmd_link`, extracted (FEAT-3149) so the MCP
    ``issue_link`` tool can perform exactly the mutation the CLI performs instead of
    reimplementing it.

    Idempotent (re-running an add/remove is a no-op reporting ``unchanged``),
    list-aware (creates the key when absent, appends when present), and
    validating (the target must resolve to an existing issue unless
    ``force``). A ``blocked_by``/``depends_on`` edge that would introduce a
    cycle in the blocking graph is refused.

    Args:
        config: Project configuration.
        issue_id: Source issue ID in any resolvable form.
        field: One of ``blocked_by``/``depends_on``/``relates_to``.
        target: Target issue ID.
        unlink: Remove the edge instead of adding it.
        reciprocal: Also write the matching reverse edge on the target.
        force: Skip target-existence validation.
        dry_run: Report what would change without writing.

    Returns:
        A :class:`LinkResult` describing the outcome.

    Raises:
        ValueError: for the conditions :func:`cmd_link` reports as errors —
            unknown ``field``, unresolvable source or target, or a refused cycle.
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.file_utils import acquire_lock, atomic_write, issue_lock_path
    from little_loops.frontmatter import parse_frontmatter, update_frontmatter

    if field not in _FIELD_FLAGS:
        raise ValueError(
            f"Unknown link field: {field!r} (expected one of {', '.join(_FIELD_FLAGS)})"
        )

    source_path = _resolve_issue_id(config, issue_id)
    if source_path is None:
        raise ValueError(f"Issue '{issue_id}' not found.")

    # BUG-3150: the source read, the cycle check, the source write and the
    # reciprocal target write are one read-modify-write and share a single lock
    # hold. Releasing between the source and reciprocal writes is exactly what
    # leaves a source claiming an edge the target has no backlink for. Writes go
    # through `atomic_write`; `write_text` truncates first and could leave a torn
    # or empty issue file.
    with acquire_lock(issue_lock_path(source_path, config.issues.base_dir)):
        source_content = source_path.read_text()
        source_fm = parse_frontmatter(source_content)
        source_id = source_fm.get("id", issue_id).upper()

        target_path = _resolve_issue_id(config, target)
        if target_path is None and not force:
            raise ValueError(f"Target issue '{target}' not found.")

        target_id = target.upper()
        if target_path is not None:
            target_fm = parse_frontmatter(target_path.read_text())
            target_id = target_fm.get("id", target_id).upper()

        existing = source_fm.get(field) or []
        if not isinstance(existing, list):
            existing = [existing]

        def _result(status: str) -> LinkResult:
            return LinkResult(issue_id=source_id, field=field, target_id=target_id, status=status)

        if unlink:
            if target_id not in existing:
                return _result("unchanged")
            if dry_run:
                return _result("would_unlink")
            new_list = [item for item in existing if item != target_id]
            atomic_write(source_path, update_frontmatter(source_content, {field: new_list}))
            return _result("unlinked")

        if target_id in existing:
            return _result("unchanged")

        if field in ("blocked_by", "depends_on"):
            cycle_error = _check_cycle(config, source_id, target_id, field)
            if cycle_error is not None:
                raise ValueError(f"refusing edge — {cycle_error}")

        if dry_run:
            return _result("would_link")

        new_list = [*existing, target_id]
        atomic_write(source_path, update_frontmatter(source_content, {field: new_list}))

        if reciprocal and target_path is not None:
            _write_reciprocal(target_path, field, source_id)

        return _result("linked")


_CHILD_TYPES = frozenset({"BUG", "FEAT", "ENH"})
_VALID_STATUSES = frozenset({"open", "in_progress", "blocked", "deferred", "done", "cancelled"})


class _ParentReject(Exception):
    """Internal: a validation failure mapped to a rejected :class:`ParentLinkResult`."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def _canonical_identity(path, text: str) -> tuple[str, str, dict]:
    """Return ``(issue_id, type_prefix, frontmatter)`` after checking file consistency.

    The filename's anchored ``TYPE-NNN`` is canonical; ``id:``/``type:`` in the
    frontmatter must agree with it.
    """
    from little_loops.frontmatter import parse_frontmatter
    from little_loops.issue_parser import _ANCHORED_FILENAME_RE

    match = _ANCHORED_FILENAME_RE.match(path.name)
    if match is None:
        raise _ParentReject("identity_mismatch", f"{path.name}: filename carries no TYPE-NNN id")
    type_prefix = match.group(2).upper()
    issue_id = f"{type_prefix}-{match.group(3)}"
    fm = parse_frontmatter(text.replace("\r\n", "\n"))
    fm_id = fm.get("id")
    if isinstance(fm_id, str) and fm_id.strip().upper() != issue_id:
        raise _ParentReject(
            "identity_mismatch", f"{path.name}: frontmatter id {fm_id!r} != filename {issue_id}"
        )
    fm_type = fm.get("type")
    if isinstance(fm_type, str) and fm_type.strip().upper() != type_prefix:
        raise _ParentReject(
            "identity_mismatch", f"{issue_id}: frontmatter type {fm_type!r} != {type_prefix}"
        )
    return issue_id, type_prefix, fm


def apply_parent_link(
    config: BRConfig,
    *,
    issue_id: str,
    target: str,
    reparent: bool = False,
    dry_run: bool = False,
) -> ParentLinkResult:
    """Assign one BUG/FEAT/ENH to an EPIC: child ``parent:`` plus the EPIC's Children bullet.

    The non-printing core of ``ll-issues link CHILD --parent EPIC``. Both files are
    re-read, validated and planned under a single issue-tree lock, then written
    child first. ``epic:`` is synchronized only when the child already carries the
    key. Validation failures are returned as ``rejected`` results (never raised) so
    the CLI can emit one structured document; ``dry_run`` performs the same
    validation and planning with zero writes.
    """
    from little_loops.cli.issues.create import AmbiguousChildrenSection
    from little_loops.cli.issues.link_epics import (
        ConflictingParent,
        _fallback_title,
        _plan_pair,
        _read_raw,
        intentional_parentless,
    )
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.file_utils import acquire_lock, atomic_write, issue_lock_path
    from little_loops.frontmatter import find_post_fence_entries

    result = ParentLinkResult(
        issue_id=issue_id.upper(), target_id=target.upper(), status="rejected"
    )

    def reject(reason: str, detail: str) -> ParentLinkResult:
        result.status, result.reason, result.detail = "rejected", reason, detail
        return result

    child_path = _resolve_issue_id(config, issue_id)
    if child_path is None:
        return reject("not_found", f"Issue '{issue_id}' not found.")
    epic_path = _resolve_issue_id(config, target)
    if epic_path is None:
        return reject("not_found", f"Target issue '{target}' not found.")

    try:
        with acquire_lock(issue_lock_path(child_path, config.issues.base_dir)):
            child_text = _read_raw(child_path)
            epic_text = _read_raw(epic_path)
            try:
                child_id, child_type, child_fm = _canonical_identity(child_path, child_text)
                epic_id, epic_type, epic_fm = _canonical_identity(epic_path, epic_text)
                result.issue_id, result.target_id = child_id, epic_id
                if child_type not in _CHILD_TYPES:
                    raise _ParentReject(
                        "invalid_type",
                        f"{child_id} is a {child_type}; only BUG/FEAT/ENH can be assigned",
                    )
                if epic_type != "EPIC":
                    raise _ParentReject("invalid_target", f"{epic_id} is not an EPIC")

                entries = find_post_fence_entries(child_text.replace("\r\n", "\n"))
                if entries:
                    keys = ", ".join(sorted({e.key for e in entries}))
                    raise _ParentReject(
                        "metadata_unsafe",
                        f"{child_id}: parenting key(s) after the frontmatter fence ({keys}); "
                        f"repair with `ll-issues format-check {child_id} --fix --apply`",
                    )
                for key in ("parent", "epic"):
                    value = child_fm.get(key)
                    if value is not None and not isinstance(value, str):
                        raise _ParentReject(
                            "malformed_metadata", f"{child_id}: {key}: must be a scalar EPIC id"
                        )
                status_value = child_fm.get("status")
                if status_value is None:
                    child_status = "open"
                elif isinstance(status_value, str) and status_value in _VALID_STATUSES:
                    child_status = status_value
                else:
                    raise _ParentReject(
                        "malformed_metadata", f"{child_id}: invalid status {status_value!r}"
                    )

                try:
                    plan = _plan_pair(
                        child_text,
                        epic_text,
                        child_id=child_id,
                        epic_id=epic_id,
                        title=_fallback_title(child_text, child_path),
                        sync_epic_key="if_present",
                        reparent=reparent,
                        child_status=child_status,
                    )
                except ConflictingParent as exc:
                    raise _ParentReject("conflicting_parent", str(exc)) from exc
                except AmbiguousChildrenSection as exc:
                    raise _ParentReject("ambiguous_children_section", str(exc)) from exc
                except ValueError as exc:
                    raise _ParentReject("metadata_unsafe", str(exc)) from exc
            except _ParentReject as exc:
                return reject(exc.reason, exc.detail)

            result.epic_body_status = plan.body_status
            result.child_would_change = plan.new_child != child_text
            result.epic_would_change = plan.new_epic != epic_text
            result.previous_parents = list(plan.displaced)
            if intentional_parentless(child_fm):
                result.warnings.append(
                    f"{child_id} is marked intentionally parentless (parentless_reason); "
                    f"explicit --parent overrides that opt-out"
                )
            if epic_fm.get("status") in ("done", "cancelled"):
                result.warnings.append(f"{epic_id} is {epic_fm.get('status')}")
            if plan.body_status == "missing_heading":
                result.warnings.append(
                    f"{epic_id} has no '## Children' heading; EPIC body not written"
                )
            for old in plan.displaced:
                if _resolve_issue_id(config, old) is None:
                    result.warnings.append(f"previous parent {old} was not found")
                else:
                    result.warnings.append(
                        f"{old} may still list {child_id} under its ## Children; review it manually"
                    )

            changed = result.child_would_change or result.epic_would_change
            if dry_run:
                result.status = "would_assign" if changed else "unchanged"
                return result

            if result.child_would_change:
                try:
                    atomic_write(child_path, plan.new_child, shared_mode=True)
                except OSError as exc:
                    return reject(
                        "write_failed", f"{child_id} write failed ({exc}); no file changed"
                    )
                result.child_written = True
            if result.epic_would_change:
                try:
                    atomic_write(epic_path, plan.new_epic, shared_mode=True)
                except OSError as exc:
                    result.status = "partial_failure" if result.child_written else "rejected"
                    result.reason = "write_failed"
                    result.repair = f"ll-issues link {child_id} --parent {epic_id}"
                    result.detail = f"{epic_id} ## Children write failed ({exc}); " + (
                        f"{child_id} was already assigned. Re-run `{result.repair}` "
                        f"or `ll-issues epic-consistency --fix {epic_id}` to repair"
                        if result.child_written
                        else "no file changed"
                    )
                    return result
                result.epic_written = True
            result.status = "assigned" if changed else "unchanged"
            return result
    except TimeoutError as exc:
        return reject("lock_timeout", str(exc))


def _cmd_link_parent(config: BRConfig, args: argparse.Namespace) -> int:
    """CLI shell around :func:`apply_parent_link` (the ``--parent`` branch of ``link``)."""
    as_json = getattr(args, "json_output", False)
    conflicts = [
        flag
        for flag, active in (
            ("--unlink/--remove", getattr(args, "unlink", False)),
            ("--force", getattr(args, "force", False)),
            ("--reciprocal", getattr(args, "reciprocal", False)),
        )
        if active
    ]
    if conflicts:
        result = ParentLinkResult(
            issue_id=args.issue_id,
            target_id=args.parent,
            status="rejected",
            reason="unsupported_flag_combination",
            detail=f"--parent cannot be combined with {', '.join(conflicts)}",
        )
    else:
        result = apply_parent_link(
            config,
            issue_id=args.issue_id,
            target=args.parent,
            reparent=getattr(args, "reparent", False),
            dry_run=args.dry_run,
        )

    if as_json:
        print_json(result.to_dict())
    else:
        _report_parent(result)
    return 1 if result.status in ("rejected", "partial_failure") else 0


def _report_parent(result: ParentLinkResult) -> None:
    """Text rendering of a :class:`ParentLinkResult`."""
    if result.status in ("rejected", "partial_failure"):
        print(f"Error: {result.reason}: {result.detail}", file=sys.stderr)
        if result.status == "partial_failure":
            print(
                f"{result.issue_id}: parent = {result.target_id} — partial "
                f"(child written: {result.child_written}, EPIC written: {result.epic_written})"
            )
        return
    verb = {
        "assigned": "assigned",
        "would_assign": "would assign (dry-run)",
        "unchanged": "unchanged (already assigned)",
    }[result.status]
    print(f"{result.issue_id}: parent = {result.target_id} — {verb}")
    if result.epic_body_status == "missing_heading":
        print(f"Note: {result.target_id} has no '## Children' heading; EPIC body not written.")
    if result.previous_parents:
        print(f"Replaced previous parent(s): {', '.join(result.previous_parents)}")
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)


def cmd_link(config: BRConfig, args: argparse.Namespace) -> int:
    """Add or remove a dependency edge in an issue's frontmatter.

    Argparse/printing shell around :func:`apply_link`, which owns the locked
    read-modify-write and is shared with the MCP ``issue_link`` tool (FEAT-3149).

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id, one of .blocked_by/.depends_on/
            .relates_to, .unlink, .reciprocal, .force, .json_output, .dry_run

    Returns:
        Exit code (0 = success, 1 = error)
    """
    if getattr(args, "parent", None):
        return _cmd_link_parent(config, args)
    if getattr(args, "reparent", False):
        print("Error: --reparent is only valid with --parent", file=sys.stderr)
        return 1

    field_name = next(name for name in _FIELD_FLAGS if getattr(args, name, None))
    target_input: str = getattr(args, field_name)

    try:
        result = apply_link(
            config,
            issue_id=args.issue_id,
            field=field_name,
            target=target_input,
            unlink=args.unlink,
            reciprocal=args.reciprocal,
            force=args.force,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _report(
        args,
        source_id=result.issue_id,
        field=result.field,
        target_id=result.target_id,
        status=result.status,
    )
    return 0


def _write_reciprocal(target_path, field: str, source_id: str) -> None:
    """Write the reverse edge on the target issue for --reciprocal.

    ``blocked_by`` reciprocates as ``blocks`` (one-sided ``blocks:``
    declarations are already honoured by ``DependencyGraph.from_issues``).
    ``relates_to`` reciprocates as ``relates_to`` (bidirectional convention
    already used by ``dependency_mapper/operations.py``). ``depends_on`` has
    no reciprocal field — it is one-directional by convention.
    """
    from little_loops.file_utils import atomic_write
    from little_loops.frontmatter import parse_frontmatter, update_frontmatter

    reciprocal_field = {"blocked_by": "blocks", "relates_to": "relates_to"}.get(field)
    if reciprocal_field is None:
        return

    content = target_path.read_text()
    fm = parse_frontmatter(content)
    existing = fm.get(reciprocal_field) or []
    if not isinstance(existing, list):
        existing = [existing]
    if source_id in existing:
        return
    new_content = update_frontmatter(content, {reciprocal_field: [*existing, source_id]})
    # BUG-3150: caller (`cmd_link`) already holds the issue-tree mutation lock —
    # do not acquire it here, flock contends within a single process.
    atomic_write(target_path, new_content)


def _check_cycle(config: BRConfig, source_id: str, target_id: str, field: str) -> str | None:
    """Return an error message if adding the edge would introduce a cycle.

    Builds the dependency graph including the prospective edge and runs
    ``topological_sort()``, which raises ``ValueError`` on cycles.
    """
    from little_loops.dependency_graph import DependencyGraph
    from little_loops.dependency_mapper import gather_all_issue_ids
    from little_loops.issue_parser import find_issues_for_graph

    issues = find_issues_for_graph(config)
    for issue in issues:
        if issue.issue_id == source_id:
            if field == "blocked_by" and target_id not in issue.blocked_by:
                issue.blocked_by = [*issue.blocked_by, target_id]
            elif field == "depends_on" and target_id not in issue.depends_on:
                issue.depends_on = [*issue.depends_on, target_id]

    all_known_ids: set[str] | None = None
    try:
        issues_dir = config.project_root / config.issues.base_dir
        all_known_ids = gather_all_issue_ids(issues_dir, config=config)
    except Exception:
        pass

    graph = DependencyGraph.from_issues(issues, all_known_ids=all_known_ids)
    try:
        graph.topological_sort()
    except ValueError as exc:
        return str(exc)
    return None


def _report(
    args: argparse.Namespace, *, source_id: str, field: str, target_id: str, status: str
) -> None:
    """Print the result of a link/unlink operation as text or JSON."""
    if getattr(args, "json_output", False):
        print_json(
            {
                "issue_id": source_id,
                "field": field,
                "target_id": target_id,
                "status": status,
            }
        )
        return
    verb = {
        "unchanged": "unchanged (already present)"
        if not args.unlink
        else "unchanged (not present)",
        "linked": "linked",
        "unlinked": "unlinked",
        "would_link": "would link (dry-run)",
        "would_unlink": "would unlink (dry-run)",
    }[status]
    print(f"{source_id}: {field} += {target_id} — {verb}")

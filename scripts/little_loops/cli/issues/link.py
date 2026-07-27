"""ll-issues link: idempotent dependency-edge writer for issue frontmatter."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from little_loops.cli.output import print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig

_FIELD_FLAGS = ("blocked_by", "depends_on", "relates_to")


def add_link_parser(subs: argparse._SubParsersAction) -> None:
    """Register the ``link`` sub-command parser.

    Args:
        subs: The subparsers action returned by ``parser.add_subparsers()``
    """
    from little_loops.cli_args import add_config_arg

    lk = subs.add_parser(
        "link",
        aliases=["lk"],
        help="Write or remove a dependency edge in issue frontmatter",
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


def cmd_link(config: BRConfig, args: argparse.Namespace) -> int:
    """Add or remove a dependency edge in an issue's frontmatter.

    Idempotent (re-running an add/remove is a no-op reporting ``unchanged``),
    list-aware (creates the key when absent, appends when present), and
    validating (the target must resolve to an existing issue unless
    ``--force``). A ``blocked_by``/``depends_on`` edge that would introduce a
    cycle in the blocking graph is refused.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id, one of .blocked_by/.depends_on/
            .relates_to, .unlink, .reciprocal, .force, .json_output, .dry_run

    Returns:
        Exit code (0 = success, 1 = error)
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter, update_frontmatter

    field = next(name for name in _FIELD_FLAGS if getattr(args, name, None))
    target_input: str = getattr(args, field)

    source_path = _resolve_issue_id(config, args.issue_id)
    if source_path is None:
        print(f"Error: Issue '{args.issue_id}' not found.", file=sys.stderr)
        return 1

    source_content = source_path.read_text()
    source_fm = parse_frontmatter(source_content)
    source_id = source_fm.get("id", args.issue_id).upper()

    target_path = _resolve_issue_id(config, target_input)
    if target_path is None and not args.force:
        print(f"Error: Target issue '{target_input}' not found.", file=sys.stderr)
        return 1

    target_id = target_input.upper()
    if target_path is not None:
        target_fm = parse_frontmatter(target_path.read_text())
        target_id = target_fm.get("id", target_id).upper()

    existing = source_fm.get(field) or []
    if not isinstance(existing, list):
        existing = [existing]

    if args.unlink:
        if target_id not in existing:
            _report(args, source_id=source_id, field=field, target_id=target_id, status="unchanged")
            return 0
        new_list = [item for item in existing if item != target_id]
        if args.dry_run:
            _report(
                args, source_id=source_id, field=field, target_id=target_id, status="would_unlink"
            )
            return 0
        new_content = update_frontmatter(source_content, {field: new_list})
        source_path.write_text(new_content)
        _report(args, source_id=source_id, field=field, target_id=target_id, status="unlinked")
        return 0

    if target_id in existing:
        _report(args, source_id=source_id, field=field, target_id=target_id, status="unchanged")
        return 0

    if field in ("blocked_by", "depends_on"):
        cycle_error = _check_cycle(config, source_id, target_id, field)
        if cycle_error is not None:
            print(f"Error: refusing edge — {cycle_error}", file=sys.stderr)
            return 1

    new_list = [*existing, target_id]

    if args.dry_run:
        _report(args, source_id=source_id, field=field, target_id=target_id, status="would_link")
        return 0

    new_content = update_frontmatter(source_content, {field: new_list})
    source_path.write_text(new_content)

    if args.reciprocal and target_path is not None:
        _write_reciprocal(target_path, field, source_id)

    _report(args, source_id=source_id, field=field, target_id=target_id, status="linked")
    return 0


def _write_reciprocal(target_path, field: str, source_id: str) -> None:
    """Write the reverse edge on the target issue for --reciprocal.

    ``blocked_by`` reciprocates as ``blocks`` (one-sided ``blocks:``
    declarations are already honoured by ``DependencyGraph.from_issues``).
    ``relates_to`` reciprocates as ``relates_to`` (bidirectional convention
    already used by ``dependency_mapper/operations.py``). ``depends_on`` has
    no reciprocal field — it is one-directional by convention.
    """
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
    target_path.write_text(new_content)


def _check_cycle(config: BRConfig, source_id: str, target_id: str, field: str) -> str | None:
    """Return an error message if adding the edge would introduce a cycle.

    Builds the dependency graph including the prospective edge and runs
    ``topological_sort()``, which raises ``ValueError`` on cycles.
    """
    from little_loops.dependency_graph import DependencyGraph
    from little_loops.issue_parser import find_issues

    issues = find_issues(config)
    for issue in issues:
        if issue.issue_id == source_id:
            if field == "blocked_by" and target_id not in issue.blocked_by:
                issue.blocked_by = [*issue.blocked_by, target_id]
            elif field == "depends_on" and target_id not in issue.depends_on:
                issue.depends_on = [*issue.depends_on, target_id]

    graph = DependencyGraph.from_issues(issues)
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

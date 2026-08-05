"""ll-issues format-check: deterministic structural linter for issue formatting (ENH-2426)."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import FormatGaps


@contextmanager
def _suppress_frontmatter_deprecations(
    *, keep: str | None = None
) -> Iterator[list[logging.LogRecord]]:
    """Silence ``issue_parser``'s deprecated-frontmatter-key warnings for the block.

    Modeled on ``acquire_lock()`` in ``file_utils.py``: install-yield-teardown,
    guaranteed cleanup via ``finally``. Yields the list of records it swallowed
    so the caller can tally them into a summary line (ENH-2961) — a single-ID
    ``format-check`` parses the whole corpus just to build the status map used
    for prose_dep_drift/stale_prose_dep resolution, and those unrelated files'
    deprecation warnings drowned out the one verdict line the caller asked for.

    *keep*, when given, is the targeted issue's filename (``path.name``): its
    own warnings pass through undisturbed since the corpus-wide status-map
    load parses every issue including the target, and ``issue_parser``'s
    once-per-process dedup ledger would otherwise silently absorb the
    warning before the target's own dedicated parse gets a chance to emit it.
    """
    captured: list[logging.LogRecord] = []

    class _SwallowFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if keep is not None and isinstance(record.args, tuple) and record.args:
                if record.args[0] == keep:
                    return True
            captured.append(record)
            return False

    parser_logger = logging.getLogger("little_loops.issue_parser")
    swallow_filter = _SwallowFilter()
    parser_logger.addFilter(swallow_filter)
    try:
        yield captured
    finally:
        parser_logger.removeFilter(swallow_filter)


def add_format_check_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the format-check subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "format-check",
        help="Deterministic structural linter for issue formatting "
        "(missing/renamed/empty/boilerplate/malformed_id/prose_dep_drift/"
        "stale_prose_dep/program_design_nonspecific/deprecated_key/"
        "multi_frontmatter/testable/stale_file_ref/unmarked_superseded_directive/"
        "duplicate_findings_block/ambiguous_file_ref/missing_behavior_parity)",
    )
    p.set_defaults(command="format-check")
    p.add_argument(
        "issue_id",
        nargs="?",
        default=None,
        help="Issue ID (e.g., 2426, ENH-2426, P3-ENH-2426); omit when using --all",
    )
    p.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Sweep every active issue (bugs/features/enhancements/epics) instead of one",
    )
    p.add_argument(
        "--next",
        action="store_true",
        help="Target the highest-priority active issue, no type filter (ENH-2946); "
        "mutually exclusive with issue_id/--all",
    )
    p.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    p.add_argument(
        "--fix",
        action="store_true",
        help="Preview backfilling blocked_by from prose_dep_drift gaps via "
        "`ll-issues link` (dry-run by default; combine with --apply to write)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="With --fix, write the proposed edges instead of previewing them",
    )
    add_config_arg(p)
    return p


def _fix_prose_deps(config: BRConfig, source_id: str, targets: list[str], *, apply: bool) -> None:
    """Backfill ``blocked_by`` edges for *source_id*'s prose_dep_drift targets.

    Invokes ``cmd_link`` in-process (the only idempotent, cycle-safe write
    path — FEAT-2851) rather than editing frontmatter directly. Dry-run by
    default; pass ``apply=True`` to actually write.
    """
    from little_loops.cli.issues.link import cmd_link

    for target_id in targets:
        ns = argparse.Namespace(
            issue_id=source_id,
            blocked_by=target_id,
            depends_on=None,
            relates_to=None,
            unlink=False,
            reciprocal=False,
            force=False,
            json_output=False,
            dry_run=not apply,
        )
        cmd_link(config, ns)


def _print_gaps(gaps: FormatGaps) -> None:
    for name in gaps.missing:
        print(f"  missing: {name}")
    for entry in gaps.renamed:
        print(f"  renamed: {entry}")
    for name in gaps.empty:
        print(f"  empty: {name}")
    for name in gaps.boilerplate:
        print(f"  boilerplate: {name}")
    for entry in gaps.malformed_id:
        print(f"  malformed_id: {entry}")
    for entry in gaps.prose_dep_drift:
        print(f"  prose_dep_drift: {entry}")
    for entry in gaps.stale_prose_dep:
        print(f"  stale_prose_dep: {entry}")
    for entry in gaps.program_design_nonspecific:
        print(f"  program_design_nonspecific: {entry}")
    for entry in gaps.deprecated_key:
        print(f"  deprecated_key: {entry}")
    for entry in gaps.multi_frontmatter:
        print(f"  multi_frontmatter: {entry}")
    for entry in gaps.testable:
        print(f"  testable: {entry} (doc-only signals; set an explicit `testable:` key)")
    for entry in gaps.stale_file_ref:
        print(f"  stale_file_ref: {entry}")
    for entry in gaps.unmarked_superseded_directive:
        print(f"  unmarked_superseded_directive: {entry}")
    for entry in gaps.duplicate_findings_block:
        print(f"  duplicate_findings_block: {entry}")
    for entry in gaps.ambiguous_file_ref:
        print(f"  ambiguous_file_ref: {entry}")
    for entry in gaps.missing_behavior_parity:
        print(f"  missing_behavior_parity: {entry}")


def cmd_format_check(config: BRConfig, args: argparse.Namespace) -> int:
    """Report structural format gaps for one issue, or sweep all active issues.

    Gap classes: missing/renamed/empty/boilerplate/malformed_id/
    prose_dep_drift/stale_prose_dep/program_design_nonspecific/deprecated_key/
    multi_frontmatter/testable/stale_file_ref/unmarked_superseded_directive/
    duplicate_findings_block/ambiguous_file_ref/missing_behavior_parity.

    Every class in :class:`FormatGaps` must have a matching loop in
    :func:`_print_gaps`; a class counted by ``has_gaps`` but not rendered
    exits 1 with an empty report (the `testable` regression, ENH-2946).

    Returns:
        0 when structurally compliant (all issues, in --all mode), 1 when gaps
        were found (any issue, in --all mode) or the issue is not found.
    """
    from little_loops.cli.output import print_json
    from little_loops.issue_parser import (
        check_format_gaps,
        find_highest_priority_issue,
        find_issues,
        superseded_marker_count,
    )
    from little_loops.issue_progress import _ALL_STATUSES
    from little_loops.issue_template import resolve_templates_dir
    from little_loops.text_utils import build_ref_index

    issue_id: str | None = getattr(args, "issue_id", None)
    check_all: bool = getattr(args, "all", False)
    next_flag: bool = getattr(args, "next", False)
    fmt = getattr(args, "format", "text") or "text"
    fix: bool = getattr(args, "fix", False)
    apply_fix: bool = getattr(args, "apply", False)

    target_count = sum([bool(issue_id), check_all, next_flag])
    if target_count == 0:
        print("Error: provide an issue ID, --all, or --next", file=sys.stderr)
        return 1
    if target_count > 1:
        print("Error: issue ID, --all, and --next are mutually exclusive", file=sys.stderr)
        return 1

    path = None
    if next_flag:
        next_issue = find_highest_priority_issue(config)
        if next_issue is None:
            print("No active issues found.", file=sys.stderr)
            return 1
        path = next_issue.path
        issue_id = next_issue.issue_id
    elif not check_all:
        from little_loops.cli.issues.show import _resolve_issue_id

        assert issue_id is not None
        path = _resolve_issue_id(config, issue_id)
        if path is None:
            print(f"Error: Issue '{issue_id}' not found.", file=sys.stderr)
            return 1

    suppressed: list[logging.LogRecord] = []
    if check_all:
        all_issues = find_issues(config, status_filter=set(_ALL_STATUSES))
    else:
        # Single-ID mode: the corpus-wide load is still required to build
        # issue_statuses (prose_dep_drift vs stale_prose_dep resolution), but
        # its deprecation warnings are off-topic here — they concern files
        # the caller isn't editing. Suppress and tally instead (ENH-2961);
        # let the target's own warnings (if any) through.
        assert path is not None
        with _suppress_frontmatter_deprecations(keep=path.name) as suppressed:
            all_issues = find_issues(config, status_filter=set(_ALL_STATUSES))
    issue_statuses = {info.issue_id: info.status for info in all_issues}
    templates_dir = resolve_templates_dir(config)
    # Built exactly once per invocation, ahead of every check_format_gaps()
    # call site below (single-ID, --all, and the post-`--fix` re-checks) —
    # this is where the "index built at most once" AC (ENH-2983) is enforced.
    ref_index = build_ref_index(config.project_root)

    if check_all:
        # Sweep only active issues (default status_filter excludes
        # done/cancelled/deferred) — a closed issue's stale prose is no
        # longer worth gating on. `issue_statuses` above still covers every
        # issue so drift/stale classification against *targets* is accurate.
        active_issues = find_issues(config)
        results: dict[str, FormatGaps] = {}
        for info in sorted(active_issues, key=lambda i: i.issue_id):
            try:
                gaps = check_format_gaps(
                    info.path,
                    templates_dir=templates_dir,
                    issue_statuses=issue_statuses,
                    ref_index=ref_index,
                )
            except OSError as exc:
                print(f"Warning: skipping {info.path}: {exc}", file=sys.stderr)
                continue
            if fix and gaps.prose_dep_drift:
                _fix_prose_deps(config, info.issue_id, gaps.prose_dep_drift, apply=apply_fix)
                if apply_fix:
                    gaps = check_format_gaps(
                        info.path,
                        templates_dir=templates_dir,
                        issue_statuses=issue_statuses,
                        ref_index=ref_index,
                    )
            if gaps.has_gaps:
                results[info.issue_id] = gaps

        if fmt == "json":
            print_json({issue_id: gaps.to_dict() for issue_id, gaps in results.items()})
            return 1 if results else 0

        if not results:
            print(f"Formatted: all {len(active_issues)} issue(s) are structurally compliant")
            return 0

        print(
            f"Needs formatting — structural gaps in {len(results)}/{len(active_issues)} issue(s):"
        )
        for gapped_id, gaps in results.items():
            print(f"{gapped_id}:")
            _print_gaps(gaps)
        return 1

    assert issue_id is not None
    assert path is not None

    gaps = check_format_gaps(
        path,
        templates_dir=templates_dir,
        issue_statuses=issue_statuses,
        ref_index=ref_index,
    )

    if fix and gaps.prose_dep_drift:
        resolved = next((info for info in all_issues if info.path == path), None)
        source_id = resolved.issue_id if resolved is not None else issue_id
        _fix_prose_deps(config, source_id, gaps.prose_dep_drift, apply=apply_fix)
        if apply_fix:
            gaps = check_format_gaps(
                path,
                templates_dir=templates_dir,
                issue_statuses=issue_statuses,
                ref_index=ref_index,
            )

    if suppressed:
        suppressed_issues = {
            record.args[0]
            for record in suppressed
            if isinstance(record.args, tuple) and record.args
        }
        print(
            f"({len(suppressed_issues)} other issue(s) have deprecated frontmatter keys — "
            "run `ll-issues format-check` to list)",
            file=sys.stderr,
        )

    if fmt == "json":
        # ENH-2992: the single-issue payload also carries marker *presence* —
        # the inverse of the unmarked_superseded_directive gap class — so
        # autodev.yaml's check_reconcile_needed can read its contradiction
        # predicate from the same call it already makes. Deliberately not a
        # FormatGaps field: a standing marker is not a structural gap, so it
        # must not feed has_gaps (and hence the exit code) or widen
        # to_dict()'s dict[str, list[str]] contract. The --all payload is
        # unchanged; it maps issue_id → gaps and no consumer queries markers
        # in bulk.
        payload: dict[str, object] = dict(gaps.to_dict())
        payload["superseded_marker_count"] = superseded_marker_count(path)
        print_json(payload)
        return 1 if gaps.has_gaps else 0

    if not gaps.has_gaps:
        print(f"Formatted: {issue_id} is structurally compliant")
        return 0

    print(f"Needs formatting — structural gaps for {issue_id}:")
    _print_gaps(gaps)
    return 1

"""ll-issues decisions: Manage rules, decisions, and exceptions log."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def add_decisions_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the decisions subparser with all sub-sub-commands on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "decisions",
        help="Manage rules, decisions, and exceptions log",
    )
    p.set_defaults(command="decisions")
    p.set_defaults(_decisions_parser=p)

    add_config_arg(p)
    subsubs = p.add_subparsers(dest="subcommand")

    # -- list --
    list_p = subsubs.add_parser("list", help="List decisions log entries")
    list_p.add_argument(
        "--type",
        choices=["rule", "decision", "exception", "coupling"],
        default=None,
        help="Filter by entry type",
    )
    list_p.add_argument("--category", default=None, help="Filter by category")
    list_p.add_argument("--label", default=None, help="Filter by label")
    list_p.add_argument(
        "--archetype",
        default=None,
        help="Filter coupling entries by archetype label (e.g. add-cli-command)",
    )
    list_p.add_argument(
        "--no-outcome",
        action="store_true",
        help="Show only DecisionEntry records with no recorded outcome",
    )
    list_p.add_argument(
        "--before",
        default=None,
        metavar="ISO-8601",
        help="Show entries with timestamp before this date",
    )
    list_p.add_argument(
        "--scope",
        default=None,
        help="Filter DecisionEntry records by scope (e.g. 'issue', 'project')",
    )
    list_p.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    list_p.add_argument(
        "--active-only",
        action="store_true",
        help="Exclude entries superseded by a newer entry",
    )
    add_config_arg(list_p)

    # -- add --
    add_p = subsubs.add_parser("add", help="Add a new entry to the decisions log")
    add_p.add_argument(
        "--type",
        required=True,
        choices=["rule", "decision", "exception", "coupling"],
        help="Entry type",
    )
    add_p.add_argument("--category", required=True, help="Category (e.g. 'architecture')")
    add_p.add_argument(
        "--rule",
        default=None,
        help="Rule or decision text (required for type=rule or type=decision)",
    )
    add_p.add_argument(
        "--rationale",
        required=True,
        help="Why this rule/decision/exception applies",
    )
    add_p.add_argument("--issue", default=None, help="Related issue ID (e.g. FEAT-1894)")
    add_p.add_argument("--label", default=None, help="Comma-separated labels")
    add_p.add_argument(
        "--enforcement",
        choices=["required", "advisory"],
        default="advisory",
        help="Enforcement level for type=rule (default: advisory)",
    )
    add_p.add_argument(
        "--rule-ref",
        default=None,
        dest="rule_ref",
        metavar="RULE-ID",
        help="Reference to the rule being excepted (required for type=exception)",
    )
    add_p.add_argument(
        "--alternatives-rejected",
        default=None,
        dest="alternatives_rejected",
        help="Alternatives considered and rejected (for type=decision or type=exception)",
    )
    add_p.add_argument(
        "--supersedes",
        default=None,
        metavar="ENTRY-ID",
        help="ID of the entry this one supersedes (for type=rule)",
    )
    add_p.add_argument(
        "--scope",
        default="issue",
        help="Decision scope: 'issue' (default) or 'project' (for type=decision)",
    )
    add_p.add_argument(
        "--id",
        default=None,
        dest="entry_id",
        metavar="ENTRY-ID",
        help="Explicit entry ID (auto-generated if omitted)",
    )
    # Coupling-specific flags (only relevant when --type=coupling)
    add_p.add_argument(
        "--if-changed",
        default=None,
        dest="if_changed",
        metavar="GLOB",
        help="Glob pattern matching files being modified (required for type=coupling)",
    )
    add_p.add_argument(
        "--then-check",
        default=None,
        dest="then_check",
        metavar="PATHS",
        help="Comma-separated file/pattern list to audit for wiring gaps (required for type=coupling)",
    )
    add_p.add_argument(
        "--tier",
        choices=["hard", "soft", "fyi"],
        default="soft",
        help="Coupling tier: hard (must change together), soft (should update), fyi (informational)",
    )
    add_p.add_argument(
        "--archetype",
        default=None,
        dest="archetype",
        help="Named bundle label grouping related coupling rules (e.g. add-cli-command)",
    )
    add_config_arg(add_p)

    # -- outcome --
    outcome_p = subsubs.add_parser("outcome", help="Record the outcome of a decision entry")
    outcome_p.add_argument("id", help="Entry ID to record outcome for")
    outcome_p.add_argument(
        "--result",
        required=True,
        choices=["worked", "did_not_work", "mixed", "reversed"],
        help="Outcome result",
    )
    outcome_p.add_argument("--notes", default=None, help="Free-text notes about the outcome")
    outcome_p.add_argument(
        "--measured-at",
        default=None,
        dest="measured_at",
        metavar="ISO-8601",
        help="When the outcome was measured (default: now)",
    )
    outcome_p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing outcome",
    )
    add_config_arg(outcome_p)

    # -- generate (stub) --
    gen_p = subsubs.add_parser(
        "generate",
        help="Generate decisions log entries from completed issues",
    )
    gen_p.add_argument(
        "--from",
        dest="source",
        default="completed",
        choices=["completed"],
        help="Source to generate from (default: completed)",
    )
    add_config_arg(gen_p)

    # -- sync (stub) --
    sync_p = subsubs.add_parser("sync", help="Sync active rules to .ll/ll.local.md")
    add_config_arg(sync_p)

    # -- promote --
    promote_p = subsubs.add_parser(
        "promote",
        help="Convert a decision entry to a rule",
    )
    promote_p.add_argument("entry_id", help="ID of the decision entry to promote")
    promote_p.add_argument(
        "--enforcement",
        choices=["required", "advisory"],
        default="required",
        help="Enforcement level for the resulting rule (default: required)",
    )
    add_config_arg(promote_p)

    return p


def cmd_decisions(config: BRConfig, args: argparse.Namespace) -> int:
    """Dispatch decisions sub-sub-commands; returns 0 on success, 1 on error."""
    from pathlib import Path

    from little_loops.decisions import (
        CouplingEntry,
        DecisionEntry,
        ExceptionEntry,
        RuleEntry,
        add_entry,
        list_entries,
        resolve_active,
        set_outcome,
    )

    if not getattr(args, "subcommand", None):
        args._decisions_parser.print_help()
        return 1

    # Resolve the decisions log path from config
    path = Path(config.project_root) / config.decisions.log_path

    sub = args.subcommand

    if sub == "list":
        return _cmd_list(args, path, list_entries, resolve_active)

    if sub == "add":
        return _cmd_add(
            args,
            path,
            RuleEntry,
            DecisionEntry,
            ExceptionEntry,
            CouplingEntry,
            add_entry,
            list_entries,
        )

    if sub == "outcome":
        return _cmd_outcome(args, path, set_outcome)

    if sub == "generate":
        from little_loops.decisions import generate_from_completed

        count = generate_from_completed(config)
        print(
            f"Generated {count} decision entr{'y' if count == 1 else 'ies'} from completed issues."
        )
        return 0

    if sub == "sync":
        return _cmd_sync(path)

    if sub == "promote":
        from little_loops.decisions import DecisionEntry, RuleEntry, load_decisions, save_decisions

        return _cmd_promote(args, path, load_decisions, save_decisions, RuleEntry, DecisionEntry)

    print(f"Unknown subcommand: {sub!r}", file=sys.stderr)
    return 1


def _cmd_list(args, path, list_entries, resolve_active) -> int:
    import json

    entries = list_entries(
        path=path,
        type=getattr(args, "type", None),
        category=getattr(args, "category", None),
        label=getattr(args, "label", None),
    )

    # Post-filters
    if getattr(args, "no_outcome", False):
        from little_loops.decisions import DecisionEntry

        entries = [e for e in entries if isinstance(e, DecisionEntry) and e.outcome is None]

    if getattr(args, "before", None):
        entries = [e for e in entries if e.timestamp < args.before]

    if getattr(args, "scope", None):
        from little_loops.decisions import DecisionEntry

        entries = [e for e in entries if isinstance(e, DecisionEntry) and e.scope == args.scope]

    if getattr(args, "active_only", False):
        entries = resolve_active(entries)

    if getattr(args, "archetype", None):
        from little_loops.decisions import CouplingEntry as _CE

        entries = [e for e in entries if isinstance(e, _CE) and e.archetype == args.archetype]

    fmt = getattr(args, "format", "text") or "text"
    if fmt == "json":
        print(json.dumps([e.to_dict() for e in entries], indent=2))
        return 0

    if not entries:
        print("(no entries)")
        return 0

    for entry in entries:
        _print_entry(entry)
    return 0


def _print_entry(entry) -> None:
    from little_loops.decisions import CouplingEntry, DecisionEntry, ExceptionEntry, RuleEntry

    label_str = ", ".join(entry.labels) if entry.labels else ""
    print(
        f"{entry.id}  [{entry.type}]  {entry.category}" + (f"  ({label_str})" if label_str else "")
    )
    if isinstance(entry, (RuleEntry, DecisionEntry)):
        print(f"  rule: {entry.rule}")
    elif isinstance(entry, ExceptionEntry):
        print(f"  rule_ref: {entry.rule_ref}")
    elif isinstance(entry, CouplingEntry):
        print(f"  if_changed: {entry.if_changed}")
        print(f"  then_check: {', '.join(entry.then_check)}")
        print(f"  tier: {entry.tier}")
        if entry.archetype:
            print(f"  archetype: {entry.archetype}")
    if entry.rationale:
        print(f"  rationale: {entry.rationale}")
    if isinstance(entry, DecisionEntry) and entry.outcome:
        print(f"  outcome: {entry.outcome.result} @ {entry.outcome.measured_at}")


def _cmd_add(
    args, path, RuleEntry, DecisionEntry, ExceptionEntry, CouplingEntry, add_entry, list_entries
) -> int:
    entry_type = args.type

    # Validate type-specific required fields
    if entry_type == "rule" and not getattr(args, "rule", None):
        print("Error: --rule is required for type 'rule'", file=sys.stderr)
        return 1
    if entry_type == "decision" and not getattr(args, "rule", None):
        print("Error: --rule is required for type 'decision' (the decision text)", file=sys.stderr)
        return 1
    if entry_type == "exception" and not getattr(args, "rule_ref", None):
        print("Error: --rule-ref is required for type 'exception'", file=sys.stderr)
        return 1
    if entry_type == "coupling":
        if not getattr(args, "if_changed", None):
            print("Error: --if-changed is required for type 'coupling'", file=sys.stderr)
            return 1
        if not getattr(args, "then_check", None):
            print("Error: --then-check is required for type 'coupling'", file=sys.stderr)
            return 1

    # Generate an ID if not provided
    entry_id = getattr(args, "entry_id", None)
    if not entry_id:
        existing = list_entries(path=path, type=entry_type)
        prefix = {
            "rule": args.category.upper() if args.category else "RULE",
            "decision": args.category.upper() if args.category else "DEC",
            "exception": args.category.upper() + "-EX" if args.category else "EX",
            "coupling": "COUPLING",
        }[entry_type]
        entry_id = f"{prefix}-{len(existing) + 1:03d}"

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    labels = [lbl.strip() for lbl in args.label.split(",")] if getattr(args, "label", None) else []

    if entry_type == "rule":
        entry = RuleEntry(
            id=entry_id,
            timestamp=timestamp,
            category=args.category,
            labels=labels,
            rationale=args.rationale,
            rule=args.rule,
            enforcement=getattr(args, "enforcement", "advisory"),
            supersedes=getattr(args, "supersedes", None),
            issue=getattr(args, "issue", None),
        )
    elif entry_type == "decision":
        entry = DecisionEntry(
            id=entry_id,
            timestamp=timestamp,
            category=args.category,
            labels=labels,
            rationale=args.rationale,
            rule=args.rule,
            alternatives_rejected=getattr(args, "alternatives_rejected", None),
            issue=getattr(args, "issue", None),
            scope=getattr(args, "scope", "issue"),
        )
    elif entry_type == "coupling":
        then_check = [t.strip() for t in args.then_check.split(",")]
        entry = CouplingEntry(
            id=entry_id,
            timestamp=timestamp,
            category=args.category,
            labels=labels,
            rationale=args.rationale,
            if_changed=args.if_changed,
            then_check=then_check,
            tier=getattr(args, "tier", "soft"),
            archetype=getattr(args, "archetype", None),
            enforcement=getattr(args, "enforcement", "advisory"),
            issue=getattr(args, "issue", None),
        )
    else:  # exception
        entry = ExceptionEntry(
            id=entry_id,
            timestamp=timestamp,
            category=args.category,
            labels=labels,
            rationale=args.rationale,
            rule_ref=args.rule_ref,
            issue=getattr(args, "issue", "") or "",
            alternatives_rejected=getattr(args, "alternatives_rejected", None),
        )

    add_entry(entry, path=path)
    print(f"Added {entry_type} entry: {entry_id}")
    return 0


def _cmd_outcome(args, path, set_outcome) -> int:
    measured_at = getattr(args, "measured_at", None) or datetime.now(UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    try:
        set_outcome(
            args.id,
            args.result,
            measured_at,
            notes=getattr(args, "notes", None),
            path=path,
            force=getattr(args, "force", False),
        )
    except KeyError:
        print(f"Error: entry {args.id!r} not found", file=sys.stderr)
        return 1
    except TypeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc} (use --force to overwrite)", file=sys.stderr)
        return 1
    print(f"Recorded outcome for {args.id}: {args.result}")
    return 0


def _cmd_sync(path) -> int:
    try:
        from little_loops.decisions_sync import sync_to_local_md

        sync_to_local_md(path=path)
    except ImportError:
        print("sync not yet available (requires FEAT-1895)", file=sys.stderr)
        return 1
    return 0


def _cmd_promote(args, path, load_decisions, save_decisions, RuleEntry, DecisionEntry) -> int:
    entry_id = args.entry_id
    enforcement = getattr(args, "enforcement", "required")

    entries = load_decisions(path)

    target = None
    idx = None
    for i, e in enumerate(entries):
        if e.id == entry_id:
            target = e
            idx = i
            break

    if target is None:
        print(f"Error: entry {entry_id!r} not found", file=sys.stderr)
        return 1

    if not isinstance(target, DecisionEntry):
        print(
            f"Error: entry {entry_id!r} is type {target.type!r}, not 'decision'; cannot promote",
            file=sys.stderr,
        )
        return 1

    rule = RuleEntry(
        id=target.id,
        timestamp=target.timestamp,
        category=target.category,
        labels=list(target.labels),
        rationale=target.rationale,
        rule=target.rule,
        enforcement=enforcement,
        supersedes=None,
        issue=target.issue,
    )

    entries[idx] = rule
    save_decisions(entries, path)

    if enforcement == "required":
        _cmd_sync(path)

    print(f"Promoted {entry_id} → rule (enforcement: {enforcement})")
    return 0

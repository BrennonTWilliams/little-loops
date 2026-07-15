"""ll-issues decisions: Manage rules, decisions, and exceptions log."""

from __future__ import annotations

import argparse
import sys
import uuid
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
    list_p.add_argument(
        "--enforcement",
        choices=["required", "advisory"],
        default=None,
        help="Filter rule/coupling entries by enforcement level (required or advisory)",
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

    # -- suggest-rules --
    suggest_p = subsubs.add_parser(
        "suggest-rules",
        help="Suggest decision entries that are candidates for promotion to rules",
    )
    add_config_arg(suggest_p)

    # -- extract-from-completed --
    extract_p = subsubs.add_parser(
        "extract-from-completed",
        help="Extract decisions and rules from completed issues via LLM",
    )
    extract_p.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        default=None,
        help="Only process issues completed on or after this date",
    )
    extract_p.add_argument(
        "--issue",
        metavar="ID",
        default=None,
        help="Only extract from this specific issue ID (e.g. ENH-2151)",
    )
    extract_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print candidates without writing to decisions.yaml",
    )
    extract_p.add_argument(
        "--min-confidence",
        type=float,
        default=0.7,
        dest="min_confidence",
        metavar="FLOAT",
        help="Minimum LLM confidence to accept a candidate (default: 0.7)",
    )
    add_config_arg(extract_p)

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

    if sub == "suggest-rules":
        return _cmd_suggest_rules(path)

    if sub == "extract-from-completed":
        return _cmd_extract_from_completed(config, args, path)

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

    if getattr(args, "enforcement", None):
        # Only RuleEntry / CouplingEntry carry an enforcement level; entries
        # without one (decisions, exceptions) never match an explicit filter.
        entries = [e for e in entries if getattr(e, "enforcement", None) == args.enforcement]

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

    # Generate an ID if not provided. Use a uuid rather than a "count on disk + 1"
    # counter so two divergent branches never mint the same id (BUG-2642/BUG-2644).
    entry_id = getattr(args, "entry_id", None)
    if not entry_id:
        entry_id = str(uuid.uuid4())

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


def _cmd_suggest_rules(path) -> int:
    """Analyze decision entries and suggest candidates for promotion to rules."""
    import re
    from collections import defaultdict

    from little_loops.decisions import DecisionEntry, list_entries

    all_entries = list_entries(path=path)
    decisions = [e for e in all_entries if isinstance(e, DecisionEntry)]

    if len(decisions) < 3:
        count = len(decisions)
        noun = "entry" if count == 1 else "entries"
        print(f"(only {count} decision {noun} found; need at least 3 to suggest rule candidates)")
        return 1

    # Heuristic: rule texts that are one-off choices rather than general constraints
    _one_off_re = re.compile(r"^(Option [A-C]\b|NO-GO\b|Captured:\s*)", re.IGNORECASE)

    def _is_general_constraint(e: DecisionEntry) -> bool:
        return not _one_off_re.match(e.rule or "")

    def _extract_tokens(text: str) -> set[str]:
        """Extract snake_case and kebab-case identifiers (min 5 chars) and file paths."""
        tokens: set[str] = set()
        for m in re.finditer(r"\b([a-z][a-z0-9]*(?:[_-][a-z0-9]+)+)\b", text):
            t = m.group(1).replace("-", "_")
            if len(t) >= 5:
                tokens.add(t)
        for m in re.finditer(r"([a-z][a-z0-9_/.-]+\.(?:py|yaml|md|json))", text):
            tokens.add(m.group(1))
        return tokens

    by_category: dict[str, list[DecisionEntry]] = defaultdict(list)
    for d in decisions:
        by_category[d.category].append(d)

    clusters: list[tuple[list[DecisionEntry], str, list[str], bool]] = []

    for category in sorted(by_category):
        cat_entries = by_category[category]
        high_signal = len(cat_entries) >= 3
        general = [e for e in cat_entries if _is_general_constraint(e)]

        if not general:
            continue

        if high_signal:
            if len(general) >= 2:
                # Find tokens shared by at least 2 entries in this high-signal category
                tok_freq: dict[str, int] = {}
                for e in general:
                    seen_in_entry: set[str] = set()
                    for t in _extract_tokens((e.rationale or "") + " " + (e.rule or "")):
                        if t not in seen_in_entry:
                            tok_freq[t] = tok_freq.get(t, 0) + 1
                            seen_in_entry.add(t)
                shared = sorted(t for t, c in tok_freq.items() if c >= 2)[:3]
                clusters.append((general, category, shared, True))
            else:
                # Single general constraint in a high-signal category — still worth surfacing
                clusters.append((general, category, [], True))
        else:
            # Low-signal category: only pair entries that share common tokens
            tok: dict[str, set[str]] = {
                e.id: _extract_tokens((e.rationale or "") + " " + (e.rule or "")) for e in general
            }
            used: set[str] = set()
            for i, e1 in enumerate(general):
                if e1.id in used:
                    continue
                group = [e1]
                for e2 in general[i + 1 :]:
                    if e2.id in used:
                        continue
                    if tok[e1.id] & tok[e2.id]:
                        group.append(e2)
                        used.add(e2.id)
                if len(group) >= 2:
                    used.add(e1.id)
                    shared_tokens = tok[e1.id].copy()
                    for e in group[1:]:
                        shared_tokens &= tok[e.id]
                    clusters.append((group, category, sorted(shared_tokens)[:3], False))

    if not clusters:
        print("(no rule candidates found in current decisions log)")
        return 1

    for group, category, shared, high_signal in clusters:
        ids = ", ".join(e.id for e in group)
        ref_str = " and reference " + ", ".join(shared) if shared else ""
        signal_str = " [high-signal]" if high_signal else ""
        best = max(group, key=lambda e: len(e.rule or ""))

        print(f"[SUGGEST]{signal_str} {ids} share category={category}{ref_str}")
        print(f'  — consider promoting to a rule: "{best.rule}"')
        for e in group:
            print(f"    • {e.id}: {e.rule}")
        print()

    return 0


def _is_near_duplicate(rule_text: str, existing_rules: list[str]) -> bool:
    """Return True if rule_text shares ≥60% significant tokens with any existing rule."""
    import re

    def _tokens(text: str) -> set[str]:
        return {w.lower() for w in re.findall(r"\b[a-zA-Z]{4,}\b", text)}

    new_tokens = _tokens(rule_text)
    if not new_tokens:
        return False

    for existing in existing_rules:
        overlap = new_tokens & _tokens(existing)
        if overlap and len(overlap) / len(new_tokens) >= 0.6:
            return True

    return False


_EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule": {"type": "string"},
                    "rationale": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "architecture",
                            "testing",
                            "style",
                            "security",
                            "performance",
                            "other",
                        ],
                    },
                    "confidence": {"type": "number"},
                    "scope": {"type": "string", "enum": ["global", "issue"]},
                },
                "required": ["rule", "rationale", "category", "confidence", "scope"],
            },
        }
    },
    "required": ["candidates"],
}


def _cmd_extract_from_completed(config, args, path) -> int:
    """Extract rules from completed issues via LLM and append to decisions.yaml."""
    import json
    import subprocess
    from datetime import UTC, date, datetime
    from pathlib import Path

    from little_loops.decisions import RuleEntry, add_entry, list_entries
    from little_loops.host_runner import resolve_host
    from little_loops.issue_history.parsing import scan_completed_issues

    project_root = Path(config.project_root)
    issues_dir = project_root / config.issues.base_dir

    since_date_str = getattr(args, "since", None)
    issue_filter = getattr(args, "issue", None)
    dry_run = getattr(args, "dry_run", False)
    min_confidence = float(getattr(args, "min_confidence", 0.7))

    # Filesystem scan always used (body content required for extraction)
    completed = scan_completed_issues(issues_dir)

    if issue_filter:
        completed = [c for c in completed if c.issue_id == issue_filter]

    if since_date_str:
        try:
            cutoff = date.fromisoformat(since_date_str)
        except ValueError:
            print(
                f"Error: invalid --since date {since_date_str!r}; expected YYYY-MM-DD",
                file=sys.stderr,
            )
            return 1
        completed = [c for c in completed if c.completed_date and c.completed_date >= cutoff]

    if not completed:
        print("No completed issues found matching filters.")
        return 0

    # Load existing entries for deduplication
    existing = list_entries(path)
    existing_issue_ids = {e.issue for e in existing if getattr(e, "issue", None)}
    existing_rule_texts = [
        e.rule.lower()  # type: ignore[union-attr]
        for e in existing
        if getattr(e, "rule", None) and isinstance(e.rule, str)  # type: ignore[union-attr]
    ]

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    total_candidates = 0
    total_written = 0
    total_skipped = 0

    for issue in completed:
        # Level-1 dedup: skip if any entry already references this issue
        if issue.issue_id in existing_issue_ids:
            total_skipped += 1
            continue

        if not issue.path or not issue.path.exists():
            continue

        body = issue.path.read_text(encoding="utf-8")

        prompt = (
            f"Issue: {issue.issue_id}\n"
            f"Type: {issue.issue_type}\n"
            f"Body:\n{body[:4000]}\n\n"
            "Extract any decisions, constraints, or rules that should guide future coding agents.\n"
            "Only extract rules general enough to apply to future work (not one-off tactical decisions).\n"
            "For each candidate return:\n"
            "  - rule: imperative sentence, ≤ 120 chars\n"
            "  - rationale: why this rule exists, drawn from the issue context\n"
            "  - category: architecture | testing | style | security | performance | other\n"
            "  - confidence: 0.0–1.0 (how likely this generalizes beyond this one issue)\n"
            "  - scope: global | issue\n"
            "Return an empty candidates array if no generalizable rules can be extracted."
        )

        invocation = resolve_host().build_blocking_json(prompt=prompt, model="sonnet")
        # ENH-2627: only append the inline --json-schema flag (and the claude-only
        # --no-session-persistence) on hosts whose CLI honors it; other hosts get
        # the schema via the prompt text and are parsed leniently below.
        llm_args = list(invocation.args)
        if getattr(invocation.capabilities, "structured_output", False):
            llm_args += [
                "--json-schema",
                json.dumps(_EXTRACTION_SCHEMA),
                "--no-session-persistence",
            ]

        try:
            proc = subprocess.run(
                [invocation.binary, *llm_args],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            print(f"Warning: LLM call timed out for {issue.issue_id}", file=sys.stderr)
            continue
        except FileNotFoundError:
            print(f"Error: host CLI not found ({invocation.binary})", file=sys.stderr)
            return 1

        if proc.returncode != 0:
            print(
                f"Warning: LLM call failed for {issue.issue_id}: {proc.stderr[:200]}",
                file=sys.stderr,
            )
            continue

        # Parse CLI JSON envelope
        candidates: list[dict] = []
        try:
            stdout = proc.stdout.strip()
            try:
                envelope = json.loads(stdout)
            except json.JSONDecodeError:
                lines = [ln for ln in stdout.split("\n") if ln.strip()]
                envelope = json.loads(lines[-1]) if lines else {}

            if envelope.get("subtype") == "error_max_structured_output_retries":
                print(
                    f"Warning: LLM schema retries exhausted for {issue.issue_id}",
                    file=sys.stderr,
                )
                continue

            if isinstance(envelope.get("structured_output"), dict):
                result = envelope["structured_output"]
            else:
                raw = envelope.get("result", "")
                result = json.loads(raw) if isinstance(raw, str) and raw else {}

            candidates = result.get("candidates", [])
        except Exception as exc:
            print(
                f"Warning: failed to parse LLM response for {issue.issue_id}: {exc}",
                file=sys.stderr,
            )
            continue

        total_candidates += len(candidates)

        for candidate in candidates:
            rule_text = (candidate.get("rule") or "").strip()[:120]
            rationale = (candidate.get("rationale") or "").strip()
            category = candidate.get("category") or "other"
            confidence = float(candidate.get("confidence") or 0.0)
            scope = candidate.get("scope") or "issue"

            if not rule_text:
                continue

            if confidence < min_confidence:
                total_skipped += 1
                continue

            # Level-2 dedup: near-duplicate rule text check
            if _is_near_duplicate(rule_text, existing_rule_texts):
                total_skipped += 1
                continue

            # uuid id: avoids cross-branch collisions on a shared count (BUG-2644).
            entry_id = str(uuid.uuid4())

            entry = RuleEntry(
                id=entry_id,
                timestamp=timestamp,
                category=category,
                labels=["extracted", scope],
                rationale=rationale,
                rule=rule_text,
                enforcement="advisory",
                issue=issue.issue_id,
            )

            if dry_run:
                print(
                    f"[DRY-RUN] {entry_id} ({category}, confidence={confidence:.2f}): {rule_text}"
                )
            else:
                add_entry(entry, path)
                existing_rule_texts.append(rule_text.lower())
                total_written += 1

    print(
        f"Extraction complete: {total_candidates} candidates found, "
        f"{total_written} written, {total_skipped} skipped (duplicate/low-confidence)."
    )
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

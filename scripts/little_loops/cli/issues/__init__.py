"""ll-issues: Issue management CLI with sub-commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context


def main_issues() -> int:
    """Entry point for ll-issues command.

    Dispatches to sub-commands for issue management and visualization.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-issues", sys.argv[1:]):
        from little_loops.cli.issues.anchor_sweep import cmd_anchor_sweep
        from little_loops.cli.issues.append_log import cmd_append_log
        from little_loops.cli.issues.check_decidable import cmd_check_decidable
        from little_loops.cli.issues.check_flag import cmd_check_flag
        from little_loops.cli.issues.check_open_questions import (
            add_check_open_questions_parser,
            cmd_check_open_questions,
        )
        from little_loops.cli.issues.check_readiness import cmd_check_readiness
        from little_loops.cli.issues.clusters import cmd_clusters
        from little_loops.cli.issues.count_cmd import cmd_count
        from little_loops.cli.issues.decisions import (
            add_decisions_parser,
            cmd_decisions,
        )
        from little_loops.cli.issues.deferred_triage import (
            add_deferred_triage_parser,
            cmd_deferred_triage,
        )
        from little_loops.cli.issues.epic_consistency import (
            add_epic_consistency_parser,
            cmd_epic_consistency,
        )
        from little_loops.cli.issues.epic_progress import (
            add_epic_progress_parser,
            cmd_epic_progress,
        )
        from little_loops.cli.issues.finalize_decomposition import (
            add_finalize_decomposition_parser,
            cmd_finalize_decomposition,
        )
        from little_loops.cli.issues.fingerprint import cmd_fingerprint
        from little_loops.cli.issues.format_check import (
            add_format_check_parser,
            cmd_format_check,
        )
        from little_loops.cli.issues.impact_effort import cmd_impact_effort
        from little_loops.cli.issues.list_cmd import cmd_list
        from little_loops.cli.issues.next_action import cmd_next_action
        from little_loops.cli.issues.next_id import cmd_next_id
        from little_loops.cli.issues.next_issue import cmd_next_issue
        from little_loops.cli.issues.next_issues import cmd_next_issues
        from little_loops.cli.issues.path_cmd import cmd_path
        from little_loops.cli.issues.refine_status import cmd_refine_status
        from little_loops.cli.issues.search import cmd_search
        from little_loops.cli.issues.sequence import cmd_sequence
        from little_loops.cli.issues.set_scores import cmd_set_scores
        from little_loops.cli.issues.set_status import cmd_set_status
        from little_loops.cli.issues.show import cmd_show
        from little_loops.cli.issues.skip import cmd_skip
        from little_loops.cli_args import VALID_PRIORITIES, add_config_arg, add_skip_arg
        from little_loops.config import BRConfig

        parser = argparse.ArgumentParser(
            prog="ll-issues",
            description="Issue management and visualization utilities",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Sub-commands:
  next-id        Print next globally unique issue number
  list           List active issues with optional filters
  search         Search issues with filters and sorting
  count          Count active issues (total or filtered)
  show           Show summary card for a single issue
  path           Print file path for an issue ID
  sequence       Suggest dependency-ordered implementation sequence
  impact-effort  Display impact vs effort matrix for active issues
  refine-status  Show refinement depth table sorted by commands touched
  append-log     Append a session log entry to an issue file
  next-action    Print the next refinement action for the highest-priority active issue
  next-issue     Print the issue ID ranked highest by outcome confidence and readiness
  next-issues    Print all active issues in ranked order (alias: nxs)
  clusters       Visualize issue dependency clusters as box diagrams
  check-readiness  Exit 0 if an issue meets readiness and outcome thresholds
  check-flag       Exit 0 if a boolean frontmatter field equals 'true'
  check-decidable  Exit 0 if an issue has >=1 enumerable option to decide between
  set-scores       Write confidence and dimension scores to issue frontmatter
  set-status       Transition an issue to a new status value
  skip             Deprioritize an issue by bumping its priority prefix
  anchor-sweep     Rewrite file:line references in active issue files to anchor form
  fingerprint      Extract structured fingerprint (id, files, key_terms) from an issue file
  format-check     Deterministic structural linter for issue formatting (missing/renamed/empty/boilerplate)
  decisions        Manage rules, decisions, and exceptions log (list/add/outcome/generate/sync)

Examples:
  %(prog)s next-id
  %(prog)s list --type FEAT --priority P2
  %(prog)s search "caching" --include-completed
  %(prog)s search --type BUG --priority P0-P2 --sort date
  %(prog)s search --since 2026-01-01 --json
  %(prog)s count
  %(prog)s count --json
  %(prog)s count --type BUG
  %(prog)s show FEAT-518
  %(prog)s path 1009
  %(prog)s path FEAT-1009
  %(prog)s p P3-FEAT-1009
  %(prog)s sequence --limit 10
  %(prog)s impact-effort
  %(prog)s impact-effort --type BUG
  %(prog)s refine-status
  %(prog)s refine-status FEAT-873
  %(prog)s refine-status --type BUG
  %(prog)s refine-status --format json
  %(prog)s refine-status --json
  %(prog)s append-log .issues/bugs/P2-BUG-123-foo.md /ll:refine-issue
  %(prog)s next-issue
  %(prog)s next-issue --json
  %(prog)s next-issue --path
  %(prog)s next-issues
  %(prog)s next-issues 5
  %(prog)s next-issues --json
  %(prog)s nxs --path
  %(prog)s skip FEAT-955
  %(prog)s skip BUG-042 --priority P4 --reason "retry after CI fix"
  %(prog)s clusters
  %(prog)s clusters --json
  %(prog)s clusters --include-orphans
  %(prog)s clusters --min-connections 2
  %(prog)s clusters --cluster 2
  %(prog)s clusters --limit 3 --compact
  %(prog)s anchor-sweep --dry-run
  %(prog)s anchor-sweep --issues-dir .issues
  %(prog)s asw --dry-run
  %(prog)s fingerprint .issues/enhancements/P3-ENH-1801-example.md
  %(prog)s fp .issues/bugs/P2-BUG-042-example.md
  %(prog)s set-scores BUG-1307 --confidence 95 --outcome 80
  %(prog)s set-scores BUG-1307 --confidence 95 --outcome 80 --score-complexity 22 --score-test-coverage 20 --score-ambiguity 25 --score-change-surface 15
  %(prog)s set-status ENH-1725 in_progress
  %(prog)s sst BUG-042 done
""",
        )

        subs = parser.add_subparsers(dest="command", help="Available commands")

        nid = subs.add_parser(
            "next-id", aliases=["ni"], help="Print next globally unique issue number"
        )
        nid.set_defaults(command="next-id")
        add_config_arg(nid)
        from little_loops.cli.issues.next_id import positive_int

        nid.add_argument(
            "--count",
            "-n",
            type=positive_int,
            default=1,
            metavar="N",
            help="Number of consecutive IDs to allocate (default: 1)",
        )

        ls = subs.add_parser("list", aliases=["l"], help="List active issues")
        ls.set_defaults(command="list")
        ls.add_argument(
            "--type", "-T", choices=["BUG", "FEAT", "ENH", "EPIC"], help="Filter by issue type"
        )
        ls.add_argument(
            "--priority",
            "-p",
            metavar="PRIORITY",
            help="Filter by priority level, e.g. P1 or P1,P2",
        )
        ls.add_argument(
            "--status",
            "-S",
            choices=["open", "in_progress", "blocked", "deferred", "done", "cancelled", "all"],
            default="open",
            help="Filter by status (default: open)",
        )
        ls.add_argument(
            "--flat",
            action="store_true",
            help="Output flat list (current format) for scripting compatibility",
        )
        ls.add_argument("--json", "-j", action="store_true", help="Output as JSON array")
        ls.add_argument(
            "--include-summary",
            action="store_true",
            dest="include_summary",
            default=False,
            help="Include ## Summary body in each JSON object (no-op without --json)",
        )
        ls.add_argument(
            "--limit",
            "-n",
            type=int,
            metavar="N",
            default=None,
            help="Cap output at N issues (must be ≥ 1)",
        )
        ls.add_argument(
            "--sort",
            "-s",
            choices=[
                "priority",
                "id",
                "type",
                "title",
                "created",
                "completed",
                "confidence",
                "outcome",
                "refinement",
            ],
            default="priority",
            help="Sort field (default: priority)",
        )
        ls.add_argument("--asc", action="store_true", default=False, help="Sort ascending")
        ls.add_argument("--desc", action="store_true", default=False, help="Sort descending")
        ls.add_argument(
            "--label",
            action="append",
            dest="label",
            metavar="LABEL",
            help="Filter by label (repeatable; matches issues whose labels: frontmatter contains LABEL)",
        )
        ls.add_argument(
            "--milestone",
            dest="milestone",
            metavar="MILESTONE",
            help="Filter by milestone name (matches issues whose milestone: frontmatter equals MILESTONE)",
        )
        ls.add_argument(
            "--parent",
            dest="parent",
            metavar="ISSUE_ID",
            help=(
                "Filter to the full transitive descendant set of a parent issue "
                "(e.g. EPIC-001), including grandchildren nested under intermediate issues"
            ),
        )
        ls.add_argument(
            "--group-by",
            choices=["type", "epic"],
            default="type",
            dest="group_by",
            help="Group output by issue type (default) or parent ID",
        )
        ls.add_argument(
            "--no-truncate",
            action="store_true",
            dest="no_truncate",
            help="Show full untruncated titles (default: truncate to terminal width)",
        )
        add_config_arg(ls)

        sr = subs.add_parser(
            "search", aliases=["sr"], help="Search issues with filters and sorting"
        )
        sr.set_defaults(command="search")
        sr.add_argument(
            "query",
            nargs="?",
            default=None,
            help="Text to match against title and body (case-insensitive)",
        )
        sr.add_argument(
            "--type",
            "-T",
            choices=["BUG", "FEAT", "ENH", "EPIC"],
            action="append",
            dest="type",
            metavar="TYPE",
            help="Filter by issue type: BUG, FEAT, ENH, EPIC (repeatable)",
        )
        sr.add_argument(
            "--priority",
            "-p",
            action="append",
            dest="priority",
            metavar="P",
            help="Filter by priority: P0-P5 or range e.g. P0-P2 (repeatable)",
        )
        sr.add_argument(
            "--status",
            "-S",
            choices=["open", "in_progress", "blocked", "deferred", "done", "cancelled", "all"],
            default="open",
            help="Filter by status (default: open)",
        )
        sr.add_argument(
            "--include-completed",
            action="store_true",
            default=False,
            dest="include_completed",
            help="Include completed issues (alias for --status all)",
        )
        sr.add_argument(
            "--label",
            action="append",
            dest="label",
            metavar="LABEL",
            help="Filter by label tag (repeatable)",
        )
        sr.add_argument("--since", metavar="DATE", help="Only issues on or after DATE (YYYY-MM-DD)")
        sr.add_argument(
            "--until", metavar="DATE", help="Only issues on or before DATE (YYYY-MM-DD)"
        )
        sr.add_argument(
            "--date-field",
            choices=["discovered", "updated"],
            default="discovered",
            dest="date_field",
            help="Date field to filter on (default: discovered)",
        )
        sr.add_argument(
            "--sort",
            "-s",
            choices=[
                "priority",
                "id",
                "date",
                "type",
                "title",
                "created",
                "completed",
                "confidence",
                "outcome",
                "refinement",
            ],
            default="priority",
            help="Sort field (default: priority)",
        )
        sr.add_argument("--asc", action="store_true", default=False, help="Sort ascending")
        sr.add_argument("--desc", action="store_true", default=False, help="Sort descending")
        sr.add_argument("--json", "-j", action="store_true", help="Output as JSON array")
        sr.add_argument(
            "--format",
            "-f",
            choices=["table", "list", "ids"],
            default="table",
            help="Output format: table (default), list, ids",
        )
        sr.add_argument("--limit", "-n", type=int, metavar="N", help="Cap results at N")
        add_config_arg(sr)

        cnt = subs.add_parser("count", aliases=["c"], help="Count active issues")
        cnt.set_defaults(command="count")
        cnt.add_argument(
            "--type", "-T", choices=["BUG", "FEAT", "ENH", "EPIC"], help="Filter by issue type"
        )
        cnt.add_argument(
            "--priority",
            "-p",
            metavar="PRIORITY",
            help="Filter by priority level, e.g. P1 or P1,P2",
        )
        cnt.add_argument(
            "--status",
            "-S",
            choices=["open", "in_progress", "blocked", "deferred", "done", "cancelled", "all"],
            default="open",
            help="Filter by status (default: open)",
        )
        cnt.add_argument("--json", "-j", action="store_true", help="Output as JSON with breakdowns")
        add_config_arg(cnt)

        seq = subs.add_parser(
            "sequence", aliases=["seq"], help="Suggest implementation order based on dependencies"
        )
        seq.set_defaults(command="sequence")
        seq.add_argument(
            "--type", "-T", choices=["BUG", "FEAT", "ENH", "EPIC"], help="Filter by issue type"
        )
        seq.add_argument(
            "--limit",
            "-n",
            type=int,
            default=10,
            help="Maximum number of issues to show (default: 10)",
        )
        seq.add_argument("--json", "-j", action="store_true", help="Output as JSON array")
        add_config_arg(seq)

        show = subs.add_parser("show", aliases=["s"], help="Show summary card for an issue")
        show.set_defaults(command="show")
        show.add_argument("issue_id", help="Issue ID (e.g., 518, FEAT-518, P3-FEAT-518)")
        show.add_argument("--json", "-j", action="store_true", help="Output as JSON")
        add_config_arg(show)

        path_p = subs.add_parser("path", aliases=["p"], help="Print file path for an issue ID")
        path_p.set_defaults(command="path")
        path_p.add_argument("issue_id", help="Issue ID (e.g., 1009, FEAT-1009, P3-FEAT-1009)")
        path_p.add_argument("--json", "-j", action="store_true", help="Output as JSON object")
        add_config_arg(path_p)

        sec_p = subs.add_parser(
            "sections", aliases=["sec"], help="Print section template JSON for an issue type"
        )
        sec_p.set_defaults(command="sections")
        sec_p.add_argument("type", help="Issue type: bug, feat, enh, or epic")
        sec_p.add_argument(
            "--path",
            action="store_true",
            help="Print path to template file instead of JSON content",
        )
        add_config_arg(sec_p)

        ie = subs.add_parser(
            "impact-effort", aliases=["ie"], help="Display impact vs effort matrix"
        )
        ie.set_defaults(command="impact-effort")
        ie.add_argument(
            "--type", "-T", choices=["BUG", "FEAT", "ENH", "EPIC"], help="Filter by issue type"
        )
        ie.add_argument("--json", "-j", action="store_true", help="Output as JSON object")
        add_config_arg(ie)

        cl = subs.add_parser(
            "clusters",
            aliases=["cl"],
            help="Visualize issue dependency clusters as box diagrams",
        )
        cl.set_defaults(command="clusters")
        cl.add_argument(
            "--include-orphans",
            action="store_true",
            default=False,
            dest="include_orphans",
            help="Include 1-issue clusters (isolated issues with no relationships)",
        )
        cl.add_argument(
            "--min-connections",
            type=int,
            default=0,
            metavar="N",
            dest="min_connections",
            help="Only show clusters where at least one issue has N or more connections",
        )
        cl.add_argument(
            "--cluster",
            type=int,
            default=None,
            metavar="N",
            dest="cluster",
            help="Render only the Nth cluster (1-indexed); error if N is out of range",
        )
        cl.add_argument(
            "--limit",
            type=int,
            default=None,
            metavar="N",
            dest="limit",
            help="Render at most N clusters; the footer reports how many were suppressed",
        )
        cl.add_argument(
            "--layout",
            choices=["tree", "list", "boxes"],
            default=None,
            dest="layout",
            help=(
                "Diagram layout: tree (default, indented multi-root dependency tree "
                "with every edge shown), list (one line per issue with edge "
                "annotations), boxes (legacy vertical box-stack). "
                "An explicit --layout overrides --compact."
            ),
        )
        cl.add_argument(
            "--compact",
            "--summary",
            action="store_true",
            default=False,
            dest="compact",
            help="Alias for --layout list (one line per issue with edge annotations)",
        )
        cl.add_argument("--json", "-j", action="store_true", help="Output as JSON array")
        cl.add_argument(
            "--edges",
            default="all",
            metavar="SET",
            help=(
                "Edge types to include. Aliases: all (default, all relationship types), "
                "blocking (blocked_by+blocks only, reproduces legacy behaviour), "
                "hard (blocked_by+blocks+depends_on). "
                "Or a comma-separated list of: blocked_by,blocks,depends_on,relates_to,parent."
            ),
        )
        cl.add_argument(
            "--status",
            default="active",
            metavar="SET",
            help=(
                "Issue statuses to include. Aliases: active (default, open/in_progress/blocked), "
                "+deferred (active + deferred), all (everything except cancelled). "
                "Or a comma-separated list of canonical status values."
            ),
        )
        add_config_arg(cl)

        refine_s = subs.add_parser(
            "refine-status",
            aliases=["rs"],
            help="Show refinement depth table sorted by commands touched",
        )
        refine_s.set_defaults(command="refine-status")
        refine_s.add_argument(
            "--type", "-T", choices=["BUG", "FEAT", "ENH", "EPIC"], help="Filter by issue type"
        )
        refine_s.add_argument(
            "--format",
            "-f",
            choices=["table", "json"],
            default="table",
            help="Output format (default: table)",
        )
        refine_s.add_argument(
            "--no-key",
            action="store_true",
            default=False,
            help="Suppress the Key section below the table",
        )
        refine_s.add_argument(
            "--json",
            "-j",
            action="store_true",
            default=False,
            help="Output as JSON array. Matches ll-issues list --json interface. (--format json outputs NDJSON instead)",
        )
        refine_s.add_argument(
            "issue_id",
            nargs="?",
            metavar="ISSUE-ID",
            default=None,
            help="Filter to a single issue by ID (e.g. FEAT-873, BUG-525)",
        )
        add_config_arg(refine_s)

        al = subs.add_parser(
            "append-log",
            aliases=["al"],
            help="Append a session log entry to an issue file",
        )
        al.set_defaults(command="append-log")
        al.add_argument("issue_path", help="Path to the issue markdown file")
        al.add_argument("log_command", help="Command name (e.g., /ll:refine-issue)")
        add_config_arg(al)

        na = subs.add_parser(
            "next-action",
            aliases=["na"],
            help="Print the next refinement action for the highest-priority active issue",
        )
        na.set_defaults(command="next-action")
        na.add_argument(
            "--refine-cap",
            type=int,
            default=5,
            dest="refine_cap",
            metavar="N",
            help="Max refinements before graduating an issue (default: 5)",
        )
        na.add_argument(
            "--ready-threshold",
            type=int,
            default=85,
            dest="ready_threshold",
            metavar="N",
            help="Minimum confidence_score to pass (default: 85)",
        )
        na.add_argument(
            "--outcome-threshold",
            type=int,
            default=70,
            dest="outcome_threshold",
            metavar="N",
            help="Minimum outcome_confidence to pass (default: 70)",
        )
        add_skip_arg(na)
        add_config_arg(na)

        nx = subs.add_parser(
            "next-issue",
            aliases=["nx"],
            help="Print the issue ranked highest by outcome confidence and readiness",
        )
        nx.set_defaults(command="next-issue")
        nx.add_argument("--json", "-j", action="store_true", help="Output as JSON object")
        nx.add_argument("--path", action="store_true", help="Output only the file path")
        nx.add_argument(
            "--include-blocked",
            action="store_true",
            default=False,
            dest="include_blocked",
            help=(
                "Include issues with unresolved blockers in the ranked output. By "
                "default, blocked issues are filtered out. When set, the JSON "
                "output row carries a `blocked` field (true/false)."
            ),
        )
        add_skip_arg(nx)
        add_config_arg(nx)

        nxs = subs.add_parser(
            "next-issues",
            aliases=["nxs"],
            help="Print all active issues in ranked order",
        )
        nxs.set_defaults(command="next-issues")
        nxs.add_argument(
            "count",
            nargs="?",
            type=int,
            default=None,
            metavar="N",
            help="Cap results at N issues",
        )
        nxs.add_argument("--json", "-j", action="store_true", help="Output as JSON array")
        nxs.add_argument("--path", action="store_true", help="Output one file path per line")
        nxs.add_argument(
            "--include-blocked",
            action="store_true",
            default=False,
            dest="include_blocked",
            help=(
                "Include issues with unresolved blockers in the ranked output. By "
                "default, blocked issues are filtered out. When set, each JSON "
                "output row carries a `blocked` field (true/false)."
            ),
        )
        add_config_arg(nxs)

        cf = subs.add_parser(
            "check-flag",
            aliases=["cf"],
            help="Exit 0 if a boolean frontmatter field equals 'true'",
        )
        cf.set_defaults(command="check-flag")
        cf.add_argument("issue_id", help="Issue ID (e.g., 518, FEAT-518, P3-FEAT-518)")
        cf.add_argument("field", help="Frontmatter field name (e.g., decision_needed)")
        add_config_arg(cf)

        cdec = subs.add_parser(
            "check-decidable",
            help="Exit 0 if an issue has >=1 enumerable option to decide between (ENH-2443)",
        )
        cdec.set_defaults(command="check-decidable")
        cdec.add_argument("issue_id", help="Issue ID (e.g., 518, FEAT-518, P3-FEAT-518)")
        add_config_arg(cdec)

        add_check_open_questions_parser(subs)

        cr = subs.add_parser(
            "check-readiness",
            aliases=["cr"],
            help="Exit 0 if an issue meets readiness and outcome thresholds",
        )
        cr.set_defaults(command="check-readiness")
        cr.add_argument("issue_id", help="Issue ID (e.g., 518, FEAT-518, P3-FEAT-518)")
        cr.add_argument(
            "--readiness",
            type=int,
            default=90,
            metavar="N",
            help="Fallback readiness threshold when not set in ll-config.json (default: 90)",
        )
        cr.add_argument(
            "--outcome",
            type=int,
            default=75,
            metavar="N",
            help="Fallback outcome threshold when not set in ll-config.json (default: 75)",
        )
        add_config_arg(cr)

        ss = subs.add_parser(
            "set-scores",
            aliases=["ss"],
            help="Write confidence and dimension scores to issue frontmatter",
        )
        ss.set_defaults(command="set-scores")
        ss.add_argument("issue_id", help="Issue ID (e.g., 518, FEAT-518, P3-FEAT-518)")
        ss.add_argument(
            "--confidence",
            type=int,
            default=None,
            metavar="N",
            help="Overall readiness score (0–100)",
        )
        ss.add_argument(
            "--outcome",
            type=int,
            default=None,
            metavar="N",
            help="Outcome confidence score (0–100)",
        )
        ss.add_argument(
            "--score-complexity",
            type=int,
            default=None,
            metavar="N",
            dest="score_complexity",
            help="Complexity dimension score (0–25)",
        )
        ss.add_argument(
            "--score-test-coverage",
            type=int,
            default=None,
            metavar="N",
            dest="score_test_coverage",
            help="Test coverage dimension score (0–25)",
        )
        ss.add_argument(
            "--score-ambiguity",
            type=int,
            default=None,
            metavar="N",
            dest="score_ambiguity",
            help="Ambiguity dimension score (0–25)",
        )
        ss.add_argument(
            "--score-change-surface",
            type=int,
            default=None,
            metavar="N",
            dest="score_change_surface",
            help="Change surface dimension score (0–25)",
        )
        add_config_arg(ss)

        sst = subs.add_parser(
            "set-status",
            aliases=["sst"],
            help="Transition an issue to a new status value",
        )
        sst.set_defaults(command="set-status")
        sst.add_argument("issue_id", help="Issue ID (e.g., 518, FEAT-518, P3-FEAT-518)")
        sst.add_argument(
            "status",
            choices=["open", "in_progress", "blocked", "deferred", "done", "cancelled"],
            help="New status value",
        )
        sst.add_argument(
            "--cascade",
            action="store_true",
            default=False,
            dest="cascade",
            help="Propagate status to active children (EPIC closure only)",
        )
        sst.add_argument(
            "--cascade-to",
            choices=["open", "in_progress", "blocked", "deferred", "done", "cancelled"],
            default="deferred",
            dest="cascade_to",
            help="Status to apply to cascaded children (default: deferred)",
        )
        sst.add_argument(
            "--by",
            choices=["human", "automation"],
            default=None,
            dest="by",
            help="Who initiated a deferred transition (default: human)",
        )
        sst.add_argument(
            "--reason",
            choices=["blocked_by_unmet", "remediation_stalled"],
            default=None,
            dest="reason",
            help="Machine-readable reason code for an automation deferral",
        )
        add_config_arg(sst)

        asw = subs.add_parser(
            "anchor-sweep",
            aliases=["asw"],
            help="Rewrite file:line references in active issue files to anchor form",
        )
        asw.set_defaults(command="anchor-sweep")
        asw.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Print changes without modifying files",
        )
        asw.add_argument(
            "--issues-dir",
            default=".issues",
            metavar="DIR",
            dest="issues_dir",
            help="Issues base directory (default: .issues)",
        )
        add_config_arg(asw)

        fp = subs.add_parser(
            "fingerprint",
            aliases=["fp"],
            help="Extract structured fingerprint (id, files, key_terms) from an issue file",
        )
        fp.set_defaults(command="fingerprint")
        fp.add_argument(
            "issue_path", help="Path to the issue file (absolute or relative to project root)"
        )
        add_config_arg(fp)

        sk = subs.add_parser(
            "skip",
            help="Deprioritize an issue by bumping its priority prefix",
        )
        sk.set_defaults(command="skip")
        sk.add_argument("issue_id", help="Issue ID (e.g., 955, FEAT-955, P4-FEAT-955)")
        sk.add_argument(
            "--priority",
            "-p",
            choices=sorted(VALID_PRIORITIES),
            default="P5",
            help="Target priority (default: P5)",
        )
        sk.add_argument("--reason", default=None, help="Reason for skipping (appended to Skip Log)")
        add_config_arg(sk)

        add_finalize_decomposition_parser(subs)
        add_deferred_triage_parser(subs)
        add_epic_progress_parser(subs)
        add_epic_consistency_parser(subs)
        add_format_check_parser(subs)
        add_decisions_parser(subs)

        args = parser.parse_args()

        if not args.command:
            parser.print_help()
            return 1

        project_root = args.config or Path.cwd()
        config = BRConfig(project_root)

        from little_loops.cli.output import configure_output

        configure_output(config.cli)

        if args.command == "next-id":
            return cmd_next_id(config, count=args.count)
        if args.command == "list":
            return cmd_list(config, args)
        if args.command == "search":
            return cmd_search(config, args)
        if args.command == "count":
            return cmd_count(config, args)
        if args.command == "sequence":
            return cmd_sequence(config, args)
        if args.command == "show":
            return cmd_show(config, args)
        if args.command == "path":
            return cmd_path(config, args)
        if args.command == "impact-effort":
            return cmd_impact_effort(config, args)
        if args.command == "clusters":
            return cmd_clusters(config, args)
        if args.command == "refine-status":
            return cmd_refine_status(config, args)
        if args.command == "append-log":
            return cmd_append_log(config, args)
        if args.command == "next-action":
            return cmd_next_action(config, args)
        if args.command == "next-issue":
            return cmd_next_issue(config, args)
        if args.command == "next-issues":
            return cmd_next_issues(config, args)
        if args.command == "check-flag":
            return cmd_check_flag(config, args)
        if args.command == "check-decidable":
            return cmd_check_decidable(config, args)
        if args.command == "check-open-questions":
            return cmd_check_open_questions(config, args)
        if args.command == "check-readiness":
            return cmd_check_readiness(config, args)
        if args.command == "set-scores":
            return cmd_set_scores(config, args)
        if args.command == "set-status":
            return cmd_set_status(config, args)
        if args.command == "anchor-sweep":
            return cmd_anchor_sweep(config, args)
        if args.command == "fingerprint":
            return cmd_fingerprint(config, args)
        if args.command == "skip":
            return cmd_skip(config, args)
        if args.command == "deferred-triage":
            return cmd_deferred_triage(config, args)
        if args.command == "epic-progress":
            return cmd_epic_progress(config, args)
        if args.command == "epic-consistency":
            return cmd_epic_consistency(config, args)
        if args.command == "format-check":
            return cmd_format_check(config, args)
        if args.command == "decisions":
            return cmd_decisions(config, args)
        if args.command == "finalize-decomposition":
            return cmd_finalize_decomposition(config, args)
        if args.command == "sections":
            from little_loops.cli.issues.sections import cmd_sections

            return cmd_sections(config, args)
        return 1

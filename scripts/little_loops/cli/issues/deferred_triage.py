"""ll-issues deferred-triage: cross-run resurfacing report for automation-deferred issues."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config import BRConfig

# remediation_stalled ranks above blocked_by_unmet, above autodev's three
# not-ready codes (ENH-2666), above any other (future/unknown) reason code —
# matches FEAT-2665's acceptance criteria.
_REASON_RANK = {
    "remediation_stalled": 0,
    "blocked_by_unmet": 1,
    "gate_blocked": 2,
    "decision_unresolved": 3,
    # BUG-2734: readiness passed but a Very Large, atomic issue's outcome risk
    # still failed after Pattern-B rescoring — a more actionable, explicit
    # needs-human-decision signal than generic low_readiness.
    "oversized_atomic": 4,
    "low_readiness": 5,
}
_DEFAULT_REASON_RANK = 6


def add_deferred_triage_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the deferred-triage subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "deferred-triage",
        aliases=["dt"],
        help="List automation-deferred issues awaiting human triage (reason + age)",
    )
    p.set_defaults(command="deferred-triage")
    p.add_argument(
        "--format",
        "-f",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    add_config_arg(p)
    return p


def _parse_deferred_date(value: Any, mtime: float | None) -> datetime | None:
    """Parse a ``deferred_date`` frontmatter value, falling back to file mtime.

    Mirrors ``cli/issues/search.py:_parse_discovered_date``'s ISO-Z-strip idiom,
    keyed on ``deferred_date`` instead of ``captured_at``.
    """
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=None)
        except ValueError:
            pass
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if mtime is not None:
        return datetime.fromtimestamp(mtime)
    return None


def _collect_rows(config: BRConfig) -> list[dict[str, Any]]:
    from little_loops.frontmatter import parse_frontmatter
    from little_loops.issue_parser import find_issues

    rows: list[dict[str, Any]] = []
    for info in find_issues(config, status_filter={"deferred"}):
        try:
            content = info.path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = parse_frontmatter(content)
        if fm.get("deferred_by") != "automation":
            continue
        reason = fm.get("deferred_reason") or "(unknown)"
        try:
            mtime = info.path.stat().st_mtime
        except OSError:
            mtime = None
        deferred_at = _parse_deferred_date(fm.get("deferred_date"), mtime)
        age_days = max(0, (datetime.now() - deferred_at).days) if deferred_at is not None else None
        rows.append(
            {
                "issue_id": info.issue_id,
                "title": info.title,
                "deferred_reason": reason,
                "age_days": age_days,
            }
        )

    rows.sort(
        key=lambda r: (
            _REASON_RANK.get(r["deferred_reason"], _DEFAULT_REASON_RANK),
            -(r["age_days"] if r["age_days"] is not None else 0),
        )
    )
    return rows


def cmd_deferred_triage(config: BRConfig, args: argparse.Namespace) -> int:
    """Display automation-deferred issues awaiting human triage.

    Returns:
        0 always — an empty result set is a valid (clean) outcome, not an error.
    """
    from little_loops.cli.output import TYPE_COLOR, colorize, print_json

    rows = _collect_rows(config)
    fmt = getattr(args, "format", "text") or "text"

    if fmt == "json":
        print_json(rows)
        return 0

    if not rows:
        if fmt == "markdown":
            print("## Deferred Triage (automation)\n\nNo automation-deferred issues.")
        else:
            print("No automation-deferred issues awaiting triage.")
        return 0

    if fmt == "markdown":
        lines = [
            "## Deferred Triage (automation)",
            "",
            "| Issue | Reason | Age | Title |",
            "| --- | --- | --- | --- |",
        ]
        for row in rows:
            age_str = f"{row['age_days']}d" if row["age_days"] is not None else "?"
            lines.append(
                f"| {row['issue_id']} | {row['deferred_reason']} | {age_str} | {row['title']} |"
            )
        print("\n".join(lines))
        return 0

    # text format
    print(f"Deferred Triage — {len(rows)} automation-deferred issue(s) awaiting triage")
    for row in rows:
        issue_type = row["issue_id"].split("-", 1)[0]
        colored_id = colorize(row["issue_id"], TYPE_COLOR.get(issue_type, "0"))
        age_str = f"{row['age_days']}d" if row["age_days"] is not None else "?"
        print(f"  {colored_id}  {row['deferred_reason']:<20} {age_str:>5}  {row['title']}")

    return 0

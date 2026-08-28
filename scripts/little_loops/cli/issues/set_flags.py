"""ll-issues set-flags: Write decision/artifact/order/spike flags from confidence-check
findings (ENH-2946).

Ports the phrase-list + numeric-gate rules previously hardcoded in
``skills/confidence-check/SKILL.md`` Phases 4.6/4.7/4.9/4.10 into data
(:data:`FLAG_RULES`), so the phrase lists live in Python instead of prose and
are independently testable and FSM-callable.

Deviations from the original prose spec (documented, not silently dropped):
Phase 4.10's score condition also allowed a Criterion A **Depth** override
(Moderate/Deep), but Depth is never persisted to frontmatter — only the
combined ``score_complexity`` total is written — so there is nothing for a
stateless CLI call to read; this port keeps only the persisted
``score_test_coverage <= 10`` gate. Phase 4.10's "external-API suppression"
(routing to ``/ll:explore-api`` instead of a spike) requires judging whether
a named entity is a third-party package versus project-internal code, which
is exactly the kind of code-reading judgment this issue's Summary says stays
in the skill, not phrase matching — it is intentionally not ported here.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo

_DEFAULT_OUTCOME_THRESHOLD = 75

_DECISION_NEEDED_PHRASES: tuple[str, ...] = (
    "open decision",
    "unresolved decision",
    "resolve before implementing",
    "decision point",
    "either/or",
    "either...or",
    "either…or",
    "resolve before starting",
    "open question",
    "Option A/B",
    "Option A or",
)

_MISSING_ARTIFACTS_PHRASES: tuple[str, ...] = (
    "not yet created",
    "does not exist",
    "needs wiring",
    "missing artifact",
    "absent",
    "unwired component",
)

_IMPLEMENTATION_ORDER_RISK_PHRASES: tuple[str, ...] = (
    "implement tests first",
    "write tests before",
    "test-first",
    "co-deliverable",
    "tests are co-deliverables",
    "implement first so",
)

_SPIKE_NEEDED_PHRASES: tuple[str, ...] = (
    "no precedent",
    "zero precedent",
    "unprecedented",
    "no existing test exercises",
    "untested mechanism",
    "novel mechanism",
    "unproven approach",
    "no test coverage of the",
)


@dataclass(frozen=True)
class FlagRule:
    """One phrase-scan rule, as data — ported from a confidence-check phase.

    Attributes:
        flag: Frontmatter field this rule writes (e.g. ``decision_needed``)
        phrases: Signal phrases; any case-insensitive substring match triggers the rule
        numeric_gate: Optional additional numeric precondition (e.g. spike_needed's
            ``score_test_coverage <= 10``)
        precondition: Optional gate all rules share unless overridden — Phase 4.5 must
            have produced Outcome Risk Factors (``outcome_confidence`` below threshold)
        suppressor: Optional check that blocks the write even when phrases matched
            (missing_artifacts' co-deliverable suppression)
        fires_on_suppression_of: Optional flag name; when that flag was suppressed this
            run, this rule fires even without its own phrase match
            (implementation_order_risk fires because missing_artifacts was suppressed)
        frontmatter_trigger: Optional check against the issue's own parsed frontmatter
            that, when True, makes the rule candidate even without a phrase match and
            bypasses ``numeric_gate`` (direct evidence is stronger than the phrase
            heuristic it stands in for) — ``spike_needed``'s ``unproven_mechanism: true``
            trigger (ENH-3350). ``precondition`` still applies, so suppression via
            ``_spike_not_already_flagged`` is unaffected.
    """

    flag: str
    phrases: tuple[str, ...]
    numeric_gate: Callable[[IssueInfo], bool] | None = None
    precondition: Callable[[IssueInfo], bool] | None = None
    suppressor: Callable[[str, IssueInfo], bool] | None = None
    fires_on_suppression_of: str | None = None
    frontmatter_trigger: Callable[[IssueInfo], bool] | None = None


@dataclass
class FlagResult:
    """Outcome of a single :func:`apply_flags_from_notes` call."""

    id: str
    set_flags: dict[str, bool] = field(default_factory=dict)
    matched_phrases: dict[str, list[str]] = field(default_factory=dict)
    suppressed: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "set_flags": self.set_flags,
            "matched_phrases": self.matched_phrases,
            "suppressed": self.suppressed,
        }


def _outcome_risk_produced_factory(threshold: int) -> Callable[[IssueInfo], bool]:
    def _check(issue: IssueInfo) -> bool:
        return issue.outcome_confidence is not None and issue.outcome_confidence < threshold

    return _check


def _spike_not_already_flagged(issue: IssueInfo) -> bool:
    """Never re-flag a spike already underway or completed (SKILL.md Phase 4.10 skip-if)."""
    from little_loops.frontmatter import parse_frontmatter

    fm = parse_frontmatter(issue.path.read_text(encoding="utf-8"), coerce_types=True)
    return not (fm.get("spike_attempted") or fm.get("spike_completed"))


def _spike_precondition_factory(threshold: int) -> Callable[[IssueInfo], bool]:
    outcome_check = _outcome_risk_produced_factory(threshold)

    def _check(issue: IssueInfo) -> bool:
        return outcome_check(issue) and _spike_not_already_flagged(issue)

    return _check


def _score_test_coverage_gate(issue: IssueInfo) -> bool:
    return issue.score_test_coverage is not None and issue.score_test_coverage <= 10


def _unproven_mechanism_trigger(issue: IssueInfo) -> bool:
    """Direct evidence trigger for spike_needed (ENH-3350).

    A refine-issue-confirmed no-precedent finding is stronger evidence than a
    phrase match, so it bypasses both the phrase list and the
    score_test_coverage numeric gate. ``_spike_not_already_flagged`` (via the
    rule's ``precondition``) still applies.
    """
    return issue.unproven_mechanism is True


def _files_to_create_section(content: str) -> str:
    """Return the body of a ``### Files to Create`` subsection, or "" if absent."""
    import re

    match = re.search(r"^###\s+Files to Create\s*$", content, re.MULTILINE)
    if match is None:
        return ""
    start = match.end()
    next_match = re.search(r"^#{2,3}\s", content[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(content)
    return content[start:end]


_FILE_TOKEN_RE_SOURCE = r"[\w][\w./-]*\.[A-Za-z0-9]+"


def _co_deliverable_suppressor(notes: str, issue: IssueInfo) -> bool:
    """True when a file named in *notes* also appears under ``### Files to Create``.

    Mirrors confidence-check Phase 4.7's co-deliverable check: an absent file
    that this same issue is already going to create is not a missing-artifact
    precondition, just an implementation-order concern (Phase 4.9).
    """
    import re

    content = issue.path.read_text(encoding="utf-8")
    files_section = _files_to_create_section(content)
    if not files_section:
        return False
    candidates = set(re.findall(_FILE_TOKEN_RE_SOURCE, notes))
    return any(candidate in files_section for candidate in candidates)


def _rules_for_threshold(threshold: int) -> tuple[FlagRule, ...]:
    """Build the four rules with *threshold* as the shared outcome-risk precondition.

    Order is significant: ``missing_artifacts`` must evaluate before
    ``implementation_order_risk`` so the latter can see whether the former was
    suppressed this run.
    """
    outcome_precondition = _outcome_risk_produced_factory(threshold)
    return (
        FlagRule(
            flag="decision_needed",
            phrases=_DECISION_NEEDED_PHRASES,
            precondition=outcome_precondition,
        ),
        FlagRule(
            flag="missing_artifacts",
            phrases=_MISSING_ARTIFACTS_PHRASES,
            precondition=outcome_precondition,
            suppressor=_co_deliverable_suppressor,
        ),
        FlagRule(
            flag="implementation_order_risk",
            phrases=_IMPLEMENTATION_ORDER_RISK_PHRASES,
            precondition=outcome_precondition,
            fires_on_suppression_of="missing_artifacts",
        ),
        FlagRule(
            flag="spike_needed",
            phrases=_SPIKE_NEEDED_PHRASES,
            precondition=_spike_precondition_factory(threshold),
            numeric_gate=_score_test_coverage_gate,
            frontmatter_trigger=_unproven_mechanism_trigger,
        ),
    )


FLAG_RULES: tuple[FlagRule, ...] = _rules_for_threshold(_DEFAULT_OUTCOME_THRESHOLD)


def _resolve_outcome_threshold(config: BRConfig) -> int:
    """Read ``commands.confidence_gate.outcome_threshold``, defaulting to 75."""
    import json

    config_path = config.project_root / ".ll" / "ll-config.json"
    try:
        raw = json.loads(config_path.read_text())
        return int(
            raw.get("commands", {})
            .get("confidence_gate", {})
            .get("outcome_threshold", _DEFAULT_OUTCOME_THRESHOLD)
        )
    except Exception:
        return _DEFAULT_OUTCOME_THRESHOLD


def apply_flags_from_notes(
    config: BRConfig, issue_id: str, notes: str | None, dry_run: bool
) -> FlagResult:
    """Scan *notes* for the four flag rules' signal phrases and stamp frontmatter.

    Set-only: a flag already ``true`` is left alone even when this run finds no
    matching phrase — absence is the negative, and clearing a flag stays owned
    by ``/ll:decide-issue`` (Design Decision 3).

    Args:
        config: Project configuration
        issue_id: Issue ID to resolve (e.g., "518", "FEAT-518", "P3-FEAT-518")
        notes: Findings text to scan; when None, reads the issue's own
            ``## Confidence Check Notes`` section
        dry_run: When True, compute the result but do not write frontmatter

    Returns:
        FlagResult describing the post-run flag state, matched phrases, and
        any suppressions

    Raises:
        ValueError: issue_id does not resolve to an issue file
    """
    from little_loops.cli.issues.show import _resolve_issue_id
    from little_loops.frontmatter import parse_frontmatter, update_frontmatter
    from little_loops.issue_parser import IssueParser, _section_body

    path = _resolve_issue_id(config, issue_id)
    if path is None:
        raise ValueError(f"Issue '{issue_id}' not found.")

    content = path.read_text(encoding="utf-8")
    issue = IssueParser(config).parse_file(path)

    if notes is None:
        notes = _section_body(content, "Confidence Check Notes") or ""

    threshold = _resolve_outcome_threshold(config)
    rules = (
        FLAG_RULES if threshold == _DEFAULT_OUTCOME_THRESHOLD else _rules_for_threshold(threshold)
    )

    existing_fm = parse_frontmatter(content, coerce_types=True)
    lowered = notes.lower()

    matched_phrases: dict[str, list[str]] = {}
    suppressed: dict[str, str] = {}
    fired: dict[str, bool] = {}

    for rule in rules:
        matches = [phrase for phrase in rule.phrases if phrase.lower() in lowered]
        matched_phrases[rule.flag] = matches

        frontmatter_triggered = bool(rule.frontmatter_trigger and rule.frontmatter_trigger(issue))

        candidate = bool(matches) or frontmatter_triggered
        if not candidate and rule.fires_on_suppression_of is not None:
            candidate = rule.fires_on_suppression_of in suppressed

        if not candidate:
            fired[rule.flag] = False
            continue

        if rule.precondition is not None and not rule.precondition(issue):
            fired[rule.flag] = False
            continue

        if (
            not frontmatter_triggered
            and rule.numeric_gate is not None
            and not rule.numeric_gate(issue)
        ):
            fired[rule.flag] = False
            continue

        if matches and rule.suppressor is not None and rule.suppressor(notes, issue):
            suppressed[rule.flag] = "co-deliverable listed under ### Files to Create"
            fired[rule.flag] = False
            continue

        fired[rule.flag] = True

    set_flags: dict[str, bool] = {}
    updates: dict[str, bool] = {}
    for rule in rules:
        already_true = str(existing_fm.get(rule.flag)).lower() == "true"
        set_flags[rule.flag] = already_true or fired[rule.flag]
        if fired[rule.flag] and not already_true:
            updates[rule.flag] = True

    if updates and not dry_run:
        new_content = update_frontmatter(content, updates)
        path.write_text(new_content, encoding="utf-8")

    return FlagResult(
        id=issue.issue_id,
        set_flags=set_flags,
        matched_phrases=matched_phrases,
        suppressed=suppressed,
    )


def add_set_flags_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the set-flags subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "set-flags",
        help="Write decision_needed/missing_artifacts/implementation_order_risk/"
        "spike_needed flags from confidence-check findings (ENH-2946)",
    )
    p.set_defaults(command="set-flags")
    p.add_argument("issue_id", help="Issue ID (e.g., 518, FEAT-518, P3-FEAT-518)")
    p.add_argument(
        "--from-notes",
        metavar="FILE",
        default=None,
        help="Path to findings text to scan, or '-' for stdin; omit to read the "
        "issue's own '## Confidence Check Notes' section",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Report what would be set without writing"
    )
    p.add_argument("--json", "-j", action="store_true", help="Output as JSON object")
    add_config_arg(p)
    return p


def cmd_set_flags(config: BRConfig, args: argparse.Namespace) -> int:
    """Run :func:`apply_flags_from_notes` for the CLI and print its result.

    Returns:
        0 on success (including "no flags matched"), 1 if the issue or notes
        file is not found
    """
    from little_loops.cli.output import print_json

    notes_arg = getattr(args, "from_notes", None)
    notes: str | None = None
    if notes_arg == "-":
        notes = sys.stdin.read()
    elif notes_arg is not None:
        from pathlib import Path

        notes_path = Path(notes_arg)
        if not notes_path.exists():
            print(f"Error: notes file '{notes_arg}' not found.", file=sys.stderr)
            return 1
        notes = notes_path.read_text(encoding="utf-8")

    try:
        result = apply_flags_from_notes(
            config, args.issue_id, notes, dry_run=getattr(args, "dry_run", False)
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print_json(result.to_dict())
        return 0

    label = "Would set" if getattr(args, "dry_run", False) else "Set"
    any_output = False
    for flag_name, value in result.set_flags.items():
        if not value:
            continue
        any_output = True
        phrases = result.matched_phrases.get(flag_name) or []
        reason = f" (matched: {', '.join(phrases)})" if phrases else " (already set)"
        print(f"{label} {flag_name}: true{reason}")
    for flag_name, reason in result.suppressed.items():
        any_output = True
        print(f"Suppressed {flag_name}: {reason}")
    if not any_output:
        print(f"No flags matched for {result.id}")
    return 0

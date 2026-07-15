"""ll-issues show: Display summary card for a single issue."""

from __future__ import annotations

import argparse
import re
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.cli.output import (
    PRIORITY_COLOR,
    TYPE_COLOR,
    colorize,
    print_json,
    strip_ansi,
    terminal_width,
)

if TYPE_CHECKING:
    from little_loops.config import BRConfig


_SHOW_CMD_ALIASES: dict[str, str] = {
    "/ll:capture-issue": "capture",
    "/ll:scan-codebase": "scan",
    "/ll:audit-architecture": "audit",
    "/ll:format-issue": "format",
}


def _source_label(discovered_by: str | None) -> str:
    """Return a short display label for the discovered_by frontmatter field."""
    if not discovered_by:
        return "\u2014"
    return _SHOW_CMD_ALIASES.get(discovered_by, discovered_by[:7])


def _resolve_issue_id(config: BRConfig, user_input: str) -> Path | None:
    """Resolve user input to an issue file path.

    Accepts three input formats:
    - Numeric ID only: "518"
    - Type + ID: "FEAT-518"
    - Priority + Type + ID: "P3-FEAT-518"

    Searches the type-scoped category directories. Status (open/done/deferred)
    lives in frontmatter, so active and inactive issues alike resolve here.

    Issue numbers are globally unique across types (see ``get_next_issue_number``),
    so a numeric match is unambiguous. The type prefix and priority are therefore
    treated as **advisory**: an exact match is preferred, but a stale or mismatched
    prefix (e.g. ``FEAT-1903`` for a file now named ``ENH-1903``) still resolves to
    the one file bearing that number rather than reporting "not found" (BUG-2003).

    Args:
        config: Project configuration
        user_input: Issue ID string in any supported format

    Returns:
        Path to the matched issue file, or None if not found
    """
    user_input = user_input.strip()

    # Parse input to extract components
    numeric_id: str | None = None
    type_prefix: str | None = None
    priority: str | None = None

    # Try P-TYPE-NNN format (e.g., P3-FEAT-518)
    m = re.match(r"^(P\d)-(BUG|FEAT|ENH|EPIC)-(\d+)$", user_input, re.IGNORECASE)
    if m:
        priority = m.group(1).upper()
        type_prefix = m.group(2).upper()
        numeric_id = m.group(3)
    else:
        # Try TYPE-NNN format (e.g., FEAT-518)
        m = re.match(r"^(BUG|FEAT|ENH|EPIC)-(\d+)$", user_input, re.IGNORECASE)
        if m:
            type_prefix = m.group(1).upper()
            numeric_id = m.group(2)
        else:
            # Try numeric only (e.g., 518)
            m = re.match(r"^(\d+)$", user_input)
            if m:
                numeric_id = m.group(1)

    if numeric_id is None:
        return None

    # Build search directories: type-scoped dirs only
    search_dirs: list[Path] = []
    for category in config.issue_categories:
        search_dirs.append(config.get_issue_dir(category))

    # Collect every file matching the numeric ID. Because numbers are globally
    # unique, this is normally a single candidate; the prefix/priority hints only
    # disambiguate the rare artificial case of two files sharing a number.
    candidates: list[Path] = []
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        candidates.extend(sorted(search_dir.glob(f"*-{numeric_id}-*.md")))

    if not candidates:
        return None

    def _matches_type(path: Path) -> bool:
        upper = path.name.upper()
        return f"-{type_prefix}-" in upper or upper.startswith(f"{type_prefix}-")

    # Prefer an exact-type match; fall back to the unambiguous numeric match when
    # the caller's type prefix is stale or mismatched (advisory, not required).
    pool = [p for p in candidates if _matches_type(p)] if type_prefix else candidates
    if not pool:
        pool = candidates

    # Within the chosen pool, prefer an exact priority match if one exists.
    if priority:
        prioritized = [p for p in pool if p.name.upper().startswith(f"{priority}-")]
        if prioritized:
            return prioritized[0]

    return pool[0]


def _parse_card_fields(path: Path, config: BRConfig) -> dict[str, str | None]:
    """Parse issue file to extract summary card fields.

    Args:
        path: Path to the issue file
        config: Project configuration (used for relative path computation)

    Returns:
        Dictionary of card fields
    """
    from little_loops.frontmatter import parse_frontmatter

    content = path.read_text()
    frontmatter = parse_frontmatter(content, coerce_types=True)
    filename = path.name

    # Extract priority from filename (e.g., P3-FEAT-518-...)
    priority_match = re.match(r"^(P\d)-", filename)
    priority = priority_match.group(1) if priority_match else None

    # Extract type and ID from filename (e.g., FEAT-518)
    type_id_match = re.search(r"(BUG|FEAT|ENH|EPIC)-(\d+)", filename)
    issue_id = f"{type_id_match.group(1)}-{type_id_match.group(2)}" if type_id_match else None

    # Extract title from content
    title: str | None = None
    title_match = re.search(r"^#\s+[\w-]+:\s*(.+)$", content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        header_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if header_match:
            title = header_match.group(1).strip()
        else:
            title = path.stem

    # Determine status from frontmatter field
    raw_status = frontmatter.get("status", "open")
    _STATUS_DISPLAY = {
        "done": "Completed",
        "cancelled": "Cancelled",
        "deferred": "Deferred",
        "in_progress": "In Progress",
        "blocked": "Blocked",
        "open": "Open",
    }
    status = _STATUS_DISPLAY.get(str(raw_status), str(raw_status).replace("_", " ").title())

    # Extract optional frontmatter fields
    confidence = frontmatter.get("confidence_score")
    outcome = frontmatter.get("outcome_confidence")
    score_complexity = frontmatter.get("score_complexity")
    score_test_coverage = frontmatter.get("score_test_coverage")
    score_ambiguity = frontmatter.get("score_ambiguity")
    score_change_surface = frontmatter.get("score_change_surface")
    effort = frontmatter.get("effort")
    discovered_by = frontmatter.get("discovered_by")
    captured_at = frontmatter.get("captured_at")
    completed_at = frontmatter.get("completed_at")
    decision_needed_raw = frontmatter.get("decision_needed")
    missing_artifacts_raw = frontmatter.get("missing_artifacts")
    # ENH-2640: spike-remediation flags read by autodev's check_spike_needed
    # (spike_needed set by /ll:confidence-check Phase 4.10; spike_attempted/
    # spike_completed written by /ll:spike). Surfaced as lowercased boolean
    # strings via `show --json`, mirroring the decision_needed pattern.
    spike_needed_raw = frontmatter.get("spike_needed")
    spike_attempted_raw = frontmatter.get("spike_attempted")
    spike_completed_raw = frontmatter.get("spike_completed")
    implementation_order_risk_raw = frontmatter.get("implementation_order_risk")
    learning_tests_raw = frontmatter.get("learning_tests_required")

    # Closure context (ENH-2535) — surfaced only when status is terminal-non-open.
    closing_note = frontmatter.get("closing_note")
    closed_reason = frontmatter.get("closed_reason")
    cancelled_reason = frontmatter.get("cancelled_reason")
    deferred_reason = frontmatter.get("deferred_reason")
    closed_by = frontmatter.get("closed_by")
    closed_at = frontmatter.get("closed_at")
    deferred_date = frontmatter.get("deferred_date")

    # Discovery (ENH-2535) — when / where this issue was first observed.
    discovered_date = frontmatter.get("discovered_date")
    discovered_commit = frontmatter.get("discovered_commit")
    discovered_branch = frontmatter.get("discovered_branch")
    discovered_source = frontmatter.get("discovered_source")
    discovered_external_repo = frontmatter.get("discovered_external_repo")

    # Decision coupling (ENH-2535) — actionable pointer when decision_needed: true.
    decision_ref = frontmatter.get("decision_ref")

    # Relationships (ENH-2535) — edges in the issue graph.
    parent_raw = frontmatter.get("parent")
    relates_to_raw = frontmatter.get("relates_to")
    depends_on_raw = frontmatter.get("depends_on")
    blocked_by_raw = frontmatter.get("blocked_by")
    blocks_raw = frontmatter.get("blocks")
    supersedes_raw = frontmatter.get("supersedes")
    decomposed_into_raw = frontmatter.get("decomposed_into")

    # Misc frontmatter (ENH-2535) — affects / focus_area surfaced when set.
    affects_raw = frontmatter.get("affects")
    focus_area_raw = frontmatter.get("focus_area")
    testable_raw = frontmatter.get("testable")

    # Source / norm / fmt fields
    from little_loops.issue_parser import is_formatted, is_normalized

    source = _source_label(discovered_by)
    norm = "\u2713" if is_normalized(path.name) else "\u2717"
    fmt = "\u2713" if is_formatted(path) else "\u2717"

    # --- New fields ---

    # Summary: full first paragraph from ## Summary section
    summary: str | None = None
    summary_match = re.search(
        r"^## Summary\s*\n+(.*?)(?:\n\n|\n##|\Z)", content, re.MULTILINE | re.DOTALL
    )
    if summary_match:
        text = summary_match.group(1).strip()
        if text:
            summary = text

    # Integration file count: count items under ### Files to Modify
    integration_files: int | None = None
    ftm_match = re.search(r"^### Files to Modify\s*$", content, re.MULTILINE)
    if ftm_match:
        start = ftm_match.end()
        next_header = re.search(r"^#{2,3}\s+", content[start:], re.MULTILINE)
        section = content[start : start + next_header.start()] if next_header else content[start:]
        count = len(re.findall(r"^- .+", section, re.MULTILINE))
        if count > 0:
            integration_files = count

    # Risk: extract from ## Impact section
    risk: str | None = None
    risk_match = re.search(r"\*\*Risk\*\*:\s*(Low|Medium|High)", content, re.IGNORECASE)
    if risk_match:
        risk = risk_match.group(1).capitalize()

    # Labels: prefer frontmatter labels: field; fall back to ## Labels body section
    labels: str | None = None
    fm_labels_raw = frontmatter.get("labels")
    if fm_labels_raw:
        if isinstance(fm_labels_raw, list):
            fm_label_list = [str(lb) for lb in fm_labels_raw if lb]
        else:
            fm_label_list = [lb.strip() for lb in str(fm_labels_raw).split(",") if lb.strip()]
        if fm_label_list:
            labels = ", ".join(fm_label_list)
    if not labels:
        labels_match = re.search(
            r"^## Labels\s*\n+(.*?)(?:\n\n|\n##|\Z)", content, re.MULTILINE | re.DOTALL
        )
        if labels_match:
            found = re.findall(r"`([^`]+)`", labels_match.group(1))
            if found:
                labels = ", ".join(found)

    # Session log: parse ## Session Log for unique /ll:* commands with counts
    history: str | None = None
    from little_loops.session_log import count_session_commands, parse_session_log

    distinct = parse_session_log(content)
    if distinct:
        counts = count_session_commands(content)
        parts = [f"{cmd} ({counts[cmd]})" if counts.get(cmd, 1) > 1 else cmd for cmd in distinct]
        history = ", ".join(parts)

    # Relative path
    try:
        rel_path = str(path.relative_to(config.project_root))
    except ValueError:
        rel_path = str(path)

    # List-or-string normalization helper for relationship frontmatter (ENH-2535).
    # Accepts a YAML list, a quoted comma-string, or a bare scalar; returns a
    # comma-joined string of the trimmed IDs or None when empty.
    def _join_ids(raw: object) -> str | None:
        if not raw:
            return None
        if isinstance(raw, list):
            items = [str(t).strip() for t in raw if str(t).strip()]
        else:
            items = [t.strip() for t in str(raw).strip("\"'").split(",") if t.strip()]
        return ", ".join(items) if items else None

    # Resolve parent title for parent display (ENH-2535).
    # Reads all issues via the IssueInfo index for cheap title lookup; falls
    # back to ID-only when the parent EPIC isn't found in the project.
    parent_str: str | None = None
    if parent_raw is not None:
        ps = str(parent_raw).strip()
        if ps:
            parent_str = ps
    parent_display: str | None = None
    if parent_str:
        try:
            from little_loops.issue_parser import find_issues

            _all = find_issues(config)
            _title = next((i.title for i in _all if i.issue_id == parent_str), None)
            parent_display = f"{parent_str} ({_title})" if _title else parent_str
        except Exception:
            parent_display = parent_str

    # Closure: prefer per-status reason field (closing_note / closed_reason /
    # cancelled_reason / deferred_reason) and emit the right label.
    closure_text: str | None = closing_note or closed_reason or cancelled_reason or deferred_reason

    return {
        "issue_id": issue_id,
        "title": title,
        "priority": priority,
        "status": status,
        "raw_status": str(raw_status).lower(),
        "effort": str(effort) if effort is not None else None,
        "confidence": str(confidence) if confidence is not None else None,
        "outcome": str(outcome) if outcome is not None else None,
        "score_complexity": str(score_complexity) if score_complexity is not None else None,
        "score_test_coverage": str(score_test_coverage)
        if score_test_coverage is not None
        else None,
        "score_ambiguity": str(score_ambiguity) if score_ambiguity is not None else None,
        "score_change_surface": str(score_change_surface)
        if score_change_surface is not None
        else None,
        "summary": summary,
        "integration_files": str(integration_files) if integration_files is not None else None,
        "risk": risk,
        "labels": labels,
        "milestone": frontmatter.get("milestone") or None,
        "history": history,
        "path": rel_path,
        "source": source,
        "norm": norm,
        "fmt": fmt,
        "captured_at": str(captured_at) if captured_at is not None else None,
        "completed_at": str(completed_at) if completed_at is not None else None,
        "decision_needed": str(decision_needed_raw).lower()
        if decision_needed_raw is not None
        else None,
        "missing_artifacts": _join_ids(missing_artifacts_raw)
        if isinstance(missing_artifacts_raw, list)
        else (str(missing_artifacts_raw).lower() if missing_artifacts_raw is not None else None),
        "implementation_order_risk": str(implementation_order_risk_raw).lower()
        if implementation_order_risk_raw is not None
        else None,
        # ENH-2640: spike-remediation flags for autodev check_spike_needed
        "spike_needed": str(spike_needed_raw).lower()
        if spike_needed_raw is not None
        else None,
        "spike_attempted": str(spike_attempted_raw).lower()
        if spike_attempted_raw is not None
        else None,
        "spike_completed": str(spike_completed_raw).lower()
        if spike_completed_raw is not None
        else None,
        "learning_tests_required": ", ".join(str(t) for t in learning_tests_raw)
        if learning_tests_raw
        else None,
        # ENH-2535: closure context
        "closing_note": str(closing_note) if closing_note is not None else None,
        "closed_reason": str(closed_reason) if closed_reason is not None else None,
        "cancelled_reason": str(cancelled_reason) if cancelled_reason is not None else None,
        "deferred_reason": str(deferred_reason) if deferred_reason is not None else None,
        "closed_by": str(closed_by) if closed_by is not None else None,
        "closed_at": str(closed_at) if closed_at is not None else None,
        "deferred_date": str(deferred_date) if deferred_date is not None else None,
        "closure_text": closure_text,
        # ENH-2535: discovery
        "discovered_date": str(discovered_date) if discovered_date is not None else None,
        "discovered_commit": str(discovered_commit) if discovered_commit is not None else None,
        "discovered_branch": str(discovered_branch) if discovered_branch is not None else None,
        "discovered_source": str(discovered_source) if discovered_source is not None else None,
        "discovered_external_repo": (
            str(discovered_external_repo) if discovered_external_repo is not None else None
        ),
        # ENH-2535: decision coupling
        "decision_ref": str(decision_ref) if decision_ref is not None else None,
        # ENH-2535: relationships
        "parent": parent_str,
        "parent_display": parent_display,
        "relates_to": _join_ids(relates_to_raw),
        "depends_on": _join_ids(depends_on_raw),
        "blocked_by": _join_ids(blocked_by_raw),
        "blocks": _join_ids(blocks_raw),
        "supersedes": _join_ids(supersedes_raw),
        "decomposed_into": _join_ids(decomposed_into_raw),
        # ENH-2535: misc
        "affects": _join_ids(affects_raw),
        "focus_area": str(focus_area_raw) if focus_area_raw is not None else None,
        "testable": str(testable_raw).lower() if testable_raw is not None else None,
    }


def _ljust(text: str, width: int) -> str:
    """Left-justify text accounting for invisible ANSI escape codes."""
    pad = max(0, width - len(strip_ansi(text)))
    return text + " " * pad


def _dim(text: str) -> str:
    """Wrap *text* in the dim SGR code (ENH-2574 item 3: label hierarchy)."""
    return colorize(text, "2")


def _date_only(value: str) -> str:
    """Strip a trailing ISO time component, returning just the date portion.

    ``"2026-07-01T00:00:00Z"`` -> ``"2026-07-01"``; already-bare dates pass
    through unchanged (ENH-2574 item 5).
    """
    return value.split("T", 1)[0]


def _truncate_to_width(text: str, width: int) -> str:
    """Truncate (optionally ANSI-colored) *text* to *width* visible chars,
    appending an ellipsis when clipped (ENH-2574 item 7 — guards unbreakable
    tokens from bleeding past the card's right border). Visible width is
    measured with ANSI codes stripped; a line that must be clipped loses its
    color codes (a rare fallback — most lines never hit this path)."""
    plain = strip_ansi(text)
    if width <= 0:
        return ""
    if len(plain) <= width:
        return text
    if width == 1:
        return plain[:1]
    return plain[: width - 1] + "…"


def _fit(text: str, width: int) -> str:
    """Truncate then left-pad *text* to exactly *width* visible chars."""
    return _ljust(_truncate_to_width(text, width), width)


# ENH-2574 item 3: status color palette. "Completed" already handled
# separately (kept for backward compat with the pre-existing green code path).
_STATUS_COLOR: dict[str, str] = {
    "Completed": "32",
    "In Progress": "33",
    "Blocked": "31",
    "Deferred": "2",
    "Cancelled": "2",
}


# Closure context rendering (ENH-2535) — only emits when status is terminal-non-open
# AND at least one closure field is populated. Returns the rendered "Key: value"
# lines to append to detail_lines.
_TERMINAL_STATUSES = {"done", "cancelled", "deferred", "closed"}


def _render_closure_block(fields: dict[str, str | None], raw_status: str) -> list[tuple[str, str]]:
    """Render closure-context rows for terminal statuses (ENH-2535).

    Args:
        fields: Card fields dict from `_parse_card_fields`.
        raw_status: Raw status string from frontmatter (lowercased). When not a
            canonical raw value, the helper falls back to the display `status`
            field so callers passing only the display form (e.g., test fixtures
            that skip extraction) still get closure rendering.

    Returns:
        List of (label, value) rows to append, or empty list when status is
        not terminal or no closure fields are populated.
    """
    rs = str(raw_status).lower() if raw_status else ""
    if rs not in _TERMINAL_STATUSES:
        # Fallback: derive from display status (Completed / Cancelled / Deferred).
        ds = (fields.get("status") or "").lower()
        if ds in ("completed", "cancelled", "deferred"):
            rs = "done" if ds == "completed" else ds
        else:
            return []
    out: list[tuple[str, str]] = []
    # Order: reason text first, then attribution, then timing.
    if fields.get("closure_text"):
        if rs == "cancelled":
            label = "Cancellation reason"
        elif rs == "deferred":
            label = "Deferral reason"
        else:  # done / closed
            label = "Closing note"
        out.append((label, str(fields["closure_text"])))
    if fields.get("closed_by"):
        out.append(("Closed by", str(fields["closed_by"])))
    if fields.get("closed_at"):
        out.append(("Closed at", _date_only(str(fields["closed_at"]))))
    if fields.get("deferred_date"):
        out.append(("Deferred at", _date_only(str(fields["deferred_date"]))))
    return out


# Discovery rendering (ENH-2535) — emits when any discovery field is set.
def _render_discovery_block(fields: dict[str, str | None]) -> list[tuple[str, str]]:
    """Render discovery-context rows (when / where the issue was first observed)."""
    out: list[tuple[str, str]] = []
    if fields.get("discovered_date"):
        out.append(("Discovered", str(fields["discovered_date"])))
    if fields.get("discovered_commit"):
        sha = str(fields["discovered_commit"])
        # Short-SHA rendering: 7 chars max to avoid right-border bleed
        # (mirrors the long-unbreakable-word guard at show.py:301-313).
        short_sha = sha[:7] if len(sha) > 7 else sha
        out.append(("Discovered commit", short_sha))
    if fields.get("discovered_branch"):
        out.append(("Discovered branch", str(fields["discovered_branch"])))
    if fields.get("discovered_source"):
        out.append(("Discovered source", str(fields["discovered_source"])))
    if fields.get("discovered_external_repo"):
        out.append(("Upstream", str(fields["discovered_external_repo"])))
    return out


# Relationships rendering (ENH-2535) — emits when any relationship edge is set.
_RELATIONSHIP_KEYS: tuple[tuple[str, str], ...] = (
    ("parent_display", "Parent"),
    ("blocks", "Blocks"),
    ("blocked_by", "Blocked by"),
    ("depends_on", "Depends on"),
    ("relates_to", "Relates to"),
    ("supersedes", "Supersedes"),
    ("decomposed_into", "Decomposed into"),
    ("affects", "Affects"),
    ("focus_area", "Focus area"),
)


def _render_relationships_block(fields: dict[str, str | None]) -> list[tuple[str, str]]:
    """Render relationship edges as a list of (label, value) rows (ENH-2535)."""
    out: list[tuple[str, str]] = []
    for key, label in _RELATIONSHIP_KEYS:
        val = fields.get(key)
        if val:
            out.append((label, str(val)))
    return out


# Decision coupling rendering (ENH-2535) — emits a coupled decision line.
def _render_decision_line(fields: dict[str, str | None]) -> str | None:
    """Render the decision-needed/decision-ref line in the coupled form."""
    needed = (fields.get("decision_needed") or "").lower()
    ref = fields.get("decision_ref")
    if needed == "true" and ref:
        return f"Decision needed → {ref}"
    if needed == "true":
        return "Decision needed: yes"
    if needed == "false":
        return "Decision needed: no"
    if ref:
        return f"Decision ref: {ref}"
    return None


def _render_card(fields: dict[str, str | None]) -> str:
    """Render a summary card using box-drawing characters.

    Args:
        fields: Dictionary of card fields from _parse_card_fields

    Returns:
        Formatted card string
    """
    # Box-drawing characters
    h = "\u2500"  # ─
    v = "\u2502"  # │
    tl = "\u250c"  # ┌
    tr = "\u2510"  # ┐
    bl = "\u2514"  # └
    br = "\u2518"  # ┘
    ml = "\u251c"  # ├
    mr = "\u2524"  # ┤

    issue_id = fields.get("issue_id") or "???"
    title = fields.get("title") or "Untitled"
    header = f"{issue_id}: {title}"

    # Inter-field separator: a middot rather than the border glyph, so intra-row
    # dividers don't read as accidental column lines (ENH-2574 item 4).
    sep = " · "

    # Build metadata line (plain, for width calculation)
    priority = fields.get("priority")
    status = fields.get("status")
    effort = fields.get("effort")
    risk = fields.get("risk")

    meta_parts: list[str] = []
    if priority:
        meta_parts.append(f"Priority: {priority}")
    if status:
        meta_parts.append(f"Status: {status}")
    if effort:
        meta_parts.append(f"Effort: {effort}")
    if risk:
        meta_parts.append(f"Risk: {risk}")
    meta_line = sep.join(meta_parts)

    # Build scores line (only if at least one score present)
    score_parts: list[str] = []
    if fields.get("confidence"):
        score_parts.append(f"Confidence: {fields['confidence']}")
    if fields.get("outcome"):
        score_parts.append(f"Outcome: {fields['outcome']}")
    scores_line = sep.join(score_parts) if score_parts else None

    # Build dimension scores line (only if at least one dimension score present)
    dim_parts: list[str] = []
    if fields.get("score_complexity"):
        dim_parts.append(f"Cmplx: {fields['score_complexity']}")
    if fields.get("score_test_coverage"):
        dim_parts.append(f"Tcov: {fields['score_test_coverage']}")
    if fields.get("score_ambiguity"):
        dim_parts.append(f"Ambig: {fields['score_ambiguity']}")
    if fields.get("score_change_surface"):
        dim_parts.append(f"Chsrf: {fields['score_change_surface']}")
    dim_scores_line = sep.join(dim_parts) if dim_parts else None

    # Build detail lines (source, integration+labels, then column-aligned rows)
    detail_lines: list[str] = []

    # ENH-2574 item 5: "Source: manual" is the default case and is low-signal;
    # hide it. Norm/Fmt collapse to a single actionable "Needs: formatting"
    # row, emitted only when formatting is actually missing.
    source_val = fields.get("source")
    if source_val and source_val not in ("—", "manual"):
        detail_lines.append(f"{_dim('Source:')} {source_val}")
    if fields.get("fmt") == "✗":
        detail_lines.append(f"{_dim('Needs:')} formatting")

    detail_mid_parts: list[str] = []
    if fields.get("integration_files"):
        detail_mid_parts.append(f"Integration: {fields['integration_files']} files")
    if fields.get("labels"):
        detail_mid_parts.append(f"Labels: {fields['labels']}")
    if fields.get("milestone"):
        detail_mid_parts.append(f"Milestone: {fields['milestone']}")
    if detail_mid_parts:
        detail_lines.append(sep.join(detail_mid_parts))

    # ENH-2574 item 6: column-aligned "Key: value" rows -- relationships,
    # capture/discovery/completion timestamps, history, closure context. Keys
    # are right-padded once there are >= 4 rows so the eye tracks one column.
    column_rows: list[tuple[str, str]] = []
    column_rows.extend(_render_relationships_block(fields))

    # ENH-2574 item 5: collapse "Captured at" when it's the same calendar date
    # as "Discovered" -- the two otherwise duplicate each other.
    captured_raw = fields.get("captured_at")
    discovered_raw = fields.get("discovered_date")
    if captured_raw:
        captured_date = _date_only(str(captured_raw))
        if not (discovered_raw and _date_only(str(discovered_raw)) == captured_date):
            column_rows.append(("Captured at", captured_date))
    # ENH-2535: discovery block sits between capture and completion timestamps.
    column_rows.extend(_render_discovery_block(fields))
    if fields.get("completed_at"):
        column_rows.append(("Completed at", _date_only(str(fields["completed_at"]))))

    tail_rows: list[tuple[str, str]] = []
    if fields.get("history"):
        tail_rows.append(("History", str(fields["history"])))
    # ENH-2535: closure context block -- at the tail (terminal statuses only).
    tail_rows.extend(_render_closure_block(fields, fields.get("raw_status") or ""))

    align = len(column_rows) + len(tail_rows) >= 4
    label_width = max((len(label) for label, _ in column_rows + tail_rows), default=0)

    def _render_row(label: str, value: str) -> str:
        key_text = f"{label}:"
        if align:
            key_text = key_text.ljust(label_width + 1)
        return f"{_dim(key_text)} {value}"

    for label, value in column_rows:
        detail_lines.append(_render_row(label, value))

    # ENH-2535: decision coupling line -- emits before history so the user sees
    # the actionable pointer alongside other metadata, not buried after history.
    decision_line = _render_decision_line(fields)
    if decision_line:
        detail_lines.append(decision_line)

    for label, value in tail_rows:
        detail_lines.append(_render_row(label, value))

    # Build path line (dimmed -- reference info, not content).
    path_line = f"Path: {fields.get('path', '???')}"

    # Calculate structural width from non-summary content
    structural_lines = [header, meta_line, path_line]
    if scores_line:
        structural_lines.append(scores_line)
    if dim_scores_line:
        structural_lines.append(dim_scores_line)
    structural_lines.extend(strip_ansi(dl) for dl in detail_lines)

    # ENH-2574 item 2: the card targets ~100 cols on wide terminals, decoupled
    # from metadata width -- it no longer stays pinned to the longest
    # structural line. Still capped at terminal_width() - 4.
    max_content_width = max(terminal_width() - 4, 20)
    wrap_width = max(min(max_content_width, 100), 60)

    # Build summary lines -- reflow paragraphs first so hard line breaks from
    # the source markdown don't survive as 1-2 word orphan lines (item 1).
    summary_lines: list[str] = []
    summary_text = fields.get("summary")
    if summary_text:
        paragraphs = re.split(r"\n\s*\n", summary_text.strip())
        for idx, para in enumerate(paragraphs):
            words = " ".join(para.split())
            if words:
                summary_lines.extend(textwrap.wrap(words, width=wrap_width, break_long_words=False))
            if idx < len(paragraphs) - 1:
                summary_lines.append("")

    # Final width includes wrapped summary and structural content.
    all_lines = structural_lines + summary_lines
    width = max(max((len(line) for line in all_lines), default=60) + 2, wrap_width + 2)
    width = min(width, max_content_width)

    # Build colorized header -- bold title, colored ID (item 3).
    if issue_id and "-" in issue_id:
        itype = issue_id.split("-")[0]
        colored_id = colorize(issue_id, TYPE_COLOR.get(itype, "0"))
    else:
        colored_id = issue_id
    colored_header = f"{colored_id}: {colorize(title, '1')}"

    # Build colorized meta line
    colored_meta_parts: list[str] = []
    if priority:
        colored_meta_parts.append(
            f"{_dim('Priority:')} {colorize(priority, PRIORITY_COLOR.get(priority, '0'))}"
        )
    if status:
        colored_status = colorize(status, _STATUS_COLOR.get(status, "0"))
        colored_meta_parts.append(f"{_dim('Status:')} {colored_status}")
    if effort:
        colored_meta_parts.append(f"{_dim('Effort:')} {effort}")
    if risk:
        risk_code = {"High": "38;5;208", "Medium": "33", "Low": "2"}.get(risk, "0")
        colored_meta_parts.append(f"{_dim('Risk:')} {colorize(risk, risk_code)}")
    colored_meta_line = sep.join(colored_meta_parts)

    colored_path_line = _dim(path_line)

    # Build card -- borders dimmed so content pops over chrome (item 3).
    lines: list[str] = []
    top_border = _dim(f"{tl}{h * width}{tr}")
    mid_border = _dim(f"{ml}{h * width}{mr}")
    bot_border = _dim(f"{bl}{h * width}{br}")
    dim_v = _dim(v)

    # ENH-2574 item 7: every content row is truncated (unbreakable tokens get
    # an ellipsis) then left-padded — no line bleeds past the right border.
    lines.append(top_border)
    lines.append(f"{dim_v} {_fit(colored_header, width - 1)}{dim_v}")
    lines.append(mid_border)
    lines.append(f"{dim_v} {_fit(colored_meta_line, width - 1)}{dim_v}")
    if scores_line:
        lines.append(f"{dim_v} {_fit(scores_line, width - 1)}{dim_v}")
    if dim_scores_line:
        lines.append(f"{dim_v} {_fit(dim_scores_line, width - 1)}{dim_v}")
    if summary_lines:
        lines.append(mid_border)
        for sl in summary_lines:
            lines.append(f"{dim_v} {_fit(sl, width - 1)}{dim_v}")
    if detail_lines:
        lines.append(mid_border)
        for dl in detail_lines:
            lines.append(f"{dim_v} {_fit(dl, width - 1)}{dim_v}")
    lines.append(mid_border)
    lines.append(f"{dim_v} {_fit(colored_path_line, width - 1)}{dim_v}")
    lines.append(bot_border)

    return "\n".join(lines)


def cmd_show(config: BRConfig, args: argparse.Namespace) -> int:
    """Display summary card for a single issue.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id attribute

    Returns:
        Exit code (0 = success, 1 = not found)
    """
    issue_id = args.issue_id
    path = _resolve_issue_id(config, issue_id)

    if path is None:
        print(f"Error: Issue '{issue_id}' not found.")
        return 1

    fields = _parse_card_fields(path, config)

    if getattr(args, "json", False):
        print_json(fields)
        return 0

    card = _render_card(fields)
    print(card)
    return 0

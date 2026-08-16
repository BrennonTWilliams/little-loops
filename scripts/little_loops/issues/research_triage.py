"""Research-axis triage for ``/ll:refine-issue`` Step 3 (ENH-2971).

``/ll:refine-issue`` used to spawn ``codebase-locator``, ``codebase-analyzer``
and ``codebase-pattern-finder`` unconditionally on every invocation. For an
already-enriched issue, most of that fan-out re-derives findings the issue
already carries. :func:`triage_research_axes` decides which axes are genuinely
unmet, as a pure function of (issue file, disk state) — no model call.

Two independent checks decide an axis:

1. **Coverage** — ≥:data:`COVERAGE_THRESHOLD` of the axis's *qualified* path
   references resolve. Qualification and resolution are ENH-2983's shipped
   :func:`~little_loops.text_utils.classify_file_ref`; globs, ``<placeholder>``
   paths and bare basenames come back ``unresolvable_form`` and are excluded
   from both sides of the fraction. The rule is deliberately fraction-based
   rather than a conjunction: the corpus's per-path staleness rate is flat
   (~15%) across every Integration Map size, so an "all must resolve" rule
   would compound to ``0.85^k`` and measure map *size* instead of currency.
2. **Staleness** — a reference resolving is not the same as its target being
   unchanged since the issue last incorporated it. Every resolved path's
   ``max(git commit time, filesystem mtime)`` is compared against the most
   recent ``/ll:refine-issue`` ``## Session Log`` timestamp; a target that moved
   after that pass makes the axis uncovered even though the path resolves.
   Both clocks are required — this repo is developed with a persistently dirty
   working tree, so a git-only check would miss uncommitted edits.

Coverage is the cheap pre-reject; staleness carries the real discrimination.

A third check overrides `analyzer` specifically: when a project's Program Design gate
(:mod:`~little_loops.issues.program_design`, ENH-2852) is active for this issue and its
``## Program Design`` section is missing, empty, boilerplate, or graded non-specific, the
axis is forced uncovered regardless of Root Cause/Current Behavior evidence (BUG-3003).
Without this, an already-refined issue with a resolving Root Cause triages `analyzer:
covered` and `/ll:refine-issue` skips the analyzer agent that would write the section.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from little_loops.session_log import last_command_timestamp
from little_loops.text_utils import (
    SOURCE_EXTENSIONS,
    RefIndex,
    build_ref_index,
    classify_file_ref,
    extract_file_paths,
    fence_spans,
    in_fence,
    resolve_ref_path,
    strip_code_fences,
)

ResearchAxis = Literal["locator", "analyzer", "pattern_finder"]

#: Fraction of an axis's qualified path references that must resolve for the
#: axis to count as covered. Measured against the issue corpus: ≥80% holds
#: within an 8.2-point band across a 10x range of Integration Map sizes, where
#: a conjunction rule spreads 70.8 points. See ENH-2971 § "The rule must be
#: fraction-based".
COVERAGE_THRESHOLD = 0.8

#: The refine command whose Session Log timestamp bounds the staleness check.
REFINE_COMMAND = "/ll:refine-issue"

AXES: tuple[ResearchAxis, ...] = ("locator", "analyzer", "pattern_finder")

# Which ``## heading`` sections evidence each axis, and whether the axis also
# demands a symbol name co-located with the resolving path. The locator agent's
# output *is* a set of file locations, so a resolving path satisfies it
# outright; the other two make claims about behavior and convention *inside* a
# file, which a bare path alone does not evidence.
_AXIS_SECTIONS: dict[ResearchAxis, tuple[str, ...]] = {
    "locator": ("Integration Map",),
    "analyzer": ("Root Cause", "Current Behavior"),
    "pattern_finder": ("Proposed Solution",),
}
_AXIS_NEEDS_SYMBOL: dict[ResearchAxis, bool] = {
    "locator": False,
    "analyzer": True,
    "pattern_finder": True,
}

# A backtick-quoted identifier: `helper()`, `Cls.method`, `COVERAGE_THRESHOLD`.
_SYMBOL_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*(?:\(\))?)`")

# Sentinel prefixing each commit's timestamp in the batched git log walk, so a
# timestamp line can never be confused with a filename line.
_GIT_LOG_FORMAT = "%x00%cI"


@dataclass(frozen=True)
class AxisCoverage:
    """Whether one research axis is already covered by the issue's own content."""

    axis: ResearchAxis
    covered: bool
    evidence: str  # satisfying section + path, staleness reason, or "" when unmet

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the JSON shape ``ll-issues research-triage --json`` emits."""
        return {"covered": self.covered, "evidence": self.evidence}


@dataclass(frozen=True)
class ChangeTimeIndex:
    """Last-commit time per repo-relative path, from a single ``git log`` walk.

    ``floor`` records how far back the walk went: commits older than it were
    never visited, so a path absent from ``by_path`` means "no commit at or
    after ``floor``", not "never committed". A caller comparing against a
    timestamp *older* than ``floor`` would therefore read a missed commit as
    no-change — :func:`triage_research_axes` guards against that by rebuilding
    a scoped index rather than trusting a too-shallow one.
    """

    by_path: dict[str, datetime]
    floor: datetime | None


def _section_text(content: str, heading: str) -> str:
    """Return the fence-stripped body of ``## heading``, or ``""`` when absent.

    Uses the same last-occurrence-wins contract as
    :func:`~little_loops.issue_parser._section_body`. Both the heading match and
    the end-boundary scan exclude matches that fall inside a fenced code block
    (ENH-3206, mirroring BUG-3202's :func:`~little_loops.issue_parser.
    _section_body_with_offset`) via :func:`~little_loops.text_utils.fence_spans`/
    :func:`~little_loops.text_utils.in_fence` — a quoted ``##``-shaped line no
    longer wins heading resolution or truncates the section that encloses it.
    The returned text stays fence-*stripped* (this function's existing
    contract) since callers like :func:`_has_symbol` scan for prose-level
    symbol mentions and fence content would inflate matches.
    """
    spans = fence_spans(content)
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    matches = [
        m
        for m in re.finditer(pattern, content, re.MULTILINE)
        if not in_fence(m.start(), m.end(), spans)
    ]
    if not matches:
        return ""
    start = matches[-1].end()

    terminator_pattern = re.compile(r"^##\s", re.MULTILINE)
    end = len(content)
    for term in terminator_pattern.finditer(content, start):
        if not in_fence(term.start(), term.end(), spans):
            end = term.start()
            break
    return strip_code_fences(content[start:end])


def _has_symbol(section: str) -> bool:
    """True when the (already fence-stripped) section names a code symbol.

    A backtick-quoted token that is really a filename (``mod.py``) does not
    count — the point of the symbol requirement is evidence about behavior
    *inside* a file, which repeating the filename does not supply.
    """
    for match in _SYMBOL_RE.finditer(section):
        token = match.group(1)
        if "/" in token:
            continue
        if Path(token.removesuffix("()")).suffix.lower() in SOURCE_EXTENSIONS:
            continue
        return True
    return False


def _axis_refs(content: str, axis: ResearchAxis) -> list[tuple[str, str, str]]:
    """Return ``(heading, ref, source_line)`` for every path ref on *axis*."""
    found: list[tuple[str, str, str]] = []
    for heading in _AXIS_SECTIONS[axis]:
        section = _section_text(content, heading)
        if not section:
            continue
        lines = section.splitlines()
        for ref in sorted(extract_file_paths(section)):
            line = next((ln for ln in lines if ref in ln), "")
            found.append((heading, ref, line))
    return found


def qualified_ref_count(
    issue_path: Path,
    axis: ResearchAxis,
    *,
    index: RefIndex | None = None,
) -> int:
    """Number of denominator-eligible path refs on *axis* for this issue.

    "Eligible" means the reference survived the form filter — i.e. it
    classifies ``resolved``, ``stale``, or ``ambiguous`` (ENH-2999: an
    ambiguous ref still cites a real file, so it stays denominator-eligible —
    only ``unresolvable_form`` and ``planned_new`` are excluded. Exposed for
    the corpus length-neutrality measurement, which bands issues by this
    count.
    """
    try:
        content = issue_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    if index is None:
        root = issue_path.parent
        index = build_ref_index(root)
    eligible = 0
    for _heading, ref, line in _axis_refs(content, axis):
        if classify_file_ref(ref, index, line=line) in ("resolved", "stale", "ambiguous"):
            eligible += 1
    return eligible


def _git_changes_since(root: Path, since: datetime | None) -> dict[str, datetime]:
    """Map each path touched at/after *since* to its most recent commit time.

    One subprocess for the whole walk — the alternative, ``git log -1`` per
    referenced path, fans out a subprocess per Integration Map entry on the hot
    path of every refine.
    """
    args = ["git", "log", f"--format={_GIT_LOG_FORMAT}", "--name-only", "--no-renames"]
    if since is not None:
        args.append(f"--since={since.astimezone(UTC).isoformat()}")
    try:
        result = subprocess.run(args, cwd=root, capture_output=True, check=False)
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}

    by_path: dict[str, datetime] = {}
    current: datetime | None = None
    for raw in result.stdout.decode("utf-8", errors="replace").splitlines():
        if raw.startswith("\0"):
            try:
                current = datetime.fromisoformat(raw[1:].strip())
            except ValueError:
                current = None
            continue
        name = raw.strip()
        if not name or current is None:
            continue
        # git log walks newest-first, so the first time a path appears is its
        # most recent commit.
        by_path.setdefault(name, current)
    return by_path


def build_change_time_index(root: Path, since: datetime | None = None) -> ChangeTimeIndex:
    """Build a :class:`ChangeTimeIndex` for *root*, optionally floored at *since*.

    Pass ``since=None`` to walk full history — the right choice when one index
    is shared across many issues with unknown refine timestamps. Pass the
    issue's own refine timestamp for a single-issue call, which is what
    :func:`triage_research_axes` does by default.
    """
    return ChangeTimeIndex(by_path=_git_changes_since(root, since), floor=since)


def _mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return None


def _change_time(root: Path, rel_path: str, change_times: ChangeTimeIndex) -> datetime | None:
    """``max(git commit time, filesystem mtime)`` for one tracked path."""
    candidates = [t for t in (change_times.by_path.get(rel_path), _mtime(root / rel_path)) if t]
    return max(candidates) if candidates else None


def triage_research_axes(
    issue_path: Path,
    root: Path,
    *,
    index: RefIndex | None = None,
    change_times: ChangeTimeIndex | None = None,
    check_staleness: bool = True,
) -> tuple[AxisCoverage, ...]:
    """Which research axes the issue already covers with resolving references.

    Args:
        issue_path: The issue markdown file to triage.
        root: Repository root that references resolve against.
        index: A :class:`~little_loops.text_utils.RefIndex` to reuse. Built once
            here when omitted; pass one explicitly to amortize the
            ``git ls-files`` call across a corpus sweep.
        change_times: A :class:`ChangeTimeIndex` to reuse. Built here, scoped to
            the issue's own refine timestamp, when omitted. A supplied index
            whose ``floor`` is *newer* than that timestamp is too shallow to
            answer the question and is rebuilt rather than trusted.
        check_staleness: Set False to score the coverage predicate alone. This
            exists for calibration, not for callers: the ENH-2971 corpus
            measurements (skip rate, size-band neutrality) were all defined
            against coverage before the Staleness Check was designed, so
            reproducing them requires isolating it. Production callers leave
            this True.

    Returns:
        One :class:`AxisCoverage` per entry in :data:`AXES`, in that order.
        Unreadable issues yield three uncovered axes (fail-open: the caller
        spawns everything, which is the pre-ENH-2971 behavior).
    """
    try:
        content = issue_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return tuple(AxisCoverage(axis=a, covered=False, evidence="") for a in AXES)

    if index is None:
        index = build_ref_index(root)

    refined_at = last_command_timestamp(content, REFINE_COMMAND) if check_staleness else None
    if refined_at is not None and (
        change_times is None or (change_times.floor is not None and change_times.floor > refined_at)
    ):
        change_times = build_change_time_index(root, refined_at)
    if change_times is None:
        change_times = ChangeTimeIndex(by_path={}, floor=None)

    coverages = tuple(
        _triage_axis(content, axis, root, index, change_times, refined_at) for axis in AXES
    )

    unmet_reason = _program_design_unmet(issue_path, content)
    if not unmet_reason:
        return coverages
    return tuple(
        AxisCoverage(axis="analyzer", covered=False, evidence=unmet_reason)
        if c.axis == "analyzer"
        else c
        for c in coverages
    )


def _program_design_unmet(issue_path: Path, content: str) -> str:
    """Evidence string when the Program Design gate is active and unmet, else ``""``.

    The override this feeds (BUG-3003) fires on the *union* of ``missing ∪ empty ∪
    boilerplate ∪ program_design_nonspecific`` for the ``## Program Design`` section —
    deliberately wider than ``format-check``'s ``program_design_nonspecific`` alone,
    since a missing/empty/boilerplate section never reaches that grading call
    (:func:`~little_loops.issue_parser.check_format_gaps`). Modeled on
    :func:`~little_loops.issue_parser._gate_program_design`.
    """
    from little_loops.issue_parser import _ISSUE_TYPE_RE, _normalize_whitespace, _section_body
    from little_loops.issue_template import load_issue_sections
    from little_loops.issues.program_design import (
        SECTION_TITLE,
        grade_issue_section,
        program_design_gate_active,
    )

    if not program_design_gate_active(issue_path, content):
        return ""

    # Non-fence-stripping extraction: Program Design's graded material (signature
    # lines, call-path anchors) routinely lives inside a fenced block per Step 5a's
    # own template. `_section_text`'s fence-stripping would read a correctly-designed
    # fenced section as empty and re-spawn the analyzer agent forever.
    body = _section_body(content, SECTION_TITLE)
    if body is None:
        return "Program Design gate: section missing"

    stripped = body.strip()
    if not stripped:
        return "Program Design gate: section empty"

    type_match = _ISSUE_TYPE_RE.search(issue_path.name)
    if type_match:
        try:
            sections_data = load_issue_sections(type_match.group(1))
        except Exception:
            sections_data = {}
        template = (
            sections_data.get("common_sections", {})
            .get(SECTION_TITLE, {})
            .get("creation_template", "")
        )
        if template and _normalize_whitespace(stripped) == _normalize_whitespace(template):
            return "Program Design gate: section boilerplate"

    verdict = grade_issue_section(issue_path, body)
    if verdict.is_specific:
        return ""
    reason = "; ".join(verdict.reasons) if verdict.reasons else "section is not specific"
    return f"Program Design gate: {reason}"


def _triage_axis(
    content: str,
    axis: ResearchAxis,
    root: Path,
    index: RefIndex,
    change_times: ChangeTimeIndex,
    refined_at: datetime | None,
) -> AxisCoverage:
    resolved: list[tuple[str, str]] = []  # (heading, tracked path)
    eligible = 0
    heading_with_symbol: set[str] = set()

    for heading, ref, line in _axis_refs(content, axis):
        status = classify_file_ref(ref, index, line=line)
        if status not in ("resolved", "stale", "ambiguous"):
            continue
        eligible += 1
        if status == "resolved":
            tracked = resolve_ref_path(ref, index) or ref
            resolved.append((heading, tracked))

    if eligible == 0 or len(resolved) / eligible < COVERAGE_THRESHOLD:
        return AxisCoverage(axis=axis, covered=False, evidence="")

    if _AXIS_NEEDS_SYMBOL[axis]:
        for heading in {h for h, _ in resolved}:
            if _has_symbol(_section_text(content, heading)):
                heading_with_symbol.add(heading)
        resolved = [(h, p) for h, p in resolved if h in heading_with_symbol]
        if not resolved:
            return AxisCoverage(axis=axis, covered=False, evidence="")

    # Staleness: a resolving reference whose target moved after the issue last
    # incorporated it is worse than an absent one — it looks like coverage.
    # With no prior refine there is nothing to compare against.
    if refined_at is not None:
        for heading, tracked in resolved:
            changed = _change_time(root, tracked, change_times)
            if changed is not None and changed > refined_at:
                return AxisCoverage(
                    axis=axis,
                    covered=False,
                    evidence=(
                        f"stale: {tracked} changed {changed.isoformat()}, "
                        f"issue last refined {refined_at.isoformat()} ({heading})"
                    ),
                )

    heading, tracked = resolved[0]
    return AxisCoverage(axis=axis, covered=True, evidence=f"{heading} → {tracked}")

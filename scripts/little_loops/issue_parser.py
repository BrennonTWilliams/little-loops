"""Issue file parsing for little-loops.

Parses issue markdown files to extract metadata like priority, ID, type, and title.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.cli_args import _id_matches
from little_loops.frontmatter import (
    DEPRECATED_FRONTMATTER_KEYS,
    DEPRECATED_STATUS_VALUES,
    parse_frontmatter,
)

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.text_utils import RefIndex


logger = logging.getLogger(__name__)

# Regex pattern for issue IDs in list items
# Matches: "- FEAT-001", "- BUG-123", "* ENH-005", "- FEAT-001 (some note)"
# Also handles bold markdown: "- **ENH-1000**: description"
ISSUE_ID_PATTERN = re.compile(r"^[-*]\s+\*{0,2}([A-Z]+-\d+)", re.MULTILINE)

# Top-level bullet markers only (FEAT-2948): "- [ ]"/"- [x]" checkboxes, plain
# "- "/"* " bullets, and "N. " numbered items. Matched with re.match against the
# *unstripped* line, so any leading whitespace before the marker (a sub-bullet)
# fails to match by construction — this is the "skip indented items" rule from
# skills/verify-issue-loop/SKILL.md:129-135.
_CRITERION_BULLET_PATTERN = re.compile(r"^(?:-\s*\[[xX ]\]\s+|[-*]\s+|\d+\.\s+)(.+)$")

# Sections checked in priority order by IssueParser.extract_criteria(): Acceptance
# Criteria is preferred; Expected Behavior is the fallback when Acceptance Criteria
# is absent or has no top-level bullets.
_CRITERIA_SECTION_NAMES = ("Acceptance Criteria", "Expected Behavior")


_NORMALIZED_RE = re.compile(r"^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$")
_ISSUE_TYPE_RE = re.compile(r"-(BUG|FEAT|ENH|EPIC)-")
_FILENAME_ID_RE = re.compile(r"(BUG|FEAT|ENH|EPIC)-(\d+)")


# (resolved path, deprecated key) pairs already warned about this process.
_WARNED_DEPRECATED_KEYS: set[tuple[str, str]] = set()


def _warn_deprecated_key(issue_path: Path, old_key: str, new_key: str) -> None:
    """Warn once per process that *issue_path* uses a deprecated frontmatter key.

    Several commands parse the whole issue tree more than once in a single run
    — ``ll-issues list --group-by epic`` and ``--parent`` each layer a second
    ``find_issues()`` sweep on top of the first, and ``next-issue``/``sequence``/
    ``deps`` pair ``find_issues()`` with ``find_issues_for_graph()``. Without
    this guard every deprecated key is reported once per sweep, which is how a
    21-file backlog produced 42 identical warning lines.

    Keyed on the *resolved* path rather than the bare filename: ``tmp_path``
    fixtures across the test suite reuse basenames freely, and collapsing two
    genuinely different files into one key would silence a real warning.
    """
    try:
        key_path = str(issue_path.resolve())
    except OSError:  # pragma: no cover - unresolvable path (broken symlink, races)
        key_path = str(issue_path)

    if (key_path, old_key) in _WARNED_DEPRECATED_KEYS:
        return
    _WARNED_DEPRECATED_KEYS.add((key_path, old_key))
    logger.warning(
        "%s: deprecated frontmatter key '%s' — rename to '%s'",
        issue_path.name,
        old_key,
        new_key,
    )


def reset_deprecated_key_warnings() -> None:
    """Clear the once-per-process warning ledger.

    Test-support hook: without it, whichever test parses a given file first
    swallows the warning for every later test that parses the same path.
    """
    _WARNED_DEPRECATED_KEYS.clear()


def is_normalized(filename: str) -> bool:
    """Check whether an issue filename conforms to naming conventions.

    Args:
        filename: The basename of the issue file (e.g. 'P2-BUG-010-my-issue.md').

    Returns:
        True if the filename matches ``^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\\.md$``.
    """
    return bool(_NORMALIZED_RE.match(filename))


def _required_sections(sections_data: dict[str, Any]) -> set[str]:
    """Return the set of non-deprecated required section titles for a template.

    Shared by :func:`is_formatted` and :func:`check_format_gaps`. ``common_sections``
    entries use a boolean ``required`` key; ``type_sections`` entries use a string
    ``level`` key (``== "required"``) — this asymmetry is why there are two loops.
    """
    required: set[str] = set()
    for name, defn in sections_data.get("common_sections", {}).items():
        if defn.get("required") is True and not defn.get("deprecated", False):
            required.add(name)
    for name, defn in sections_data.get("type_sections", {}).items():
        if defn.get("level") == "required" and not defn.get("deprecated", False):
            required.add(name)
    return required


#: Title of the section graded for specificity (ENH-2852). Duplicated as a module
#: constant so the hot path does not import the grading module on every issue.
_PROGRAM_DESIGN_TITLE = "Program Design"


def _gate_program_design(required: set[str], issue_path: Path, content: str) -> set[str]:
    """Drop ``Program Design`` from *required* unless this issue is subject to the gate.

    ``Program Design`` is a required ``common_sections`` entry (ENH-2852), so without
    this filter it would report ``missing`` for every pre-existing issue in every
    project the moment the schema ships. The gate is opt-in per project (the
    ``.ll/program-design-cutover.json`` stamp) and grandfathers issues refined before
    it — see :mod:`little_loops.issues.program_design`. Applying the filter here rather
    than in skill prose means every consumer of the gap set inherits the exemption.
    """
    from little_loops.issues.program_design import SECTION_TITLE, program_design_gate_active

    if SECTION_TITLE not in required:
        return required
    if program_design_gate_active(issue_path, content):
        return required
    return required - {SECTION_TITLE}


def is_formatted(issue_path: Path, templates_dir: Path | None = None) -> bool:
    """Check whether an issue file has been formatted.

    An issue is considered formatted if either:
    1. Its ## Session Log contains a ``/ll:format-issue`` entry, OR
    2. It has all required sections per its type template (structural check).

    Args:
        issue_path: Path to the issue markdown file.
        templates_dir: Optional override for the templates directory.

    Returns:
        True if the issue is formatted by either criterion, False otherwise.
        Returns False for files whose type cannot be determined or whose template
        cannot be loaded.
    """
    from little_loops.issue_template import load_issue_sections
    from little_loops.session_log import parse_session_log

    try:
        content = issue_path.read_text(encoding="utf-8")
    except Exception:
        return False

    # Criterion 1: /ll:format-issue appears in the session log
    if "/ll:format-issue" in parse_session_log(content):
        return True

    # Criterion 2: all required sections are present as ## headings
    type_match = _ISSUE_TYPE_RE.search(issue_path.name)
    if not type_match:
        return False
    issue_type = type_match.group(1)

    try:
        sections_data = load_issue_sections(issue_type, templates_dir)
    except Exception:
        return False

    required = _gate_program_design(_required_sections(sections_data), issue_path, content)
    if not required:
        return True

    headings = {m.strip() for m in re.findall(r"^##\s+(.+)$", content, re.MULTILINE)}
    return required.issubset(headings)


# Extracts a canonical replacement name from a deprecation_reason string, e.g.
# "Renamed to 'Proposed Solution' in v2.0" or "Consolidated into 'API/Interface' section".
_DEPRECATION_CANONICAL_RE = re.compile(r"(?:Renamed to|Consolidated into|Redundant with) '([^']+)'")


def _section_body_with_offset(content: str, heading: str) -> tuple[str, int] | None:
    """Return ``(body, absolute_start_offset)`` for a ``## heading`` section.

    ``absolute_start_offset`` is *body*'s start position within *content*, used by
    span-reporting callers (e.g. :func:`locate_enumerable_options`, ENH-2950) to
    translate body-relative match positions into document line numbers. Returns
    None when the heading is absent. When the heading appears more than once
    (e.g. ``## Confidence Check Notes`` appended fresh by every confidence-check
    run), the last occurrence wins — the same "last one wins" contract used by
    :func:`~little_loops.session_log.parse_session_log`.
    """
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    matches = list(re.finditer(pattern, content, re.MULTILINE))
    if not matches:
        return None
    match = matches[-1]
    start = match.end()
    next_match = re.search(r"^##\s", content[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(content)
    return content[start:end], start


def _section_body(content: str, heading: str) -> str | None:
    """Return the raw text between a ``## heading`` line and the next ``##`` line.

    Returns None when the heading is absent.
    """
    result = _section_body_with_offset(content, heading)
    return result[0] if result else None


def _normalize_whitespace(text: str) -> str:
    """Collapse all whitespace runs to single spaces, for boilerplate comparison."""
    return " ".join(text.split())


@dataclass
class FormatGaps:
    """Graded structural format gaps for an issue (ENH-2426).

    Model: EpicDrift (cli/issues/epic_consistency.py) — one list[str] field per
    gap category plus a derived has_gaps property and a to_dict() for --format json.
    """

    missing: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)
    boilerplate: list[str] = field(default_factory=list)
    malformed_id: list[str] = field(default_factory=list)
    prose_dep_drift: list[str] = field(default_factory=list)
    stale_prose_dep: list[str] = field(default_factory=list)
    program_design_nonspecific: list[str] = field(default_factory=list)
    deprecated_key: list[str] = field(default_factory=list)
    multi_frontmatter: list[str] = field(default_factory=list)
    testable: list[str] = field(default_factory=list)
    stale_file_ref: list[str] = field(default_factory=list)
    unmarked_superseded_directive: list[str] = field(default_factory=list)
    duplicate_findings_block: list[str] = field(default_factory=list)

    @property
    def has_gaps(self) -> bool:
        """True when any gap category is non-empty."""
        return bool(
            self.missing
            or self.renamed
            or self.empty
            or self.boilerplate
            or self.malformed_id
            or self.prose_dep_drift
            or self.stale_prose_dep
            or self.program_design_nonspecific
            or self.deprecated_key
            or self.multi_frontmatter
            or self.testable
            or self.stale_file_ref
            or self.unmarked_superseded_directive
            or self.duplicate_findings_block
        )

    def to_dict(self) -> dict[str, list[str]]:
        """Serialize to a JSON-serializable dict for --format json output."""
        return {
            "missing": self.missing,
            "renamed": self.renamed,
            "empty": self.empty,
            "boilerplate": self.boilerplate,
            "malformed_id": self.malformed_id,
            "prose_dep_drift": self.prose_dep_drift,
            "stale_prose_dep": self.stale_prose_dep,
            "program_design_nonspecific": self.program_design_nonspecific,
            "deprecated_key": self.deprecated_key,
            "multi_frontmatter": self.multi_frontmatter,
            "testable": self.testable,
            "stale_file_ref": self.stale_file_ref,
            "unmarked_superseded_directive": self.unmarked_superseded_directive,
            "duplicate_findings_block": self.duplicate_findings_block,
        }


@dataclass
class QuestionGaps:
    """Coverage-aware unresolved-decision gaps for an issue (ENH-2446).

    Mirror of :class:`FormatGaps` (lines above): two list[str] fields (one per
    gap category) plus a derived :attr:`has_gaps` property and :meth:`to_dict`
    for --format json. Drives ``ll-issues check-open-questions``.
    """

    unresolved_options: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    @property
    def has_gaps(self) -> bool:
        return bool(self.unresolved_options) or bool(self.open_questions)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "unresolved_options": self.unresolved_options,
            "open_questions": self.open_questions,
        }


def check_format_gaps(
    issue_path: Path,
    templates_dir: Path | None = None,
    issue_statuses: dict[str, str] | None = None,
    ref_index: RefIndex | None = None,
) -> FormatGaps:
    """Grade an issue's structural format gaps against its type template.

    Deterministic (no LLM) structural linter for the ``ensure_formatted`` gate.
    Unlike :func:`is_formatted`, this always runs the structural analysis — it does
    not honor the ``/ll:format-issue`` session-log shortcut, since every issue that
    reaches the gate has already run that command (the shortcut would always fire
    and defeat the point of catching malformed-but-present issues).

    Gap classes:
        missing: a required section header is absent from the body.
        renamed: a present section header is deprecated with an extractable
            canonical replacement (e.g. "Proposed Fix" -> "Proposed Solution").
        empty: a required section header is present but its body is whitespace-only.
        boilerplate: a required section's body still equals its creation_template.
        malformed_id: frontmatter ``id`` is present but does not match the
            filename-derived ``TYPE-NNN`` (BUG-2769) — e.g. a bare int
            (``id: 2756``) or quoted numeric (``id: "1294"``) instead of
            ``id: BUG-2756``.
        prose_dep_drift: the body claims a dependency in prose (FEAT-2849,
            :func:`little_loops.issues.prose_deps.extract_prose_deps`) on an
            **active** issue absent from ``blocked_by``/``depends_on``.
        stale_prose_dep: the body claims a prose dependency on an issue whose
            status is ``done``/``cancelled`` — the remedy is deleting the
            stale text, not adding an edge.
        program_design_nonspecific: the ``## Program Design`` section is present
            and non-boilerplate but not *specific* (ENH-2852) — it lacks a
            signature-shaped line, or names no ``Call Path`` anchor that resolves
            against the repo. Only reported when the project has armed the gate
            with a ``.ll/program-design-cutover.json`` stamp and the issue is not
            grandfathered or opted out via ``program_design_not_applicable``.
        deprecated_key: the frontmatter carries a retired key (e.g.
            ``superseded_by``) or a coerced status synonym (ENH-2876,
            :data:`little_loops.frontmatter.DEPRECATED_FRONTMATTER_KEYS`,
            :data:`little_loops.frontmatter.DEPRECATED_STATUS_VALUES`). Each
            entry pairs the retired key/value with its mandatory prose reason,
            surfaced in the same output that reports the key.
        multi_frontmatter: the issue carries more than one YAML frontmatter
            block in its header region (BUG-2955,
            :func:`little_loops.frontmatter.has_multiple_frontmatter_blocks`)
            — e.g. an outer ``score_*`` block prepended by the confidence-check
            scoring path, followed by the canonical ``id:``-bearing block. Read
            paths merge both blocks so no data is lost, but the shape is
            malformed and should be folded into a single block.
        stale_file_ref: a file path reference extracted from the body
            (ENH-2983, :func:`little_loops.text_utils.classify_issue_refs`)
            classifies as ``stale`` — a ``/``-qualified path with no exact or
            unique-suffix match against tracked files, i.e. genuine drift
            (the file moved or was deleted since the issue was written).
            Reporting only; the remedy needs human intent, so no auto-fix.
            Only reported when *ref_index* is given. When absent, this check
            fails open (no gaps reported), matching this module's existing
            convention.
        unmarked_superseded_directive: an issue's ``### Codebase Research
            Findings`` block contains a correction phrase from the closed
            list below (ENH-2995) while none of the three directive sections
            (``## Implementation Steps``, ``### Files to Modify``,
            ``## Acceptance Criteria``) carries a ``⚠ Superseded`` marker.
            Correction phrases: ``is wrong``, ``does not exist``,
            ``will not work``, ``must be dropped``, ``target file is wrong``,
            ``is stale``, ``omit entirely`` — the closed set /ll:refine-issue's
            Preservation Rule carve-out uses as non-exhaustive LLM guidance;
            here it is a closed detection list. Report-only, keyword-inference
            heuristic (like ``testable``) — not proof the correction actually
            refutes the specific line, only that the block and the marker are
            both absent or present.

    Args:
        issue_path: Path to the issue markdown file.
        templates_dir: Optional override for the templates directory.
        issue_statuses: Optional mapping of issue_id -> status, used to
            distinguish ``prose_dep_drift`` (active target) from
            ``stale_prose_dep`` (done/cancelled target). When absent, prose
            dependency checking fails open (no gaps reported for that class),
            matching this module's existing convention.
        ref_index: Optional :class:`little_loops.text_utils.RefIndex` built
            once per invocation (e.g. by ``ll-issues format-check``) via
            :func:`little_loops.text_utils.build_ref_index`, used to resolve
            file path references cited in the body. When absent, no
            ``stale_file_ref`` gaps are reported.

    Returns:
        A FormatGaps instance. Fails open (empty FormatGaps, no gaps) when the
        file is unreadable, its type cannot be determined, or its template cannot
        be loaded — mirroring is_formatted()'s fail-open behavior.
    """
    from little_loops.issue_template import load_issue_sections

    gaps = FormatGaps()

    try:
        content = issue_path.read_text(encoding="utf-8")
    except Exception:
        return gaps

    from little_loops.frontmatter import has_multiple_frontmatter_blocks

    if has_multiple_frontmatter_blocks(content):
        gaps.multi_frontmatter.append(
            "issue carries more than one YAML frontmatter block "
            "(fold into a single id:-bearing block — BUG-2955)"
        )

    frontmatter = parse_frontmatter(content)
    for key, entry in DEPRECATED_FRONTMATTER_KEYS.items():
        if key in frontmatter:
            gaps.deprecated_key.append(f"{key} — {entry.reason}")
    # parse_frontmatter() already canonicalizes STATUS_SYNONYMS on read (unconditionally),
    # so the raw synonym must be recovered from the frontmatter block text directly.
    raw_status_match = re.search(r"(?m)^status:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", content)
    if raw_status_match:
        raw_status = raw_status_match.group(1).strip()
        if raw_status in DEPRECATED_STATUS_VALUES:
            entry = DEPRECATED_STATUS_VALUES[raw_status]
            gaps.deprecated_key.append(f"status: {raw_status} — {entry.reason}")

    type_match = _ISSUE_TYPE_RE.search(issue_path.name)
    if not type_match:
        return gaps
    issue_type = type_match.group(1)

    try:
        sections_data = load_issue_sections(issue_type, templates_dir)
    except Exception:
        return gaps

    required = _gate_program_design(_required_sections(sections_data), issue_path, content)
    headings = {m.strip() for m in re.findall(r"^##\s+(.+)$", content, re.MULTILINE)}

    gaps.missing = sorted(required - headings)

    section_defs: dict[str, dict[str, Any]] = {}
    for group in ("common_sections", "type_sections"):
        for name, defn in sections_data.get(group, {}).items():
            if isinstance(defn, dict):
                section_defs[name] = defn

    deprecated_present = sorted(
        name
        for name, defn in section_defs.items()
        if defn.get("deprecated", False) and name in headings
    )
    for name in deprecated_present:
        canonical_match = _DEPRECATION_CANONICAL_RE.search(
            section_defs[name].get("deprecation_reason", "")
        )
        if canonical_match:
            gaps.renamed.append(f"{name} → {canonical_match.group(1)}")

    for name in sorted(required & headings):
        body = _section_body(content, name)
        if body is None:
            continue
        stripped = body.strip()
        if not stripped:
            gaps.empty.append(name)
            continue
        template = section_defs.get(name, {}).get("creation_template", "")
        if template and _normalize_whitespace(stripped) == _normalize_whitespace(template):
            gaps.boilerplate.append(name)
            continue
        if name == _PROGRAM_DESIGN_TITLE:
            from little_loops.issues.program_design import grade_issue_section

            verdict = grade_issue_section(issue_path, body)
            if not verdict.is_specific:
                gaps.program_design_nonspecific.append(f"{name}: {'; '.join(verdict.reasons)}")

    fm = parse_frontmatter(content)
    raw_id = fm.get("id")
    filename_id_match = _FILENAME_ID_RE.search(issue_path.name)
    if raw_id and filename_id_match:
        raw_str = str(raw_id).strip()
        canonical = f"{filename_id_match.group(1)}-{filename_id_match.group(2)}"
        if raw_str.upper() != canonical:
            gaps.malformed_id.append(f"id: {raw_str} (expected {canonical})")

    if issue_statuses is not None:
        from little_loops.frontmatter import strip_frontmatter
        from little_loops.issues.prose_deps import extract_prose_deps

        own_id = (
            f"{filename_id_match.group(1)}-{filename_id_match.group(2)}"
            if filename_id_match
            else None
        )
        structured_deps: set[str] = set()
        for key in ("blocked_by", "depends_on"):
            value = fm.get(key)
            if isinstance(value, list):
                structured_deps.update(str(v).strip().upper() for v in value)
            elif isinstance(value, str) and value.strip():
                structured_deps.add(value.strip().upper())

        body_only = strip_frontmatter(content)
        for prose_id in sorted(extract_prose_deps(body_only)):
            if prose_id == own_id:
                continue
            status = issue_statuses.get(prose_id)
            if status in ("done", "cancelled"):
                gaps.stale_prose_dep.append(prose_id)
            elif prose_id not in structured_deps:
                gaps.prose_dep_drift.append(prose_id)

    if "testable" not in fm:
        from little_loops.frontmatter import strip_frontmatter as _strip_fm

        title = str(fm.get("title") or "").strip()
        if not title:
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1) if title_match else ""
        scan_text = f"{title}\n{_strip_fm(content)}"
        if _count_testable_keyword_matches(scan_text) >= _TESTABLE_KEYWORD_THRESHOLD:
            gaps.testable.append(issue_path.name)

    if ref_index is not None:
        from little_loops.text_utils import classify_issue_refs

        for ref, status in sorted(classify_issue_refs(content, ref_index).items()):
            if status == "stale":
                gaps.stale_file_ref.append(ref)

    findings_bodies = _heading_bodies(content, "Codebase Research Findings")
    has_correction = any(
        phrase in body.lower()
        for body in findings_bodies
        for phrase in _SUPERSEDED_CORRECTION_PHRASES
    )
    if has_correction:
        directive_bodies = [
            body
            for name in _SUPERSEDED_DIRECTIVE_SECTIONS
            for body in _heading_bodies(content, name)
        ]
        if not any(_SUPERSEDED_MARKER_PREFIX in body for body in directive_bodies):
            gaps.unmarked_superseded_directive.append(issue_path.name)

    gaps.duplicate_findings_block.extend(_duplicate_findings_blocks(content))

    return gaps


# ENH-2993: `### Codebase Research Findings` accumulates one block per
# /ll:refine-issue pass; `ll-issues fold-findings` folds them to one per H2.
_FINDINGS_SUB_HEADING = "Codebase Research Findings"
_FINDINGS_H3_RE = re.compile(rf"^###\s+{re.escape(_FINDINGS_SUB_HEADING)}\s*$", re.MULTILINE)


def _duplicate_findings_blocks(content: str) -> list[str]:
    """Return ``"<H2> (N)"`` for each H2 carrying more than one findings block.

    Deliberately **not** built on :func:`_heading_bodies`, despite that being
    the existing reader of this heading. ``_heading_bodies`` is document-wide
    and returns bodies with no parent-section information, so ``len(bodies) > 1``
    cannot express "per H2": a fully compliant document with one findings block
    under each of three H2s would return 3 and be flagged. It also matches
    ``##`` as well as ``###``, so a stray ``## Codebase Research Findings``
    would register as a duplicate of a legitimate nested one.

    Slicing with :func:`_iter_h2_sections` and counting only ``###`` matches
    *within each slice* avoids both traps.
    """
    duplicates: list[str] = []
    for heading, start, end in _iter_h2_sections(content):
        count = len(_FINDINGS_H3_RE.findall(content[start:end]))
        if count > 1:
            duplicates.append(f"{heading} ({count})")
    return duplicates


# ENH-2995: closed detection list for the unmarked_superseded_directive gap
# class — mirrors the non-exhaustive LLM guidance in
# commands/refine-issue.md's Preservation Rule carve-out verbatim.
_SUPERSEDED_CORRECTION_PHRASES = (
    "is wrong",
    "does not exist",
    "will not work",
    "must be dropped",
    "target file is wrong",
    "is stale",
    "omit entirely",
)
_SUPERSEDED_DIRECTIVE_SECTIONS = ("Implementation Steps", "Files to Modify", "Acceptance Criteria")
_SUPERSEDED_MARKER_PREFIX = "⚠ Superseded"


def superseded_marker_count(issue_path: Path) -> int:
    """Count ``⚠ Superseded`` markers inside *issue_path*'s directive sections.

    ENH-2992: the public marker-*presence* surface. :func:`check_format_gaps`
    reports only the inverse (``unmarked_superseded_directive`` — correction
    language present, marker missing), which is a refine-did-not-mark defect.
    ``autodev.yaml``'s ``check_reconcile_needed`` needs the opposite signal:
    a marker standing in a directive section means this issue's own findings
    refute a directive line, which is exactly the condition
    ``/ll:reconcile-issue`` exists to clear.

    Scans only the three sections reconcile rewrites
    (:data:`_SUPERSEDED_DIRECTIVE_SECTIONS`), reusing
    :func:`_heading_bodies` and :data:`_SUPERSEDED_MARKER_PREFIX` verbatim so
    the presence query and the gap class can never disagree about what counts
    as a marker. Returns 0 for an unreadable or missing file — the FSM
    predicate that reads this must never fail the loop on a vanished issue.
    """
    try:
        content = issue_path.read_text()
    except OSError:
        return 0
    return sum(
        body.count(_SUPERSEDED_MARKER_PREFIX)
        for name in _SUPERSEDED_DIRECTIVE_SECTIONS
        for body in _heading_bodies(content, name)
    )


def _heading_bodies(content: str, heading: str) -> list[str]:
    """Return body text for every ``##``/``###`` occurrence of *heading*.

    Each body stops at the next heading of equal-or-higher level. Supports
    both levels since ``### Files to Modify`` is an H3 (nested under
    ``## Integration Map``) while ``## Implementation Steps`` and
    ``## Acceptance Criteria`` are H2 — unlike :func:`_section_body`, which
    only matches ``##``.
    """
    bodies: list[str] = []
    for match in re.finditer(rf"^(#{{2,3}})\s+{re.escape(heading)}\s*$", content, re.MULTILINE):
        level = len(match.group(1))
        start = match.end()
        next_match = re.search(rf"^#{{1,{level}}}\s", content[start:], re.MULTILINE)
        end = start + next_match.start() if next_match else len(content)
        bodies.append(content[start:end])
    return bodies


# Ported verbatim from skills/format-issue/SKILL.md's Testable Inference section
# (doc-only detection): 11 case-insensitive signal keywords; 2+ distinct matches
# is an advisory that the issue is documentation-only (testable: false candidate).
_TESTABLE_SIGNAL_KEYWORDS: tuple[str, ...] = (
    "doc",
    "docs",
    "documentation",
    "broken link",
    "broken anchor",
    "readme",
    "changelog",
    "spelling",
    "typo",
    "guide",
    "fix link",
)
_TESTABLE_KEYWORD_THRESHOLD = 2


def _count_testable_keyword_matches(text: str) -> int:
    """Count distinct `_TESTABLE_SIGNAL_KEYWORDS` present (case-insensitive) in *text*."""
    lowered = text.lower()
    return sum(1 for kw in _TESTABLE_SIGNAL_KEYWORDS if kw in lowered)


def infer_testable(issue: IssueInfo) -> bool:
    """Doc-only keyword inference: True when the issue looks documentation-only.

    Opt-in helper a caller can use to decide whether to write `testable: false`
    via `frontmatter.update_frontmatter` — not invoked automatically by
    `check_format_gaps`, which is a pure read-only linter. Mirrors the same
    2+-distinct-keyword-match rule as `check_format_gaps`'s `testable` gap.
    """
    from little_loops.frontmatter import strip_frontmatter as _strip

    body = issue.path.read_text(encoding="utf-8")
    scan_text = f"{issue.title}\n{_strip(body)}"
    return _count_testable_keyword_matches(scan_text) >= _TESTABLE_KEYWORD_THRESHOLD


# ENH-2443: deterministic (non-LLM) re-implementation of skills/decide-issue/SKILL.md
# Phase 3's Patterns 1-4, tried in precedence order (only the first tier with >=1 match
# counts). This is a cheap pre-check for FSM automation (ll-issues check-decidable), not
# a replacement for the skill's own extraction — approximate matches are fine here since
# an under-count only costs one harmless extra /ll:refine-issue detour, and an over-count
# just skips that optimization; `decide` itself remains the source of truth.
_OPTION_PATTERNS = (
    re.compile(r"^###\s+Option\s+[A-Za-z0-9]", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\*\*Option\s+[A-Za-z0-9]+.*?\*\*", re.MULTILINE),
    re.compile(r"^\d+\.\s+(?:\*\*Option|[A-Z][^.]*\bapproach\b)", re.MULTILINE),
    re.compile(
        r"^[-*]\s+(?:\([a-z0-9]\)\s+|\*{0,2}Option\s+[A-Za-z0-9])", re.MULTILINE | re.IGNORECASE
    ),
)

_OPTION_FALLBACK_SECTIONS = ("Codebase Research Findings", "Implementation Status")

# Names for the _OPTION_PATTERNS tiers, in the same precedence order, plus the
# non-regex Pattern E heuristic — reported as LocatedOptions.pattern (ENH-2950).
_OPTION_PATTERN_NAMES = ("section_header", "bold_label", "numbered", "bullet")


@dataclass
class LocatedOption:
    """One enumerable option span located by :func:`locate_enumerable_options` (ENH-2950)."""

    label: str
    text: str
    start_line: int
    end_line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "text": self.text,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


@dataclass
class LocatedOptions:
    """Result of :func:`locate_enumerable_options` (ENH-2950).

    Widens the original ``(count, heading)`` tuple to also carry which pattern
    tier fired and the per-option spans that tier's regex already computed
    internally — previously discarded by :func:`_count_options_in_text`.
    """

    count: int
    pattern: str | None
    heading: str | None
    options: list[LocatedOption] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "pattern": self.pattern,
            "heading": self.heading,
            "options": [o.to_dict() for o in self.options],
        }


def _count_options_in_text(text: str) -> int:
    """Count matches for the first pattern tier (in precedence order) that has any."""
    for pattern in _OPTION_PATTERNS:
        n = sum(1 for _ in pattern.finditer(text))
        if n:
            return n
    return 0


def _extract_option_label(match_text: str) -> str:
    """Strip markdown decoration from a matched option heading/marker to get a label."""
    label = match_text.strip()
    label = re.sub(r"^\d+\.\s*", "", label)
    label = re.sub(r"^[-*]\s*(?:\([a-z0-9]\)\s*)?", "", label)
    label = label.strip("#").strip()
    label = label.strip("*").strip()
    return label


def _locate_options_in_text(content: str, body: str, body_offset: int) -> LocatedOptions | None:
    """Return spans for the first :data:`_OPTION_PATTERNS` tier with a match in *body*.

    ``body_offset`` is *body*'s absolute start offset within *content*, used to
    translate each match's position into a 1-indexed line number in *content*.
    Returns None when no tier matches anywhere in *body*.
    """
    for pattern, pattern_name in zip(_OPTION_PATTERNS, _OPTION_PATTERN_NAMES, strict=True):
        matches = list(pattern.finditer(body))
        if not matches:
            continue
        options = []
        for i, m in enumerate(matches):
            line_start = body.rfind("\n", 0, m.start()) + 1
            if i + 1 < len(matches):
                block_end = body.rfind("\n", 0, matches[i + 1].start()) + 1
            else:
                block_end = len(body)
            block_text = body[line_start:block_end].rstrip()
            abs_start = body_offset + line_start
            abs_end = body_offset + max(block_end - 1, line_start)
            start_line = content.count("\n", 0, abs_start) + 1
            end_line = content.count("\n", 0, abs_end) + 1
            options.append(
                LocatedOption(
                    label=_extract_option_label(m.group(0)),
                    text=block_text,
                    start_line=start_line,
                    end_line=end_line,
                )
            )
        return LocatedOptions(
            count=len(options), pattern=pattern_name, heading=None, options=options
        )
    return None


def _iter_h2_sections(content: str) -> list[tuple[str, int, int]]:
    """Yield ``(heading_text, start, end)`` for each H2 section in *content*.

    A section's body spans to the next ``##`` line (or EOF), so it includes any
    nested H3 subsections — this is what lets the whole-document fallback (ENH-2821)
    find option blocks filed under an H3 nested inside an unrelated H2, or under an
    H2 with a decorated/suffixed heading, without needing a separate depth- or
    prefix-tolerant resolver.
    """
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", content, re.MULTILINE))
    sections = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections.append((m.group(1).strip(), start, end))
    return sections


# ENH-2936: Pattern E — un-preferenced decision directive. Mirrors
# skills/decide-issue/SKILL.md Phase 3b Provisional Pattern E: an issue can name 2+
# concrete alternatives plus an imperative to decide ("stamp it or move it to Out
# of scope — do not leave it unaddressed") without stating a preference. Pattern D
# (declarative recommendation) requires a stated preference, so this shape falls
# through every other tier — this heuristic closes that gap for the deterministic
# probe (ll-issues check-decidable) the same way the LLM skill's Pattern E does.
_DECIDE_IMPERATIVE_RE = re.compile(
    r"\bdecide before implementation\b"
    r"|\bdo not leave (?:it |this )?unaddressed\b"
    r"|\bpick one\b"
    r"|\bmust be decided\b"
    r"|\bdecision (?:needed|required) before\b",
    re.IGNORECASE,
)

# A stated preference disqualifies the passage from Pattern E — that shape is
# already Pattern D's job (declarative recommendation with a resolvable referent).
_PREFERENCE_MARKER_RE = re.compile(
    r"\*\*recommended\*\*"
    r"|\brecommendation is\b"
    r"|\bsupersedes\b"
    r"|\bleaning toward\b"
    r"|\bpreferred\b"
    r"|>\s*\*\*selected:\*\*",
    re.IGNORECASE,
)

_INLINE_OR_RE = re.compile(r"\bor\b", re.IGNORECASE)

# Sections where a "decide before implementation" imperative is written — narrower
# than Patterns A-D's whole-document scan (ENH-2936's Expected Behavior scope).
_DIRECTIVE_ALTERNATIVES_SECTIONS = (
    "Scope Boundaries",
    "Proposed Change",
    "Proposed Solution",
    "Open Questions",
)


def _locate_directive_alternatives(content: str) -> LocatedOptions | None:
    """Locate an un-preferenced decision directive (ENH-2936, Pattern E).

    A passage counts when an imperative decide-marker (:data:`_DECIDE_IMPERATIVE_RE`)
    and a 2+-alternative "X or Y" shape co-occur within 3 lines, with no stated
    preference marker (:data:`_PREFERENCE_MARKER_RE`) or resolved-question marker
    (:data:`_RESOLVED_QUESTION_MARKER_RE`) in that same window. Bare "X or Y" prose
    with no imperative marker never matches — that is the settled-informal-list case
    Pattern 4's auto-mode conservatism protects elsewhere.

    Each window is whitespace-normalized (lines joined with a single space) before
    matching, so a soft-wrapped marker or alternative split across lines by markdown's
    line length (e.g. "do not leave\n  it unaddressed") still matches — a per-line-only
    search would miss it.

    Returns:
        A ``LocatedOptions`` with ``count=2`` on a match — this heuristic only proves
        "a decision exists here", never how many alternatives, so a match always
        reports 2 (the minimum Phase 4 scoring requires). ``options`` holds a single
        ``LocatedOption`` spanning the matched window — the individual "X" / "Y"
        alternatives are not separated out (that would be a pattern-semantics change,
        out of scope for ENH-2950). ``None`` when nothing matches.
    """
    for heading in _DIRECTIVE_ALTERNATIVES_SECTIONS:
        result = _section_body_with_offset(content, heading)
        if result is None:
            continue
        body, body_offset = result
        if not body:
            continue
        lines = body.splitlines()
        line_offsets = []
        offset = 0
        for line in lines:
            line_offsets.append(offset)
            offset += len(line) + 1
        for i in range(len(lines)):
            lo, hi = max(0, i - 3), min(len(lines), i + 4)
            window = " ".join(" ".join(lines[lo:hi]).split())
            if not _DECIDE_IMPERATIVE_RE.search(window):
                continue
            if _PREFERENCE_MARKER_RE.search(window):
                continue
            if _RESOLVED_QUESTION_MARKER_RE.search(window):
                continue
            if _INLINE_OR_RE.search(window):
                window_start = body_offset + line_offsets[lo]
                window_end_line_idx = hi - 1
                window_end = (
                    body_offset
                    + line_offsets[window_end_line_idx]
                    + len(lines[window_end_line_idx])
                )
                start_line = content.count("\n", 0, window_start) + 1
                end_line = content.count("\n", 0, window_end) + 1
                window_text = "\n".join(lines[lo:hi])
                return LocatedOptions(
                    count=2,
                    pattern="provisional_e",
                    heading=heading,
                    options=[
                        LocatedOption(
                            label=heading,
                            text=window_text,
                            start_line=start_line,
                            end_line=end_line,
                        )
                    ],
                )
    return None


def locate_enumerable_options(content: str) -> LocatedOptions:
    """Locate enumerable option blocks anywhere in *content* (ENH-2821).

    Tries, in precedence order: (1) the scoped scan — ``## Proposed Solution``,
    then :data:`_OPTION_FALLBACK_SECTIONS` — matching :func:`count_enumerable_options`'s
    original behavior; (2) a whole-document fallback over every H2 section (which,
    by construction, includes nested H3 subsections and decorated/suffixed H2
    headings) when the scoped scan finds nothing; (3) the Pattern E directive-alternatives
    heuristic (:func:`_locate_directive_alternatives`, ENH-2936) when even the
    whole-document fallback finds nothing.

    Returns:
        A :class:`LocatedOptions`. ``heading`` is the exact H2/section name the
        options were found under, or ``None`` when ``count`` is 0 (nothing found
        anywhere in the document). ``pattern`` names which rule fired
        (``section_header`` | ``bold_label`` | ``numbered`` | ``bullet`` |
        ``provisional_e``), or ``None`` when ``count`` is 0. ``options`` carries the
        per-option spans the firing pattern computed (ENH-2950) — previously
        discarded by the tuple-returning predecessor of this function.
    """
    result = _section_body_with_offset(content, "Proposed Solution")
    if result is not None:
        body, body_offset = result
        located = _locate_options_in_text(content, body, body_offset)
        if located is not None:
            located.heading = "Proposed Solution"
            return located

    for heading in _OPTION_FALLBACK_SECTIONS:
        result = _section_body_with_offset(content, heading)
        if result is not None:
            body, body_offset = result
            located = _locate_options_in_text(content, body, body_offset)
            if located is not None:
                located.heading = heading
                return located

    best: LocatedOptions | None = None
    for heading_text, start, end in _iter_h2_sections(content):
        located = _locate_options_in_text(content, content[start:end], start)
        if located is not None and (best is None or located.count > best.count):
            located.heading = heading_text
            best = located
    if best is not None:
        return best

    directive = _locate_directive_alternatives(content)
    if directive is not None:
        return directive

    return LocatedOptions(count=0, pattern=None, heading=None, options=[])


def count_enumerable_options(content: str) -> int:
    """Count enumerable implementation options anywhere in an issue (ENH-2821).

    Widens to ## Codebase Research Findings / ## Implementation Status when Proposed
    Solution yields 0 (mirroring Phase 3's Pattern 4 note that refined issues often
    deposit options there instead), then to a whole-document scan when those also
    yield 0 — see :func:`locate_enumerable_options` for section attribution.
    """
    return locate_enumerable_options(content).count


# ENH-2446: coverage-aware variants used by ll-issues check-open-questions.
# A block in ## Proposed Solution is "resolved" if it carries a `> **Selected:**`
# callout OR a `### Decision Rationale` subsection (the two markers that
# /ll:decide-issue writes when it resolves an option). "Unresolved" = enumerable
# option block with neither marker — i.e. options that still need to be decided.

_RESOLVED_OPTION_MARKER_RE = re.compile(
    r"^\s*>\s+\*\*Selected:\*\*|^\s*###\s+Decision Rationale\b",
    re.MULTILINE,
)

# Pattern 1 + Pattern 2 headings: H3 "Option X" OR bold "**Option X: ...**" lines.
_OPTION_HEADING_RE = re.compile(
    r"^(?:###\s+Option\s+[A-Za-z0-9]|\*\*Option\s+[A-Za-z0-9]+)",
    re.MULTILINE | re.IGNORECASE,
)


def _iter_option_blocks(text: str) -> list[tuple[str, str]]:
    """Yield ``(heading_line, block_body)`` for each ``### Option X`` / ``**Option X:**`` block in *text*.

    Boundary = next ``###``, ``##``, or ``**Option`` line at the same or shallower
    level. Patterns 1-2 from :data:`_OPTION_PATTERNS` (skipping the more approximate
    Patterns 3-4 so the coverage-aware probe stays conservative).
    """
    if not text:
        return []
    blocks: list[tuple[str, str]] = []
    matches = list(_OPTION_HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        line_start = text.rfind("\n", 0, start) + 1
        blocks.append((text[line_start:start].strip(), text[start:end]))
    return blocks


def _is_option_resolved(block_body: str) -> bool:
    """Return True if *block_body* contains a `> **Selected:**` or `### Decision Rationale`."""
    return bool(_RESOLVED_OPTION_MARKER_RE.search(block_body))


def locate_unresolved_options(content: str) -> tuple[int, str | None]:
    """Locate unresolved option blocks anywhere in *content* (ENH-2821).

    Mirrors :func:`locate_enumerable_options`'s precedence: scoped sections first
    (``## Proposed Solution`` then :data:`_OPTION_FALLBACK_SECTIONS`), falling back
    to a whole-document scan (which covers nested H3s and decorated H2 headings)
    only when the scoped sections carry no option blocks at all — resolved or not.

    Return-shape note (ENH-2950): unlike its sibling, this function still returns
    the original ``(count, heading)`` tuple — it was not widened to ``LocatedOptions``.
    Do not assume the two functions are interchangeable beyond precedence semantics.

    Returns:
        ``(unresolved_count, containing_heading)``. ``containing_heading`` names the
        first scoped section carrying any option block, or the whole-document
        fallback's first H2 section carrying one; ``None`` when no option block
        exists anywhere in the document.
    """
    sections = ["Proposed Solution", *_OPTION_FALLBACK_SECTIONS]
    unresolved = 0
    found_heading: str | None = None
    for heading in sections:
        body = _section_body(content, heading) or ""
        blocks = _iter_option_blocks(body)
        if blocks and found_heading is None:
            found_heading = heading
        for _, block in blocks:
            if not _is_option_resolved(block):
                unresolved += 1
    if found_heading is not None:
        return unresolved, found_heading

    for heading_text, start, end in _iter_h2_sections(content):
        blocks = _iter_option_blocks(content[start:end])
        if not blocks:
            continue
        total = sum(1 for _, block in blocks if not _is_option_resolved(block))
        return total, heading_text

    return 0, None


def count_unresolved_options(content: str) -> int:
    """Count enumerable option blocks lacking a `> **Selected:**` or `### Decision Rationale` marker (ENH-2446).

    Mirrors :func:`count_enumerable_options` for section selection (Proposed Solution
    primary, fallback to ``_OPTION_FALLBACK_SECTIONS``, then a whole-document scan —
    ENH-2821), but only counts Pattern 1 + Pattern 2 blocks and filters those that
    lack a resolution marker. An issue with resolved options PLUS unresolved open
    questions (free-form in ``## Edge Cases`` etc.) is the coverage gap this probe
    catches.

    Return-shape note (ENH-2950): ``count_enumerable_options`` now reads ``.count``
    off a ``LocatedOptions``; this function's own ``count_unresolved_options``
    caller below still unpacks a plain ``(count, heading)`` tuple from
    :func:`locate_unresolved_options`, which was not widened.
    """
    count, _ = locate_unresolved_options(content)
    return count


# Resolved-question markers — same vocabulary as skills/decide-issue/SKILL.md:197
# (ENH-2446 explicitly mirrors that regex to keep the deterministic probe and the
# LLM skill reading the same markers).
_RESOLVED_QUESTION_MARKER_RE = re.compile(
    r"(?:✅|✔)\s*RESOLVED"
    r"|>\s*\*\*RESOLVED\*\*"
    r"|\*\*RESOLVED\*\*",
    re.IGNORECASE,
)

# Open-question signals — a bullet/numbered item is "an open question" if it carries
# any of these. Mirrors the confidence-check signal phrases from
# skills/confidence-check/SKILL.md:356-371 and the canonical "Q:" / "?" patterns.
_OPEN_QUESTION_SIGNAL_RE = re.compile(
    r"\?\s*$"  # ends with question mark
    r"|^\s*-\s*\*\*Q\d*"  # **Q1.** style
    r"|^\s*-\s*Q:"  # Q: prefix
    r"|\bopen question\b"
    r"|\bneeds decision\b"
    r"|\bdecision needed\b"
    r"|\bopen decision\b"
    r"|\bunresolved decision\b"
    r"|\bdecision point\b",
    re.IGNORECASE,
)


_OPEN_QUESTION_SECTIONS = ("Edge Cases", "Confidence Check Notes", "Open Questions")


def _count_unresolved_items_in_text(text: str) -> int:
    """Count bullet/numbered items carrying an open-question signal and NOT a RESOLVED marker."""
    if not text:
        return 0
    unresolved = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        is_item = stripped.startswith(("-", "*")) or (
            len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in (".", ")")
        )
        if not is_item:
            continue
        if _RESOLVED_QUESTION_MARKER_RE.search(stripped):
            continue
        if not _OPEN_QUESTION_SIGNAL_RE.search(stripped):
            continue
        unresolved += 1
    return unresolved


def count_open_questions_in_sections(content: str) -> int:
    """Count unresolved open questions in ``## Edge Cases``, ``## Confidence Check Notes``, ``## Open Questions`` (ENH-2446).

    Mirror of :func:`count_enumerable_options` (section-scoped, deprecated-aware
    via :func:`_section_body`'s heading matching). Items prefixed with
    ``✅ RESOLVED`` / ``✔ RESOLVED`` / ``**RESOLVED**`` / ``> **RESOLVED**`` are
    excluded — same vocabulary as :func:`skills/decide-issue/SKILL.md` Phase 3b-i.
    """
    total = 0
    for heading in _OPEN_QUESTION_SECTIONS:
        body = _section_body(content, heading)
        if body:
            total += _count_unresolved_items_in_text(body)
    return total


def slugify(text: str) -> str:
    """Convert text to slug format for filenames.

    Args:
        text: Text to convert

    Returns:
        Lowercase slug with hyphens
    """
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-").lower()


def get_next_issue_number(config: BRConfig, category: str | None = None) -> int:
    """Determine the next globally unique issue number.

    Scans ALL issue directories (active and completed) to find the highest
    existing number across ALL issue types (BUG, FEAT, ENH). Issue numbers
    are globally unique regardless of type.

    Args:
        config: Project configuration
        category: Unused, kept for backwards compatibility

    Returns:
        Next available issue number (globally unique across all types)
    """
    max_num = 0

    # Get all known prefixes from configuration
    all_prefixes = [cat_config.prefix for cat_config in config.issues.categories.values()]

    # Directories to scan: ALL category directories. Status (open/done/deferred)
    # now lives in frontmatter, so all issues — active and inactive — are in
    # their type dir. We still scan the legacy completed/ and deferred/ dirs
    # if they happen to exist (in-flight migration safety).
    dirs_to_scan: list[Path] = []
    for cat_name in config.issues.categories:
        dirs_to_scan.append(config.get_issue_dir(cat_name))
    legacy_completed = config.project_root / config.issues.base_dir / "completed"
    legacy_deferred = config.project_root / config.issues.base_dir / "deferred"
    if legacy_completed.exists():
        dirs_to_scan.append(legacy_completed)
    if legacy_deferred.exists():
        dirs_to_scan.append(legacy_deferred)

    if not all_prefixes:
        return max_num + 1

    # Pre-compile a single union regex to match any known prefix
    prefix_pattern = re.compile(r"(?:" + "|".join(re.escape(p) for p in all_prefixes) + r")-(\d+)")

    for dir_path in dirs_to_scan:
        if not dir_path.exists():
            continue
        for file in dir_path.glob("*.md"):
            match = prefix_pattern.search(file.name)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num

    return max_num + 1


@dataclass
class ProductImpact:
    """Product impact assessment for an issue.

    Attributes:
        goal_alignment: ID of the strategic priority this supports
        persona_impact: ID of the persona affected
        business_value: Business value assessment (high|medium|low)
        user_benefit: Description of how this helps the target user
    """

    goal_alignment: str | None = None
    persona_impact: str | None = None
    business_value: str | None = None  # high|medium|low
    user_benefit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "goal_alignment": self.goal_alignment,
            "persona_impact": self.persona_impact,
            "business_value": self.business_value,
            "user_benefit": self.user_benefit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ProductImpact | None:
        """Create ProductImpact from dictionary.

        Args:
            data: Dictionary with product impact fields, or None

        Returns:
            ProductImpact instance or None if data is None/empty
        """
        if not data:
            return None
        return cls(
            goal_alignment=data.get("goal_alignment"),
            persona_impact=data.get("persona_impact"),
            business_value=data.get("business_value"),
            user_benefit=data.get("user_benefit"),
        )


@dataclass
class CriterionSlot:
    """One extracted top-level bullet from an issue's criteria section (FEAT-2948).

    Consumed by ``ll-loop scaffold-verify`` to build one verification state per
    criterion; ``state_name`` is the FSM state the scaffold will emit.
    """

    index: int
    source_text: str
    state_name: str


@dataclass
class IssueInfo:
    """Parsed information from an issue file.

    Attributes:
        path: Path to the issue file
        issue_type: Type of issue (e.g., "bugs", "features")
        priority: Priority level (e.g., "P0", "P1")
        issue_id: Issue identifier (e.g., "BUG-123")
        title: Issue title from markdown header
        blocked_by: List of issue IDs that block this issue
        blocks: List of issue IDs that this issue blocks
        discovered_by: Source command/workflow that created this issue
        product_impact: Product impact assessment (optional)
        effort: Effort estimate (1=low, 2=medium, 3=high), inferred from priority if absent
        impact: Impact estimate (1=low, 2=medium, 3=high), inferred from priority if absent
        confidence_score: Readiness score (0-100) written by /ll:confidence-check, or None
        outcome_confidence: Outcome confidence (0-100) written by /ll:confidence-check, or None
        score_complexity: Outcome criterion A – Complexity (0-25), written by /ll:confidence-check, or None
        score_test_coverage: Outcome criterion B – Test Coverage (0-25), written by /ll:confidence-check, or None
        score_ambiguity: Outcome criterion C – Ambiguity (0-25), written by /ll:confidence-check, or None
        score_change_surface: Outcome criterion D – Change Surface (0-25), written by /ll:confidence-check, or None
        testable: Whether TDD phase should be applied; False skips TDD, None treated as testable
        session_commands: Distinct /ll:* commands found in the ## Session Log section
        session_command_counts: Per-command occurrence counts from the ## Session Log section
        labels: Labels extracted from the ## Labels section of the issue file
        milestone: Sprint or milestone name this issue is assigned to; None if unassigned
        status: Issue lifecycle status read from frontmatter; defaults to "open"
        parent: Parent issue ID (e.g., EPIC-123); populated from frontmatter `parent:` or deprecated `parent_issue:`
        base_branch: For EPIC issues, the branch its integration branch forks from; populated from
            frontmatter `base_branch:` or alias `target_branch:`. None means fall back to the global
            `parallel.base_branch` (FEAT-2652).
        depends_on: List of issue IDs this issue depends on (soft prerequisite)
        relates_to: List of related issue IDs; populated from frontmatter `relates_to:` or deprecated `related:`
        duplicate_of: Issue ID that this issue duplicates
        supersedes: List of issue IDs this issue supersedes/replaces; populated from frontmatter `supersedes:`
    """

    path: Path
    issue_type: str
    priority: str
    issue_id: str
    title: str
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    parent: str | None = None
    base_branch: str | None = None
    depends_on: list[str] = field(default_factory=list)
    relates_to: list[str] = field(default_factory=list)
    duplicate_of: str | None = None
    supersedes: list[str] = field(default_factory=list)
    discovered_by: str | None = None
    epic: str | None = None
    product_impact: ProductImpact | None = None
    effort: int | None = None
    impact: int | None = None
    confidence_score: int | None = None
    outcome_confidence: int | None = None
    score_complexity: int | None = None
    score_test_coverage: int | None = None
    score_ambiguity: int | None = None
    score_change_surface: int | None = None
    size: str | None = None
    testable: bool | None = None
    decision_needed: bool | None = None
    missing_artifacts: bool | None = None
    implementation_order_risk: bool | None = None
    learning_tests_required: list[str] | None = None
    session_commands: list[str] = field(default_factory=list)
    session_command_counts: dict[str, int] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)
    milestone: str | None = None
    status: str = "open"

    @property
    def priority_int(self) -> int:
        """Convert priority to integer for comparison (lower = higher priority)."""
        # Support P0-P5 priorities
        match = re.match(r"^P(\d+)$", self.priority)
        if match:
            return int(match.group(1))
        return 99  # Unknown priority sorts last

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "path": str(self.path),
            "issue_type": self.issue_type,
            "priority": self.priority,
            "issue_id": self.issue_id,
            "title": self.title,
            "blocked_by": self.blocked_by,
            "blocks": self.blocks,
            "parent": self.parent,
            "depends_on": self.depends_on,
            "relates_to": self.relates_to,
            "duplicate_of": self.duplicate_of,
            "supersedes": self.supersedes,
            "discovered_by": self.discovered_by,
            "epic": self.epic,
            "product_impact": (self.product_impact.to_dict() if self.product_impact else None),
            "effort": self.effort,
            "impact": self.impact,
            "confidence_score": self.confidence_score,
            "outcome_confidence": self.outcome_confidence,
            "score_complexity": self.score_complexity,
            "score_test_coverage": self.score_test_coverage,
            "score_ambiguity": self.score_ambiguity,
            "score_change_surface": self.score_change_surface,
            "size": self.size,
            "testable": self.testable,
            "decision_needed": self.decision_needed,
            "missing_artifacts": self.missing_artifacts,
            "implementation_order_risk": self.implementation_order_risk,
            "learning_tests_required": self.learning_tests_required,
            "session_commands": self.session_commands,
            "session_command_counts": self.session_command_counts,
            "labels": self.labels,
            "milestone": self.milestone,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IssueInfo:
        """Create IssueInfo from dictionary."""
        return cls(
            path=Path(data["path"]),
            issue_type=data["issue_type"],
            priority=data["priority"],
            issue_id=data["issue_id"],
            title=data["title"],
            blocked_by=data.get("blocked_by", []),
            blocks=data.get("blocks", []),
            parent=data.get("parent"),
            depends_on=data.get("depends_on", []),
            relates_to=data.get("relates_to", []),
            duplicate_of=data.get("duplicate_of"),
            supersedes=data.get("supersedes", []),
            discovered_by=data.get("discovered_by"),
            epic=data.get("epic"),
            product_impact=ProductImpact.from_dict(data.get("product_impact")),
            effort=data.get("effort"),
            impact=data.get("impact"),
            confidence_score=data.get("confidence_score"),
            outcome_confidence=data.get("outcome_confidence"),
            score_complexity=data.get("score_complexity"),
            score_test_coverage=data.get("score_test_coverage"),
            score_ambiguity=data.get("score_ambiguity"),
            score_change_surface=data.get("score_change_surface"),
            size=data.get("size"),
            testable=data.get("testable"),
            decision_needed=data.get("decision_needed"),
            missing_artifacts=data.get("missing_artifacts"),
            implementation_order_risk=data.get("implementation_order_risk"),
            learning_tests_required=data.get("learning_tests_required"),
            session_commands=data.get("session_commands", []),
            session_command_counts=data.get("session_command_counts", {}),
            labels=data.get("labels", []),
            milestone=data.get("milestone"),
            status=data.get("status", "open"),
        )


class IssueParser:
    """Parses issue files based on project configuration.

    Uses BRConfig to understand issue categories, prefixes, and priorities.
    """

    def __init__(self, config: BRConfig) -> None:
        """Initialize parser with project configuration.

        Args:
            config: Project configuration
        """
        self.config = config
        self._build_prefix_map()

    def _build_prefix_map(self) -> None:
        """Build mapping from issue prefixes to category names."""
        self._prefix_to_category: dict[str, str] = {}
        for category_name, category in self.config.issues.categories.items():
            self._prefix_to_category[category.prefix] = category_name

    def parse_file(self, issue_path: Path) -> IssueInfo:
        """Parse an issue file to extract metadata.

        Args:
            issue_path: Path to the issue markdown file

        Returns:
            Parsed IssueInfo
        """
        filename = issue_path.name

        # Parse priority from filename prefix (e.g., P1-BUG-123-...)
        priority = self._parse_priority(filename)

        # Parse issue type and ID from filename
        issue_type, issue_id = self._parse_type_and_id(filename, issue_path)

        # Read content once for all content-based parsing
        content = self._read_content(issue_path)

        # Parse frontmatter for discovered_by, epic, product impact, effort, and impact
        frontmatter = parse_frontmatter(content)
        discovered_by = frontmatter.get("discovered_by")
        epic = frontmatter.get("epic")
        size = frontmatter.get("size")
        product_impact = self._parse_product_impact(frontmatter)
        effort_raw = frontmatter.get("effort")
        impact_raw = frontmatter.get("impact")
        effort = int(effort_raw) if effort_raw is not None and str(effort_raw).isdigit() else None
        impact = int(impact_raw) if impact_raw is not None and str(impact_raw).isdigit() else None
        confidence_raw = frontmatter.get("confidence_score")
        outcome_raw = frontmatter.get("outcome_confidence")
        confidence_score = (
            int(confidence_raw)
            if confidence_raw is not None and str(confidence_raw).isdigit()
            else None
        )
        outcome_confidence = (
            int(outcome_raw) if outcome_raw is not None and str(outcome_raw).isdigit() else None
        )
        complexity_raw = frontmatter.get("score_complexity")
        test_coverage_raw = frontmatter.get("score_test_coverage")
        ambiguity_raw = frontmatter.get("score_ambiguity")
        change_surface_raw = frontmatter.get("score_change_surface")
        score_complexity = (
            int(complexity_raw)
            if complexity_raw is not None and str(complexity_raw).isdigit()
            else None
        )
        score_test_coverage = (
            int(test_coverage_raw)
            if test_coverage_raw is not None and str(test_coverage_raw).isdigit()
            else None
        )
        score_ambiguity = (
            int(ambiguity_raw)
            if ambiguity_raw is not None and str(ambiguity_raw).isdigit()
            else None
        )
        score_change_surface = (
            int(change_surface_raw)
            if change_surface_raw is not None and str(change_surface_raw).isdigit()
            else None
        )
        testable_raw = frontmatter.get("testable")
        if isinstance(testable_raw, str):
            testable_value: bool | None = (
                testable_raw.lower() == "true"
                if testable_raw.lower() in ("true", "false")
                else None
            )
        else:
            testable_value = testable_raw

        decision_needed_raw = frontmatter.get("decision_needed")
        if isinstance(decision_needed_raw, str):
            decision_needed_value: bool | None = (
                decision_needed_raw.lower() == "true"
                if decision_needed_raw.lower() in ("true", "false")
                else None
            )
        else:
            decision_needed_value = decision_needed_raw

        missing_artifacts_raw = frontmatter.get("missing_artifacts")
        if isinstance(missing_artifacts_raw, str):
            missing_artifacts_value: bool | None = (
                missing_artifacts_raw.lower() == "true"
                if missing_artifacts_raw.lower() in ("true", "false")
                else None
            )
        else:
            missing_artifacts_value = missing_artifacts_raw

        implementation_order_risk_raw = frontmatter.get("implementation_order_risk")
        if isinstance(implementation_order_risk_raw, str):
            implementation_order_risk_value: bool | None = (
                implementation_order_risk_raw.lower() == "true"
                if implementation_order_risk_raw.lower() in ("true", "false")
                else None
            )
        else:
            implementation_order_risk_value = implementation_order_risk_raw

        learning_tests_raw = frontmatter.get("learning_tests_required")
        if isinstance(learning_tests_raw, str):
            learning_tests_required_value: list[str] | None = [
                t.strip() for t in learning_tests_raw.split(",") if t.strip()
            ] or None
        elif isinstance(learning_tests_raw, list):
            learning_tests_required_value = [str(t) for t in learning_tests_raw] or None
        else:
            learning_tests_required_value = None

        status = frontmatter.get("status", "open")
        if status == "open" and frontmatter.get("completed_at"):
            status = "done"

        parent = frontmatter.get("parent")
        if parent is None and (alias_val := frontmatter.get("parent_issue")):
            _warn_deprecated_key(issue_path, "parent_issue", "parent")
            parent = alias_val

        base_branch = frontmatter.get("base_branch")
        if base_branch is None and (alias_val := frontmatter.get("target_branch")):
            _warn_deprecated_key(issue_path, "target_branch", "base_branch")
            base_branch = alias_val

        duplicate_of = frontmatter.get("duplicate_of")

        relates_to: list[str] = []
        if alias_val := frontmatter.get("related"):
            _warn_deprecated_key(issue_path, "related", "relates_to")
            relates_to = (
                [id.strip() for id in alias_val.strip("\"'").split(",") if id.strip()]
                if isinstance(alias_val, str)
                else list(alias_val)
            )

        depends_on: list[str] = []
        supersedes: list[str] = []

        # Parse title: prefer frontmatter title: field, then markdown header, then filename stem
        title = frontmatter.get("title") or self._parse_title_from_content(content, issue_path)
        blocked_by = self._parse_blocked_by(content)
        blocks = self._parse_blocks(content)

        # Also read blocked_by/blocks/depends_on/relates_to from frontmatter (canonical format).
        # When both sources provide values and they differ, prefer frontmatter and warn
        # so stale body sections are surfaced rather than silently merged.
        for fm_key, body_ids in (
            ("blocked_by", blocked_by),
            ("blocks", blocks),
            ("depends_on", depends_on),
            ("relates_to", relates_to),
            ("supersedes", supersedes),
        ):
            fm_val = frontmatter.get(fm_key)
            if not fm_val:
                continue
            fm_ids = (
                [id.strip() for id in fm_val.strip("\"'").split(",") if id.strip()]
                if isinstance(fm_val, str)
                else list(fm_val)
            )
            if body_ids and set(fm_ids) != set(body_ids):
                logger.warning(
                    "%s: frontmatter %s %s conflicts with body section %s; "
                    "preferring frontmatter — update or remove the stale body section",
                    issue_path.name,
                    fm_key,
                    fm_ids,
                    body_ids,
                )
                body_ids.clear()
                body_ids.extend(fm_ids)
            elif not body_ids:
                body_ids.extend(fm_ids)

        # Parse labels from frontmatter
        labels: list[str] = []
        fm_labels = frontmatter.get("labels")
        if fm_labels:
            if isinstance(fm_labels, str):
                labels = [lb.strip() for lb in fm_labels.split(",") if lb.strip()]
            else:
                labels = [str(lb) for lb in fm_labels]

        # Parse milestone from frontmatter
        milestone: str | None = frontmatter.get("milestone") or None

        # Parse session commands from ## Session Log section
        from little_loops.session_log import count_session_commands, parse_session_log

        session_commands = parse_session_log(content)
        session_command_counts = count_session_commands(content)

        return IssueInfo(
            path=issue_path,
            issue_type=issue_type,
            priority=priority,
            issue_id=issue_id,
            title=title,
            blocked_by=blocked_by,
            blocks=blocks,
            parent=parent,
            base_branch=base_branch,
            depends_on=depends_on,
            relates_to=relates_to,
            duplicate_of=duplicate_of,
            supersedes=supersedes,
            discovered_by=discovered_by,
            epic=epic,
            product_impact=product_impact,
            effort=effort,
            impact=impact,
            confidence_score=confidence_score,
            outcome_confidence=outcome_confidence,
            score_complexity=score_complexity,
            score_test_coverage=score_test_coverage,
            score_ambiguity=score_ambiguity,
            score_change_surface=score_change_surface,
            size=size,
            testable=testable_value,
            decision_needed=decision_needed_value,
            missing_artifacts=missing_artifacts_value,
            implementation_order_risk=implementation_order_risk_value,
            learning_tests_required=learning_tests_required_value,
            session_commands=session_commands,
            session_command_counts=session_command_counts,
            labels=labels,
            milestone=milestone,
            status=status,
        )

    def _parse_priority(self, filename: str) -> str:
        """Extract priority from filename.

        Args:
            filename: Issue filename

        Returns:
            Priority string (e.g., "P1") or last priority if not found
        """
        for priority in self.config.issue_priorities:
            if filename.startswith(f"{priority}-"):
                return priority
        # Default to lowest priority if not found
        return self.config.issue_priorities[-1] if self.config.issue_priorities else "P3"

    def _get_category_for_prefix(self, prefix: str) -> str:
        """Get category name from issue prefix.

        Args:
            prefix: Issue prefix (e.g., "BUG", "FEAT")

        Returns:
            Category name (e.g., "bugs", "features"), defaults to "bugs"
        """
        return self._prefix_to_category.get(prefix, "bugs")

    def _parse_type_and_id(self, filename: str, issue_path: Path) -> tuple[str, str]:
        """Extract issue type and ID from filename.

        Args:
            filename: Issue filename
            issue_path: Full path to issue file

        Returns:
            Tuple of (issue_type, issue_id)
        """
        # Try to match known prefixes (BUG, FEAT, ENH, etc.)
        for prefix, category in self._prefix_to_category.items():
            pattern = rf"({prefix})-(\d+)"
            match = re.search(pattern, filename)
            if match:
                issue_id = f"{match.group(1)}-{match.group(2)}"
                return category, issue_id

        # Fall back to inferring category from directory.
        parent_name = issue_path.parent.name
        for category_name, category_config in self.config.issues.categories.items():
            if parent_name == category_config.dir:
                # If the filename uses the standard P[0-5]-NNN-... shape but
                # omits the type token, capture the number directly and pair
                # it with the directory-derived prefix. Without this, generic
                # number scanning would pick up the priority digit instead.
                priority_match = re.match(r"^P\d+-(\d+)(?:[-.]|$)", filename)
                if priority_match:
                    return category_name, f"{category_config.prefix}-{priority_match.group(1)}"
                issue_id = self._generate_id_from_filename(filename, category_config.prefix)
                return category_name, issue_id

        # Last resort: use filename as ID
        return "bugs", filename.replace(".md", "")

    def _generate_id_from_filename(self, filename: str, prefix: str) -> str:
        """Generate an issue ID from filename when not explicitly present.

        Args:
            filename: Issue filename
            prefix: Issue prefix to use

        Returns:
            Generated issue ID
        """
        # Strip a leading priority token (e.g. "P2-") so it does not get
        # picked up as the issue number by the generic digit scan below.
        scan_target = re.sub(r"^P\d+-", "", filename)
        numbers = re.findall(r"\d+", scan_target)
        if numbers:
            return f"{prefix}-{numbers[0]}"
        # Use next sequential number instead of hash-based fallback
        # This ensures IDs are deterministic and don't collide with existing issues
        category = self._get_category_for_prefix(prefix)
        next_num = get_next_issue_number(self.config, category)
        return f"{prefix}-{next_num:03d}"

    def _read_content(self, issue_path: Path) -> str:
        """Read file content, returning empty string on error.

        Args:
            issue_path: Path to issue file

        Returns:
            File content or empty string on error
        """
        try:
            return issue_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read %s: %s", issue_path.name, e)
            return ""

    def _parse_title_from_content(self, content: str, issue_path: Path) -> str:
        """Extract title from issue file content.

        Args:
            content: Pre-read file content
            issue_path: Path to issue file (for fallback)

        Returns:
            Issue title or filename stem as fallback
        """
        if content:
            # Look for markdown header: # ISSUE-ID: Title
            match = re.search(r"^#\s+[\w-]+:\s*(.+)$", content, re.MULTILINE)
            if match:
                return match.group(1).strip()
            # Try first header of any format
            match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if match:
                return match.group(1).strip()
        # Fall back to filename
        return issue_path.stem

    def _parse_section_items(self, content: str, section_name: str) -> list[str]:
        """Extract issue IDs from a markdown section.

        Finds section header (## Section Name) and extracts issue IDs
        from list items until the next section or end of file.
        Skips content inside code fences.

        Args:
            content: File content to parse
            section_name: Section name to find (e.g., "Blocked By")

        Returns:
            List of issue IDs found in the section
        """
        if not content:
            return []

        # Strip code fences to avoid matching sections in examples
        content_without_code = self._strip_code_fences(content)

        # Match section header case-insensitively
        section_pattern = rf"^##\s+{re.escape(section_name)}\s*$"
        match = re.search(section_pattern, content_without_code, re.MULTILINE | re.IGNORECASE)
        if not match:
            return []

        # Get content after section header until next ## header or end
        start = match.end()
        next_section = re.search(r"^##\s+", content_without_code[start:], re.MULTILINE)
        if next_section:
            section_content = content_without_code[start : start + next_section.start()]
        else:
            section_content = content_without_code[start:]

        # Extract issue IDs from list items
        issue_ids = ISSUE_ID_PATTERN.findall(section_content)
        return issue_ids

    def extract_criteria(self, issue_path: Path) -> list[CriterionSlot]:
        """Extract ordered top-level criteria bullets for ``ll-loop scaffold-verify`` (FEAT-2948).

        Generalizes ``_parse_section_items()``'s section-location logic (header
        regex, slice to next ``## `` header, code-fence stripping) but extracts
        bullet text instead of issue IDs. Tries ``## Acceptance Criteria`` first;
        falls back to ``## Expected Behavior`` when Acceptance Criteria is absent
        or yields no top-level bullets (the primary/fallback rule the Program
        Design calls out). Sub-bullets (indented items) are skipped — only
        column-0 bullets count, per skills/verify-issue-loop/SKILL.md:129-135.

        Args:
            issue_path: Path to the issue markdown file.

        Returns:
            Ordered ``CriterionSlot`` list (1-indexed), or ``[]`` if neither
            section has usable bullets.
        """
        content = self._read_content(issue_path)
        if not content:
            return []

        content_without_code = self._strip_code_fences(content)

        for section_name in _CRITERIA_SECTION_NAMES:
            section_pattern = rf"^##\s+{re.escape(section_name)}\s*$"
            match = re.search(section_pattern, content_without_code, re.MULTILINE | re.IGNORECASE)
            if not match:
                continue

            start = match.end()
            next_section = re.search(r"^##\s+", content_without_code[start:], re.MULTILINE)
            section_content = (
                content_without_code[start : start + next_section.start()]
                if next_section
                else content_without_code[start:]
            )

            bullets: list[str] = []
            for line in section_content.splitlines():
                if not line.strip():
                    continue
                bullet_match = _CRITERION_BULLET_PATTERN.match(line)
                if bullet_match:
                    bullets.append(bullet_match.group(1).strip())

            if bullets:
                return [
                    CriterionSlot(
                        index=i,
                        source_text=text,
                        state_name=f"verify-criterion-{i}",
                    )
                    for i, text in enumerate(bullets, start=1)
                ]

        return []

    def _strip_code_fences(self, content: str) -> str:
        """Remove code fence blocks from content.

        Replaces content between ``` markers with empty lines to preserve
        line numbers while removing code fence content from parsing.

        Args:
            content: File content

        Returns:
            Content with code fence blocks replaced by empty lines
        """
        # Match code fences: ``` or ```language through closing ```
        result = []
        in_fence = False
        for line in content.split("\n"):
            if line.startswith("```"):
                in_fence = not in_fence
                result.append("")  # Preserve line count
            elif in_fence:
                result.append("")  # Replace fenced content with empty line
            else:
                result.append(line)
        return "\n".join(result)

    def _parse_blocked_by(self, content: str) -> list[str]:
        """Extract issue IDs from ## Blocked By section.

        Args:
            content: File content to parse

        Returns:
            List of issue IDs that block this issue
        """
        return self._parse_section_items(content, "Blocked By")

    def _parse_blocks(self, content: str) -> list[str]:
        """Extract issue IDs from ## Blocks section.

        Args:
            content: File content to parse

        Returns:
            List of issue IDs that this issue blocks
        """
        return self._parse_section_items(content, "Blocks")

    def _parse_product_impact(self, frontmatter: dict[str, Any]) -> ProductImpact | None:
        """Extract product impact from frontmatter.

        Args:
            frontmatter: Dictionary of frontmatter fields

        Returns:
            ProductImpact instance if any product fields are present, None otherwise
        """
        # Check if any product fields are present
        product_fields = ("goal_alignment", "persona_impact", "business_value", "user_benefit")
        if not any(frontmatter.get(key) for key in product_fields):
            return None

        return ProductImpact(
            goal_alignment=frontmatter.get("goal_alignment"),
            persona_impact=frontmatter.get("persona_impact"),
            business_value=frontmatter.get("business_value"),
            user_benefit=frontmatter.get("user_benefit"),
        )


def find_issues(
    config: BRConfig,
    category: str | None = None,
    skip_ids: set[str] | None = None,
    only_ids: list[str] | set[str] | None = None,
    type_prefixes: set[str] | None = None,
    status_filter: set[str] | None = None,
    *,
    skip_blocked: bool = False,
) -> list[IssueInfo]:
    """Find all issues matching criteria.

    Args:
        config: Project configuration
        category: Optional category to filter (e.g., "bugs")
        skip_ids: Issue IDs to skip
        only_ids: If provided, only include these issue IDs. When a list,
            results are returned in list order (input sequence preserved).
            When a set, results are sorted by priority as usual.
        type_prefixes: If provided, only include issues whose ID starts with
            one of these prefixes (e.g., {"BUG", "ENH"})
        status_filter: If provided, only include issues whose status is in this
            set. When None (default), skips done/cancelled/deferred issues
            (preserves all existing caller behaviour).
        skip_blocked: Keyword-only. When True, exclude issues with an
            unresolved `blocked_by` edge (a blocker not yet done/cancelled)
            from the returned list. Default False is byte-identical to prior
            behaviour — no existing caller is affected.

    Returns:
        List of IssueInfo sorted by priority, or in only_ids list order when
        only_ids is a list
    """
    skip_ids = skip_ids or set()
    parser = IssueParser(config)
    issues: list[IssueInfo] = []

    # Determine which categories to search
    if category:
        categories = [category] if category in config.issue_categories else []
    else:
        categories = config.issue_categories

    def _matches_status(info: IssueInfo, status_filter: set[str] | None) -> bool:
        if status_filter is None:
            return info.status not in ("done", "cancelled", "deferred")
        return info.status in status_filter

    def _matches_filters(info: IssueInfo) -> bool:
        if info.issue_id in skip_ids:
            return False
        if only_ids is not None and not any(_id_matches(info.issue_id, p) for p in only_ids):
            return False
        if type_prefixes is not None:
            prefix = info.issue_id.split("-", 1)[0]
            if prefix not in type_prefixes:
                return False
        return True

    if skip_blocked:
        from little_loops.dependency_graph import DependencyGraph
        from little_loops.issue_progress import _ALL_STATUSES, _TERMINAL_STATUSES

        # Single unfiltered non-terminal parse pass over every category (the
        # superset the graph needs regardless of this call's category/type/
        # skip/only filters, so a blocker outside the requested slice is
        # still correctly recognized as blocking or resolved). The outer
        # call's `issues` result is then derived from this same superset in
        # memory instead of re-walking the directory a second time.
        non_terminal = _ALL_STATUSES - _TERMINAL_STATUSES
        requested_categories = set(categories)
        all_active: list[IssueInfo] = []
        for cat in config.issue_categories:
            issue_dir = config.get_issue_dir(cat)
            if not issue_dir.exists():
                continue
            for issue_file in issue_dir.glob("*.md"):
                info = parser.parse_file(issue_file)
                if info.status in non_terminal:
                    all_active.append(info)
                    if cat in requested_categories:
                        if not _matches_status(info, status_filter):
                            continue
                        if not _matches_filters(info):
                            continue
                        issues.append(info)

        all_known_ids: set[str] | None = None
        try:
            from little_loops.dependency_mapper import gather_all_issue_ids

            issues_dir = config.project_root / config.issues.base_dir
            all_known_ids = gather_all_issue_ids(issues_dir, config=config)
        except Exception:
            pass
        graph = DependencyGraph.from_issues(all_active, all_known_ids=all_known_ids)
        ready_ids = {info.issue_id for info in graph.get_ready_issues()}
        issues = [info for info in issues if info.issue_id in ready_ids]
    else:
        for cat in categories:
            issue_dir = config.get_issue_dir(cat)
            if not issue_dir.exists():
                continue

            for issue_file in issue_dir.glob("*.md"):
                info = parser.parse_file(issue_file)
                if not _matches_status(info, status_filter):
                    continue
                if not _matches_filters(info):
                    continue
                issues.append(info)

    # When only_ids is a list, preserve input order; otherwise sort by priority
    if isinstance(only_ids, list):
        issues.sort(
            key=lambda x: next(
                (i for i, p in enumerate(only_ids) if _id_matches(x.issue_id, p)),
                len(only_ids),
            )
        )
    else:
        issues.sort(key=lambda x: (x.priority_int, x.issue_id))
    return issues


def find_issues_for_graph(
    config: BRConfig,
    category: str | None = None,
) -> list[IssueInfo]:
    """Build the non-terminal superset needed for correct graph construction.

    ``find_issues()``'s default status filter hides ``done``/``cancelled``/
    ``deferred`` issues — correct for work-selection callers, but wrong for
    ``DependencyGraph`` construction: a ``blocked_by``/``depends_on`` edge
    pointing at a ``deferred`` issue must not be silently dropped just
    because the blocker is absent from the graph (BUG-2897). Only terminal
    statuses (``done``, ``cancelled``) should resolve a dependency edge, so
    callers building a graph should load this superset rather than relying
    on the default filter, then apply their own display-narrowing filter to
    the *ordered/display* list afterward.
    """
    from little_loops.issue_progress import _ALL_STATUSES, _TERMINAL_STATUSES

    non_terminal = set(_ALL_STATUSES - _TERMINAL_STATUSES)
    return find_issues(config, category=category, status_filter=non_terminal)


def superseded_by(issue_id: str, all_issues: Iterable[IssueInfo]) -> list[str]:
    """Return IDs of every issue whose `supersedes` list contains `issue_id`.

    Derives the reverse edge of the `supersedes` forward reference rather than
    requiring a second hand-maintained frontmatter field (ENH-2829).
    """
    return [info.issue_id for info in all_issues if issue_id in info.supersedes]


def find_highest_priority_issue(
    config: BRConfig,
    category: str | None = None,
    skip_ids: set[str] | None = None,
    only_ids: set[str] | None = None,
    type_prefixes: set[str] | None = None,
) -> IssueInfo | None:
    """Find the highest priority issue.

    Args:
        config: Project configuration
        category: Optional category to filter
        skip_ids: Issue IDs to skip
        only_ids: If provided, only include these issue IDs
        type_prefixes: If provided, only include issues with these type prefixes

    Returns:
        Highest priority IssueInfo or None if no issues found
    """
    issues = find_issues(config, category, skip_ids, only_ids, type_prefixes)
    return issues[0] if issues else None

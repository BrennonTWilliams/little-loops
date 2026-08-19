"""Issue file parsing for little-loops.

Parses issue markdown files to extract metadata like priority, ID, type, and title.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.cli_args import _id_matches
from little_loops.frontmatter import (
    DEPRECATED_FRONTMATTER_KEYS,
    DEPRECATED_STATUS_VALUES,
    parse_frontmatter,
)
from little_loops.text_utils import fence_spans, in_fence

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issues.cli_surface import CliSurfaceIndex
    from little_loops.issues.symbol_claims import SymbolIndex
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


_NORMALIZED_RE = re.compile(r"^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9_-]+\.md$")
_ISSUE_TYPE_RE = re.compile(r"-(BUG|FEAT|ENH|EPIC)-")
_FILENAME_ID_RE = re.compile(r"(BUG|FEAT|ENH|EPIC)-(\d+)")

# Anchored at the *start* of the filename: the canonical `P?-TYPE-NNN-` position.
# Unlike _FILENAME_ID_RE (an unanchored search), this can never be satisfied by a
# TYPE-NNN string embedded in the title slug (e.g. the "epic-3127" in
# "P3-ENH-3144-correct-epic-3127-tasks-extension-premise.md").
_ANCHORED_FILENAME_RE = re.compile(r"^(?:(P[0-5])-)?(BUG|FEAT|ENH|EPIC)-(\d+)-", re.IGNORECASE)


@dataclass(frozen=True)
class FilenameId:
    """The identity components parsed from an issue filename's anchor position."""

    priority: str | None
    type_prefix: str
    number: str


def parse_issue_filename(filename: str) -> FilenameId | None:
    """Parse the canonical ``P?-TYPE-NNN-`` anchor at the start of an issue filename.

    The numeric ID is the true unique identifier (globally unique across types);
    the type prefix is human-readable shorthand. Resolvers must key on this
    anchored parse — never on substring matching over the whole filename, which
    a title slug embedding another issue's ID can accidentally satisfy.

    Args:
        filename: Issue file basename (e.g. ``P2-BUG-010-my-issue.md``).

    Returns:
        The parsed components, or None when the filename has no canonical anchor
        (legacy/unnormalized names).
    """
    m = _ANCHORED_FILENAME_RE.match(filename)
    if not m:
        return None
    priority = m.group(1).upper() if m.group(1) else None
    return FilenameId(priority=priority, type_prefix=m.group(2).upper(), number=m.group(3))


def resolve_issue_path(config: BRConfig, user_input: str) -> Path | None:
    """Resolve user input to an issue file path.

    The single shared ID->path resolver for filename-based lookups (BUG-3229).
    Both `ll-issues show`/`path`/`set-status`/etc. (via `cli/issues/show.py`)
    and the sprint subsystem (`sprint.py:_find_issue_path`) delegate here so
    the two definitions of "an issue file on disk" cannot drift apart again.

    Accepts three input formats:
    - Numeric ID only: "518"
    - Type + ID: "FEAT-518"
    - Priority + Type + ID: "P3-FEAT-518"

    Searches the type-scoped category directories, plus any existing legacy
    `completed_dir`/`deferred_dir` (BUG-2733) — a `done`/`cancelled` issue
    parked there by a stale migration or manual placement would otherwise
    resolve as "not found". Status (open/done/deferred) lives in frontmatter,
    so active and inactive issues alike resolve here.

    Issue numbers are globally unique across types (see ``get_next_issue_number``),
    so a numeric match is unambiguous. The type prefix and priority are therefore
    treated as **advisory**: an exact match is preferred, but a stale or mismatched
    prefix (e.g. ``FEAT-1903`` for a file now named ``ENH-1903``) still resolves to
    the one file bearing that number rather than reporting "not found" (BUG-2003).

    A candidate filename is accepted only when its *anchored* `P?-TYPE-NNN-`
    position carries the requested number, regardless of whether a `P<n>-`
    priority prefix is present (BUG-3229) — `_ANCHORED_FILENAME_RE`'s priority
    group is optional. The raw (unanchored) glob set is used as a fallback
    only when **no** candidate's filename parses at all — a legacy/unnormalized
    name escape hatch — never merely because the anchored filter or the later
    type filter emptied the pool; a filter emptying the pool means "no match",
    not "widen the search" (this is what let a slug embedding another issue's
    ID resolve as a false positive before BUG-3229).

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

    # Type token alternation is derived from the project's configured issue
    # categories rather than hardcoded to BUG|FEAT|ENH|EPIC: a project with a
    # custom category (e.g. "tasks" -> prefix "TASK") must resolve
    # "TASK-001" the same as any built-in type. Longest-prefix-first so a
    # prefix that is a substring of another (unlikely, but not guaranteed)
    # can't shadow it.
    configured_prefixes = sorted(
        {config.get_issue_prefix(c) for c in config.issue_categories},
        key=len,
        reverse=True,
    )
    type_alt = "|".join(re.escape(p) for p in configured_prefixes) or "BUG|FEAT|ENH|EPIC"

    # Try P-TYPE-NNN format (e.g., P3-FEAT-518)
    m = re.match(rf"^(P\d)-({type_alt})-(\d+)$", user_input, re.IGNORECASE)
    if m:
        priority = m.group(1).upper()
        type_prefix = m.group(2).upper()
        numeric_id = m.group(3)
    else:
        # Try TYPE-NNN format (e.g., FEAT-518)
        m = re.match(rf"^({type_alt})-(\d+)$", user_input, re.IGNORECASE)
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

    # Build search directories: type-scoped dirs, plus existing legacy dirs
    search_dirs: list[Path] = []
    for category in config.issue_categories:
        search_dirs.append(config.get_issue_dir(category))
    search_dirs.extend(config.legacy_issue_dirs())

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

    # The glob above is a substring match over the whole filename, so a title
    # slug embedding another issue's number (e.g. "...-correct-epic-3127-..."
    # in ENH-3144's slug) also lands here. Keep only files whose *anchored*
    # `P?-TYPE-NNN-` position carries the requested number; fall back to the
    # raw glob set only when NO candidate's filename parses at all (a genuine
    # legacy/unnormalized name) — never merely because the anchored filter
    # rejected every parseable candidate, which would resurrect a
    # wrong-number file that happens to be the sole candidate (BUG-3229).
    anchored = [
        p
        for p in candidates
        if (fid := parse_issue_filename(p.name)) is not None and fid.number == numeric_id
    ]
    if anchored:
        candidates = anchored
    elif all(parse_issue_filename(p.name) is None for p in candidates):
        pass  # legacy escape hatch: nothing parses, keep the raw glob set
    else:
        return None  # every candidate parsed, but none carries the requested number

    def _frontmatter_identity(path: Path) -> tuple[str | None, str | None]:
        """Return (type, number) claimed by frontmatter, format-agnostically.

        Both `id: EPIC-3127` and bare `id: 3127` are supported formats; for a
        bare numeric id the type comes from the `type:` field when present.
        """
        try:
            content = path.read_text()
        except OSError:
            return (None, None)
        fm = parse_frontmatter(content)
        raw = fm.get("id")
        if not raw:
            return (None, None)
        m = re.match(r"^(?:(BUG|FEAT|ENH|EPIC)-)?(\d+)$", str(raw).strip(), re.IGNORECASE)
        if not m:
            return (None, None)
        fm_type = m.group(1).upper() if m.group(1) else None
        if fm_type is None:
            raw_type = fm.get("type")
            fm_type = str(raw_type).strip().upper() if raw_type else None
        return (fm_type, m.group(2))

    # Prefer a frontmatter `id:` match over filename-derived matching
    # (BUG-2806): when a candidate's own frontmatter claims the requested
    # number (and doesn't contradict the requested type), it wins outright. A
    # missing/unparseable `id:` field is "no opinion" and falls through
    # unchanged to the filename-derived matching below (BUG-2003 tolerance for
    # stale/mismatched type prefixes relies on that fallback).
    if type_prefix:
        frontmatter_matches = []
        for p in candidates:
            fm_type, fm_number = _frontmatter_identity(p)
            if fm_number == numeric_id and (fm_type is None or fm_type == type_prefix):
                frontmatter_matches.append(p)
        if frontmatter_matches:
            candidates = frontmatter_matches

    def _matches_type(path: Path) -> bool:
        fid = parse_issue_filename(path.name)
        if fid is not None:
            return fid.type_prefix == type_prefix
        # Legacy/unnormalized filename: fall back to the historical substring
        # heuristic rather than excluding the file outright.
        upper = path.name.upper()
        return f"-{type_prefix}-" in upper or upper.startswith(f"{type_prefix}-")

    # Prefer an exact-type match; fall back to the unambiguous numeric match when
    # the caller's type prefix is stale or mismatched (advisory, not required).
    # Safe to widen back to `candidates` here (unlike the anchored stage above):
    # by this point `candidates` only ever contains anchored-number matches (or
    # the all-unparsed legacy set), never a wrong-number file, so this can only
    # relax the *type* requirement (BUG-2003), not resurrect a false positive.
    pool = [p for p in candidates if _matches_type(p)] if type_prefix else candidates
    if not pool:
        pool = candidates

    # Within the chosen pool, prefer an exact priority match if one exists.
    if priority:
        prioritized = [p for p in pool if p.name.upper().startswith(f"{priority}-")]
        if prioritized:
            return prioritized[0]

    return pool[0]


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
        True if the filename matches ``^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9_-]+\\.md$``.
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

    Both the heading match and the end-boundary scan exclude matches that fall
    inside a fenced code block (BUG-3202) via :func:`~little_loops.text_utils.
    fence_spans`/:func:`~little_loops.text_utils.in_fence` — a quoted ``##``-shaped
    line in an issue body about markdown tooling no longer wins section
    resolution or truncates the section that encloses it. The body is always
    sliced from *content* itself (never from fence-blanked text), so a section
    whose content is entirely a code fence is not reported empty by callers like
    :func:`~little_loops.issue_parser.check_format_gaps`. A heading that appears
    only inside fences resolves as absent, same as a heading that never appears.
    """
    spans = fence_spans(content)
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    matches = [
        m
        for m in re.finditer(pattern, content, re.MULTILINE)
        if not in_fence(m.start(), m.end(), spans)
    ]
    if not matches:
        return None
    match = matches[-1]
    start = match.end()

    terminator_pattern = re.compile(r"^##\s", re.MULTILINE)
    end = len(content)
    for term in terminator_pattern.finditer(content, start):
        if not in_fence(term.start(), term.end(), spans):
            end = term.start()
            break
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


# ENH-2966 Option E: gap classes that are advisory-only — reported (they still
# feed FormatGaps.has_gaps, so they render in every output surface) but must
# not fail format-check's exit code. `testable`'s false-positive rate made a
# hard gate out of what is meant to be a "maybe set testable: false" nudge.
_ADVISORY_GAP_CLASSES: frozenset[str] = frozenset({"testable"})


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
    ambiguous_file_ref: list[str] = field(default_factory=list)
    missing_behavior_parity: list[str] = field(default_factory=list)
    soft_dep_hard_edge: list[str] = field(default_factory=list)
    malformed_dep_id: list[str] = field(default_factory=list)
    stale_symbol_ref: list[str] = field(default_factory=list)
    mislocated_symbol_ref: list[str] = field(default_factory=list)
    stale_cli_flag: list[str] = field(default_factory=list)
    duplicate_heading: list[str] = field(default_factory=list)
    empty_provenance_stub: list[str] = field(default_factory=list)
    template_placeholders: list[str] = field(default_factory=list)
    unapplied_decision: list[str] = field(default_factory=list)

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
            or self.ambiguous_file_ref
            or self.missing_behavior_parity
            or self.soft_dep_hard_edge
            or self.malformed_dep_id
            or self.stale_symbol_ref
            or self.mislocated_symbol_ref
            or self.stale_cli_flag
            or self.duplicate_heading
            or self.empty_provenance_stub
            or self.template_placeholders
            or self.unapplied_decision
        )

    @property
    def has_blocking_gaps(self) -> bool:
        """True when any *non-advisory* gap category is non-empty (ENH-2966).

        Exit-code predicate — narrower than :attr:`has_gaps`, which stays the
        reporting predicate so advisory classes (`_ADVISORY_GAP_CLASSES`) still
        render everywhere but no longer fail `format-check`'s exit code.
        """
        return any(
            getattr(self, f.name) for f in fields(self) if f.name not in _ADVISORY_GAP_CLASSES
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
            "ambiguous_file_ref": self.ambiguous_file_ref,
            "missing_behavior_parity": self.missing_behavior_parity,
            "soft_dep_hard_edge": self.soft_dep_hard_edge,
            "malformed_dep_id": self.malformed_dep_id,
            "stale_symbol_ref": self.stale_symbol_ref,
            "mislocated_symbol_ref": self.mislocated_symbol_ref,
            "stale_cli_flag": self.stale_cli_flag,
            "duplicate_heading": self.duplicate_heading,
            "empty_provenance_stub": self.empty_provenance_stub,
            "template_placeholders": self.template_placeholders,
            "unapplied_decision": self.unapplied_decision,
        }


def design_gate_failed(gaps: FormatGaps) -> bool:
    """True when the Program Design gate failed for the issue *gaps* describe (ENH-2967).

    Single owner of the three-way OR that `autodev.yaml` previously re-derived
    independently in three inline ``python3 -c`` blocks (plus prose/shellout
    restatements in ``ready-issue.md`` and ``confidence-check/SKILL.md``):
    a non-specific ``## Program Design`` section, or the section missing/empty
    entirely. Inert (returns False) on projects that haven't armed the gate,
    since ``check_format_gaps`` never populates these three fields in that case.
    """
    return (
        bool(gaps.program_design_nonspecific)
        or "Program Design" in gaps.missing
        or "Program Design" in gaps.empty
    )


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
    symbol_index: SymbolIndex | None = None,
    cli_index: CliSurfaceIndex | None = None,
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
        ambiguous_file_ref: a file path reference classifies as ``ambiguous``
            (ENH-2999, :func:`little_loops.text_utils.classify_issue_refs`) —
            the unrooted suffix matches more than one tracked file after the
            host-adapter mirror tie-break, so the reference cannot be resolved
            without disambiguation. Distinct from ``stale_file_ref``: the file
            was not deleted or moved, the reference is just missing enough
            path prefix to pick one of several real matches. Each entry names
            the candidate count and up to three candidate paths (elided with
            ``…`` beyond that). Only reported when *ref_index* is given.
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
        missing_behavior_parity: a file ref in ``## Summary``,
            ``## Proposed Solution``, or ``### Files to Modify`` (ENH-3045)
            resolves (:func:`little_loops.text_utils.classify_file_ref`) and
            shares a line with a replacement keyword (``delete``, ``remove``,
            ``replace``, ``rewrite``, ``supersede``, ``delegate``, and their
            inflections — same line only, no multi-line proximity window),
            while no ``### Behavior Parity`` section exists
            (:func:`_heading_bodies`). Suppressed unconditionally by
            ``behavior_parity_not_applicable: true`` in frontmatter, a human
            decision mirroring ``program_design_not_applicable`` — refine and
            wire must never set it themselves. Only reported when *ref_index*
            is given.
        soft_dep_hard_edge: an ID in ``blocked_by``/``depends_on`` (ENH-3046)
            that the body describes with soft-dependency language ("soft dep",
            "optional", "nice to have", "has not landed") in the same
            blank-line-delimited paragraph as the ID. The hard structured edge
            contradicts the soft prose — remedy is moving the ID to
            ``relates_to``, not deleting the prose (the soft language is
            usually the accurate statement). No suppression escape hatch.
            Only reported when *issue_statuses* is given.
        malformed_dep_id: an entry in ``blocked_by``/``depends_on``/``blocks``/
            ``relates_to``/``supersedes`` that is not a well-formed
            ``TYPE-NNN`` ID (BUG-3059) -- most often a bare number, e.g.
            ``depends_on: [3038]`` instead of ``[FEAT-3038]``. This is not
            cosmetic: ``DependencyGraph`` matches IDs by exact string, so a
            malformed entry silently drops the edge from the graph. The
            optional ``P<n>-`` filename prefix is accepted and normalized.
        stale_symbol_ref: a backticked symbol claim (FEAT-3048,
            :func:`little_loops.issues.symbol_claims.extract_symbol_claims`)
            attributed to a cited file that itself resolves via *ref_index*,
            where the symbol does not resolve as a def-site or module-level
            constant in that file
            (:func:`little_loops.issues.symbol_claims.symbol_exists_in_file`)
            **and** does not resolve anywhere else in the repo either
            (:func:`little_loops.issues.symbol_claims.symbol_resolves_elsewhere`,
            BUG-3063 § Proposed Solution C). Claims are extracted only from the
            current-state section allowlist (BUG-3063 § Proposed Solution A1,
            :data:`_STALE_SYMBOL_SCOPE_H2_SECTIONS`) — a symbol named in a
            forward-looking section (``## Program Design``, ``### Files to
            Modify``, ``## Implementation Steps``, …) is never read as an
            existence assertion. Only reported when both *ref_index* and
            *symbol_index* are given; fails open otherwise, and for a cited
            file whose language is outside the resolver's supported set.
        mislocated_symbol_ref: the BUG-3063 § Proposed Solution C sibling of
            ``stale_symbol_ref`` — a symbol claim, subject to the same
            allowlist scoping, that does not resolve in the cited file but
            does resolve somewhere else in the repo. This is a mis-attribution
            (the symbol exists, just not where the issue says), not a stale
            claim, and is reported separately rather than folded into
            ``stale_symbol_ref``.
        stale_cli_flag: a backticked ``ll-<tool> <subcommand> [--flag ...]``
            claim (FEAT-3048,
            :func:`little_loops.issues.cli_claims.extract_cli_flag_claims`)
            naming a subcommand or long flag the tool's argparse parser does
            not accept, per a ``--help``-scraped surface index
            (:func:`little_loops.issues.cli_surface.build_cli_surface_index`).
            Only reported when *cli_index* is given; fails open for an
            unscrapable tool.
        duplicate_heading: the same ``###`` heading text appears more than
            once under one ``##`` parent (ENH-3247) — e.g. two
            ``### Files to Modify`` under ``## Integration Map`` after a retry
            pass. Excludes ``### Codebase Research Findings``, which is
            already owned by ``duplicate_findings_block`` with its own
            dedicated repair. Both detection and repair mask fenced code
            blocks (:func:`little_loops.text_utils.fence_spans`) — a
            duplicate heading inside an illustrative ``` ``` ``` block is
            documentation, not a gap.
        empty_provenance_stub: an ``_Added by `/ll:refine-issue` — DATE —
            based on codebase analysis:_`` provenance line (ENH-3247,
            :data:`little_loops.issues.fold_research_findings._MARKER_PREFIX`)
            with no bullet or other content before the next heading or the
            next stub — a provenance marker for findings that were never
            written. Fence-masked like ``duplicate_heading``.
        template_placeholders: a literal unfilled template placeholder
            (ENH-3244) — e.g. ``TBD - requires codebase analysis``,
            ``[Major phase 1]`` — still present in the section whose
            ``creation_template`` emits it. The pattern set is derived at
            runtime from ``scripts/little_loops/templates/*-sections.json``
            (:func:`_template_placeholder_patterns`), not hand-transcribed.
            Section-scoped (a mention in a different section does not
            count), fence- and inline-backtick-masked
            (:func:`_template_placeholders`), and excludes ``Program
            Design`` — its placeholders are the only ones every template
            already wraps in backticks, so inline masking would swallow
            them anyway, and its residue is already caught by
            ``boilerplate``/``program_design_nonspecific``. Detection only —
            no ``--fix`` handler is registered.
        unapplied_decision: a ``> **Selected:**`` callout names a winning
            option in ``## Proposed Solution`` (ENH-3256) while a backticked
            identifier unique to a *rejected* option
            (:func:`_unapplied_decision`) still appears, unmarked, in one of
            :data:`_DECISION_DIRECTIVE_SECTIONS`. A decision *record* is not
            proof the decision was *applied* -- the rejected option's
            discriminating identifiers (``REJ - SEL``, where ``SEL``/``REJ``
            are the backticked identifiers in the selected/rejected option
            blocks) must not survive into the directive sections. Options are
            enumerated from ``## Proposed Solution`` only, never full document
            content; the selected block is identified by matching the
            callout's option title against each option heading, not by
            :func:`_is_option_resolved`, which cannot distinguish selected
            from rejected. Exempt when ``⚠ Superseded``
            (:data:`_SUPERSEDED_MARKER_PREFIX`) appears in the same paragraph.
            Report-only; caps ``/ll:confidence-check`` Criterion C, never a
            hard override.

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
        symbol_index: Optional
            :class:`little_loops.issues.symbol_claims.SymbolIndex` built once
            per invocation via
            :func:`little_loops.issues.symbol_claims.build_symbol_index`,
            used to resolve symbol claims. When absent, no
            ``stale_symbol_ref`` gaps are reported.
        cli_index: Optional
            :class:`little_loops.issues.cli_surface.CliSurfaceIndex` built
            once per invocation via
            :func:`little_loops.issues.cli_surface.build_cli_surface_index`,
            used to resolve CLI-flag claims. Lazily scrapes and caches a
            tool's ``--help`` surface on first query per tool (not eagerly
            for every registered tool), so a body naming no ``ll-*`` command
            triggers no subprocess at all. When absent, no
            ``stale_cli_flag`` gaps are reported.

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

    # BUG-3059: dependency-entry *shape*. malformed_id above only checks the
    # `id:` key against the filename; nothing validated the edge keys, so a
    # bare-numeric entry (`depends_on: [3038]`) passed every gate while
    # DependencyGraph's exact-string membership test silently dropped the edge.
    for dep_key in ("blocked_by", "depends_on", "blocks", "relates_to", "supersedes"):
        dep_value = fm.get(dep_key)
        if isinstance(dep_value, list):
            dep_entries = [str(v).strip() for v in dep_value]
        elif isinstance(dep_value, str) and dep_value.strip():
            dep_entries = [dep_value.strip()]
        else:
            continue
        for dep_entry in dep_entries:
            if dep_entry and not _DEP_ID_RE.fullmatch(dep_entry):
                gaps.malformed_dep_id.append(f"{dep_key}: {dep_entry} (expected TYPE-NNN)")

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
        for prose_id in sorted(extract_prose_deps(body_only, host_id=own_id)):
            if prose_id == own_id:
                continue
            status = issue_statuses.get(prose_id)
            if status in ("done", "cancelled"):
                gaps.stale_prose_dep.append(prose_id)
            elif prose_id not in structured_deps:
                gaps.prose_dep_drift.append(prose_id)

        if structured_deps:
            from little_loops.issues.prose_deps import _ID_ONLY_RE, _in_fence
            from little_loops.text_utils import _CODE_FENCE

            fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(body_only)]
            soft_edges: set[str] = set()
            for para_start, para_end in _paragraph_spans(body_only):
                if _in_fence(para_start, para_end, fence_spans):
                    continue
                paragraph = body_only[para_start:para_end]
                if not _SOFT_DEP_PHRASE_RE.search(paragraph):
                    continue
                for id_match in _ID_ONLY_RE.finditer(paragraph):
                    candidate = f"{id_match.group(1).upper()}-{id_match.group(2)}"
                    if candidate in structured_deps:
                        soft_edges.add(candidate)
            gaps.soft_dep_hard_edge.extend(sorted(soft_edges))

    if "testable" not in fm:
        title = str(fm.get("title") or "").strip()
        if not title:
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = title_match.group(1) if title_match else ""
        summary = _section_body(content, "Summary") or ""
        scan_text = f"{title}\n{summary}"
        if _count_testable_keyword_matches(scan_text) >= _TESTABLE_KEYWORD_THRESHOLD:
            gaps.testable.append(issue_path.name)

    if ref_index is not None:
        from little_loops.text_utils import (
            classify_file_ref,
            classify_issue_refs,
            extract_file_paths,
            suffix_match_candidates,
        )

        for ref, status in sorted(classify_issue_refs(content, ref_index).items()):
            if status == "stale":
                gaps.stale_file_ref.append(ref)
            elif status == "ambiguous":
                candidates = sorted(suffix_match_candidates(ref, ref_index))
                shown = ", ".join(candidates[:3])
                if len(candidates) > 3:
                    shown += ", …"
                gaps.ambiguous_file_ref.append(f"{ref} ({len(candidates)}: {shown})")

        if not fm.get("behavior_parity_not_applicable") and not _heading_bodies(
            content, "Behavior Parity"
        ):
            scope_text = _behavior_parity_scope_text(content)
            scope_lines = scope_text.splitlines()
            for ref in sorted(extract_file_paths(scope_text)):
                replacement_line = next(
                    (
                        ln
                        for ln in scope_lines
                        if ref in ln and _BEHAVIOR_PARITY_KEYWORD_RE.search(ln)
                    ),
                    None,
                )
                if replacement_line is None:
                    continue
                if classify_file_ref(ref, ref_index, line=replacement_line) == "resolved":
                    gaps.missing_behavior_parity.append(ref)

        if symbol_index is not None:
            from little_loops.issues.symbol_claims import (
                claim_breadth_exceeds_cap,
                extract_symbol_claims,
                symbol_exists_in_file,
                symbol_resolves_elsewhere,
            )

            scoped_content = _symbol_claim_scope_text(content)
            for claim in sorted(
                extract_symbol_claims(scoped_content, ref_index), key=lambda c: (c.file, c.symbol)
            ):
                if claim_breadth_exceeds_cap(symbol_index, claim.file, claim.symbol):
                    continue
                if symbol_exists_in_file(symbol_index, claim.file, claim.symbol) is False:
                    if symbol_resolves_elsewhere(symbol_index, claim.file, claim.symbol):
                        gaps.mislocated_symbol_ref.append(
                            f"{claim.symbol} (claimed in {claim.file})"
                        )
                    else:
                        gaps.stale_symbol_ref.append(f"{claim.symbol} (claimed in {claim.file})")

    if cli_index is not None:
        from little_loops.issues.cli_claims import extract_cli_flag_claims
        from little_loops.issues.cli_surface import cli_surface_accepts

        for cli_claim in sorted(
            extract_cli_flag_claims(content), key=lambda c: (c.tool, c.subcommand, c.flags)
        ):
            if cli_surface_accepts(cli_index, cli_claim.tool, cli_claim.subcommand) is False:
                gaps.stale_cli_flag.append(f"{cli_claim.raw} (no such subcommand)")
                continue
            for flag in cli_claim.flags:
                if (
                    cli_surface_accepts(cli_index, cli_claim.tool, cli_claim.subcommand, flag)
                    is False
                ):
                    gaps.stale_cli_flag.append(
                        f"{cli_claim.tool} {cli_claim.subcommand} {flag} (no such flag)"
                    )

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

    gaps.unapplied_decision.extend(_unapplied_decision(content))

    gaps.duplicate_findings_block.extend(_duplicate_findings_blocks(content))
    gaps.duplicate_heading.extend(_duplicate_headings(content))
    gaps.empty_provenance_stub.extend(_empty_provenance_stubs(content))
    gaps.template_placeholders.extend(_template_placeholders(content, issue_type, templates_dir))

    return gaps


# ENH-2993: `### Codebase Research Findings` accumulates one block per
# /ll:refine-issue pass; `ll-issues fold-findings` folds them to one per H2.
_FINDINGS_SUB_HEADING = "Codebase Research Findings"
_FINDINGS_H3_RE = re.compile(rf"^###\s+{re.escape(_FINDINGS_SUB_HEADING)}\s*$", re.MULTILINE)


def _iter_h2_sections_fence_masked(
    content: str, fences: list[tuple[int, int]] | None = None
) -> list[tuple[str, int, int]]:
    """Fence-masked sibling of :func:`_iter_h2_sections` (ENH-3247).

    A ``## `` line inside a fenced code block (e.g. an illustrative markdown
    example embedded in an issue body) is not a real section boundary — see
    BUG-3245's own file, whose ```` ```markdown ```` example block contains a
    ``## Program Design`` line that previously made ``_iter_h2_sections``
    report that heading twice. New H2-scoped detectors should use this
    instead of :func:`_iter_h2_sections`.
    """
    from little_loops.text_utils import in_fence

    if fences is None:
        from little_loops.text_utils import fence_spans

        fences = fence_spans(content)
    matches = [
        m
        for m in re.finditer(r"^##\s+(.+?)\s*$", content, re.MULTILINE)
        if not in_fence(m.start(), m.end(), fences)
    ]
    sections = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections.append((m.group(1).strip(), start, end))
    return sections


def _duplicate_findings_blocks(content: str) -> list[str]:
    """Return ``"<H2> (N)"`` for each H2 carrying more than one findings block.

    Deliberately **not** built on :func:`_heading_bodies`, despite that being
    the existing reader of this heading. ``_heading_bodies`` is document-wide
    and returns bodies with no parent-section information, so ``len(bodies) > 1``
    cannot express "per H2": a fully compliant document with one findings block
    under each of three H2s would return 3 and be flagged. It also matches
    ``##`` as well as ``###``, so a stray ``## Codebase Research Findings``
    would register as a duplicate of a legitimate nested one.

    Slicing with :func:`_iter_h2_sections_fence_masked` and counting only
    ``###`` matches *within each slice*, excluding fenced ones, avoids all
    three traps (ENH-3247 fixed the fence blindness in the same pass as the
    two new gap classes below, per Proposed Solution step 0's decision).
    """
    from little_loops.text_utils import fence_spans, in_fence

    fences = fence_spans(content)
    duplicates: list[str] = []
    for heading, start, end in _iter_h2_sections_fence_masked(content, fences):
        count = sum(
            1
            for m in _FINDINGS_H3_RE.finditer(content, start, end)
            if not in_fence(m.start(), m.end(), fences)
        )
        if count > 1:
            duplicates.append(f"{heading} ({count})")
    return duplicates


# ENH-3247: the same "same ### text repeated under one ## parent" shape as
# _duplicate_findings_blocks, but for arbitrary heading text rather than the
# one fixed pattern. Codebase Research Findings is excluded — that shape
# stays owned by _duplicate_findings_blocks/fold-findings (Decision Rules).
_H3_HEADING_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)


def _duplicate_heading_groups(
    content: str,
) -> list[tuple[str, str, list[tuple[int, int, int]]]]:
    """Return ``(h2, h3, [(block_start, body_start, block_end), ...])`` per repeated H3.

    Only H3 headings repeated more than once under the same H2 parent are
    returned. Each block spans from the ``###`` heading line start
    (``block_start``) through the next heading of level <=3 or the parent H2
    slice end (``block_end``), with ``body_start`` marking where the heading
    line ends and the body begins — the same three-way split
    :func:`little_loops.issues.fold_research_findings.find_subsections` uses,
    so the repair (which collapses these spans) and that existing precedent
    agree on what "the block" and "the body" mean. Fence-masked throughout
    (ENH-3247 Proposed Solution step 0): a duplicate heading that exists only
    inside a fenced example is not a gap.
    """
    from little_loops.text_utils import fence_spans, in_fence

    fences = fence_spans(content)
    groups: list[tuple[str, str, list[tuple[int, int, int]]]] = []
    for h2, h2_start, h2_end in _iter_h2_sections_fence_masked(content, fences):
        by_heading: dict[str, list[tuple[int, int, int]]] = {}
        for m in _H3_HEADING_RE.finditer(content, h2_start, h2_end):
            if in_fence(m.start(), m.end(), fences):
                continue
            text = m.group(1).strip()
            if text == _FINDINGS_SUB_HEADING:
                continue
            following = re.search(r"^#{1,3}\s", content[m.end() : h2_end], re.MULTILINE)
            block_end = m.end() + following.start() if following else h2_end
            by_heading.setdefault(text, []).append((m.start(), m.end(), block_end))
        for text, spans in by_heading.items():
            if len(spans) > 1:
                groups.append((h2, text, spans))
    return groups


def _duplicate_headings(content: str) -> list[str]:
    """Gap-report strings for the ``duplicate_heading`` class (ENH-3247)."""
    return [f"{h2} > {h3} ({len(spans)})" for h2, h3, spans in _duplicate_heading_groups(content)]


def _empty_provenance_stub_matches(content: str) -> list[re.Match[str]]:
    """Return regex matches for empty ``_Added by …:_`` stubs (ENH-3247).

    "Empty" means no non-blank line (bullet or otherwise) appears between the
    stub and whichever comes first: the next heading (any level) or the next
    stub. Fence-masked. Built on the exact marker text
    :func:`little_loops.issues.fold_research_findings.fold_research_findings`
    writes, so detection here and the module that produces (and, post
    BUG-3245, never again produces empty) these stubs can never disagree
    about what a stub looks like.
    """
    from little_loops.issues.fold_research_findings import _MARKER_PREFIX, _MARKER_SUFFIX
    from little_loops.text_utils import fence_spans, in_fence

    stub_re = re.compile(
        rf"^{re.escape(_MARKER_PREFIX)}.*?{re.escape(_MARKER_SUFFIX)}[ \t]*$",
        re.MULTILINE,
    )
    fences = fence_spans(content)
    stubs = [m for m in stub_re.finditer(content) if not in_fence(m.start(), m.end(), fences)]
    heading_re = re.compile(r"^#{1,6}\s", re.MULTILINE)

    empty: list[re.Match[str]] = []
    for i, m in enumerate(stubs):
        next_stub_start = stubs[i + 1].start() if i + 1 < len(stubs) else len(content)
        heading_match = heading_re.search(content, m.end())
        heading_start = heading_match.start() if heading_match else len(content)
        boundary = min(next_stub_start, heading_start)
        if not content[m.end() : boundary].strip():
            empty.append(m)
    return empty


def _empty_provenance_stubs(content: str) -> list[str]:
    """Gap-report strings for the ``empty_provenance_stub`` class (ENH-3247)."""
    return [
        f"line {content.count(chr(10), 0, m.start()) + 1}"
        for m in _empty_provenance_stub_matches(content)
    ]


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

# ENH-3256: superset of _SUPERSEDED_DIRECTIVE_SECTIONS -- "Proposed Solution"
# and "Program Design" also carry decision-drift risk, since /ll:decide-issue
# only ever annotates ## Proposed Solution. "Files to Modify" is an H3 nested
# under ## Integration Map, so it must be read via _heading_bodies, not
# _section_body.
_DECISION_DIRECTIVE_SECTIONS = (
    "Proposed Solution",
    "Program Design",
    "Implementation Steps",
    "Files to Modify",
    "Acceptance Criteria",
)

# ENH-3256: the callout /ll:decide-issue writes -- `> **Selected:** <title>`.
_SELECTED_CALLOUT_RE = re.compile(r"^\s*>\s+\*\*Selected:\*\*\s*(.+)$", re.MULTILINE)
# An "Option X" label, used to match a selected-callout title against option
# heading lines without depending on the surrounding markdown decoration
# (### Option A vs **Option A**: ...).
_OPTION_LABEL_RE = re.compile(r"Option\s+[A-Za-z0-9]+", re.IGNORECASE)
_DECISION_RATIONALE_HEADING_RE = re.compile(r"^###\s+Decision Rationale\s*$", re.MULTILINE)
# A backticked code span of length >= 3 -- the identifier unit both SEL and
# REJ are built from (Program Design § Decision Rules, Identifier extraction).
_DECISION_IDENTIFIER_RE = re.compile(r"`([^`\n]{3,})`")


def _selected_option_title(section_body: str) -> str | None:
    """Option title text from the first `> **Selected:** <title>` callout, or None.

    First-occurrence is intentional (ENH-3256): whether the matched callout
    lives in the winning option's own block or a rejected block's
    "Selected: Option A, not this one" cross-reference, both name the winner
    by the same label, so the first match always resolves to the correct
    title regardless of physical block order.
    """
    match = _SELECTED_CALLOUT_RE.search(section_body)
    return match.group(1).strip() if match else None


def _option_label(text: str) -> str | None:
    """Lowercased "option x" label extracted from *text*, or None."""
    match = _OPTION_LABEL_RE.search(text)
    return match.group(0).lower() if match else None


def _decision_identifiers(text: str) -> set[str]:
    """Backticked identifiers of length >= 3 in *text*."""
    return {m.group(1) for m in _DECISION_IDENTIFIER_RE.finditer(text)}


def _strip_codebase_research_findings(body: str) -> str:
    """Drop every ``### Codebase Research Findings`` block from *body*.

    ENH-3256 corpus finding: /ll:refine-issue commonly appends per-option
    comparison notes ("Step 2 (pytest option A): ...", "Step 2 (CLI option
    B): ...") under this heading, nested inside directive sections like
    ``## Implementation Steps``. That is deliberate research documentation of
    the rejected alternative, not a directive telling the implementer to
    build it -- scanning it produced 128 corpus-wide false-positive firings
    (live-corpus run required by Implementation Steps, step 5) before this
    strip was added.
    """
    matches = list(_FINDINGS_H3_RE.finditer(body))
    if not matches:
        return body
    kept: list[str] = []
    cursor = 0
    for m in matches:
        kept.append(body[cursor : m.start()])
        next_heading = re.search(r"^#{1,3}\s", body[m.end() :], re.MULTILINE)
        cursor = m.end() + next_heading.start() if next_heading else len(body)
    kept.append(body[cursor:])
    return "".join(kept)


def _option_block_spans(text: str) -> list[tuple[int, int, str]]:
    """``(start, end, heading_line)`` for each option block in *text*.

    Offset-carrying sibling of :func:`_iter_option_blocks`, built on the same
    :data:`_OPTION_HEADING_RE` boundary rule, needed here because
    :func:`_unapplied_decision` must clamp and scrub option-block spans
    in-place rather than just read their text.
    """
    matches = list(_OPTION_HEADING_RE.finditer(text))
    spans: list[tuple[int, int, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        line_end = text.find("\n", start)
        if line_end == -1:
            line_end = len(text)
        heading_line = text[start:line_end].strip()
        spans.append((start, end, heading_line))
    return spans


def _unapplied_decision(content: str) -> list[str]:
    """Reason strings for rejected-option identifiers left in directive sections.

    Options are enumerated from ``_section_body(content, "Proposed Solution")``
    only -- never full ``content`` -- and the final block is clamped at
    ``### Decision Rationale``. The Proposed Solution scan subtracts the option
    blocks and the Decision Rationale subsection. See Program Design ›
    Decision Rules (ENH-3256) for why each of those is load-bearing.
    """
    proposed_body = _section_body(content, "Proposed Solution")
    if not proposed_body:
        return []

    spans = _option_block_spans(proposed_body)
    if len(spans) < 2:
        return []

    dr_match = _DECISION_RATIONALE_HEADING_RE.search(proposed_body)
    dr_start = dr_match.start() if dr_match else len(proposed_body)

    # Clamp the final option block at the Decision Rationale boundary -- it is
    # appended to the end of Proposed Solution by /ll:decide-issue, not to
    # any option's own body, and its block would otherwise run to end-of-input.
    last_start, last_end, last_heading = spans[-1]
    if last_end > dr_start:
        spans[-1] = (last_start, max(last_start, dr_start), last_heading)

    # The final block is additionally trimmed at the end of its own callout
    # line, if it carries one, dropping any further unheaded prose before the
    # section end. Only the *last* block risks this "runs to end-of-section"
    # absorption (every other block is naturally bounded by the next option
    # heading), and only when it is itself the callout-carrying (selected)
    # block -- a trailing callout there marks "the option's own description is
    # done; what follows is free-form rationale", which legitimately
    # re-mentions other sections/identifiers by name for narrative reasons
    # (observed on this issue's own corpus firing).
    last_start, last_end, last_heading = spans[-1]
    last_callout = _SELECTED_CALLOUT_RE.search(proposed_body, last_start, last_end)
    if last_callout:
        line_end = proposed_body.find("\n", last_callout.end())
        line_end = len(proposed_body) if line_end == -1 else line_end
        spans[-1] = (last_start, min(last_end, line_end), last_heading)

    # Every block's identifiers are read with its own `> **Selected:**`
    # callout LINE masked out (not the rest of the block): the callout is
    # meta-commentary about the decision, and a rejected option's callout
    # routinely names the *winner's* identifiers in prose ("not this one --
    # `foo`'s scope excludes `bar`"), which would otherwise leak the winner's
    # own vocabulary into REJ. The callout's position within a block is not
    # reliable (some conventions place it right after the option heading,
    # others at the end), so masking only that one line -- not "everything
    # before/after it" -- is the only positionally-safe exclusion.
    block_texts: list[str] = []
    for start, end, _heading in spans:
        block_text = proposed_body[start:end]
        callout = _SELECTED_CALLOUT_RE.search(block_text)
        if callout:
            line_end = block_text.find("\n", callout.end())
            line_end = len(block_text) if line_end == -1 else line_end
            block_text = block_text[: callout.start()] + block_text[line_end:]
        block_texts.append(block_text)

    title = _selected_option_title(proposed_body)
    if title is None:
        return []
    label = _option_label(title)
    if label is None:
        return []

    matching = [i for i, (_, _, heading) in enumerate(spans) if _option_label(heading) == label]
    if len(matching) != 1:
        return []
    selected_index = matching[0]

    sel_ids = _decision_identifiers(block_texts[selected_index])
    rej_ids: set[str] = set()
    for i, block_text in enumerate(block_texts):
        if i != selected_index:
            rej_ids |= _decision_identifiers(block_text)

    discriminating = rej_ids - sel_ids
    if not discriminating:
        return []

    # Self-scan subtraction (mandatory): "Proposed Solution" is both the
    # extraction source and a scan target, so REJ members -- present by
    # construction inside the rejected option block, itself inside Proposed
    # Solution -- would otherwise self-fire on every decided issue. Also caps
    # at the final block's own (already-trimmed) end: unheaded rationale
    # prose past that point re-mentions rejected-option identifiers for
    # narrative reasons, same as the headed Decision Rationale form.
    scrub_start = min(dr_start, spans[-1][1])
    scrubbed_proposed = proposed_body[:scrub_start]
    for start, end, _ in sorted(spans, key=lambda s: s[0], reverse=True):
        end = min(end, scrub_start)
        if start < end:
            scrubbed_proposed = scrubbed_proposed[:start] + scrubbed_proposed[end:]

    reasons: list[str] = []
    for section_name in _DECISION_DIRECTIVE_SECTIONS:
        if section_name == "Proposed Solution":
            bodies = [scrubbed_proposed]
        elif section_name == "Files to Modify":
            bodies = _heading_bodies(content, section_name)
        else:
            body = _section_body(content, section_name)
            bodies = [body] if body else []
        bodies = [_strip_codebase_research_findings(body) for body in bodies]

        for identifier in sorted(discriminating):
            needle = f"`{identifier}`"
            fired = False
            for body in bodies:
                for p_start, p_end in _paragraph_spans(body):
                    paragraph = body[p_start:p_end]
                    if needle in paragraph and _SUPERSEDED_MARKER_PREFIX not in paragraph:
                        fired = True
                        break
                if fired:
                    break
            if fired:
                reasons.append(f"{section_name} still specifies `{identifier}` (rejected option)")
    return reasons


# BUG-3059: a well-formed dependency entry. The optional `P<n>-` prefix is the
# filename form and is tolerated here; anything else (bare number, typo'd type,
# free text) is a dropped graph edge waiting to happen.
_DEP_ID_RE = re.compile(r"(?:P[0-5]-)?(?:BUG|FEAT|ENH|EPIC)-\d+", re.IGNORECASE)

# ENH-3046: closed soft-dependency phrase list for the soft_dep_hard_edge gap
# class — proximity window is the blank-line-delimited paragraph containing
# the blocked_by/depends_on ID, not the same line (Expected Behavior).
_SOFT_DEP_PHRASE_RE = re.compile(
    r"\b(?:soft dep(?:endency)?|soft-dep|optional|nice to have|has(?:n't| not) landed)\b",
    re.IGNORECASE,
)


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    """Return (start, end) offsets of *text*'s blank-line-delimited paragraphs."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    end = 0
    pos = 0
    for line in text.splitlines(keepends=True):
        if line.strip():
            if start is None:
                start = pos
            end = pos + len(line.rstrip("\n"))
        elif start is not None:
            spans.append((start, end))
            start = None
        pos += len(line)
    if start is not None:
        spans.append((start, end))
    return spans


# ENH-3045: closed replacement-keyword list for the missing_behavior_parity
# gap class — matched as whole words, same line as the ref only (Program
# Design § Decision Rules condition 3; no multi-line proximity window in v1).
_BEHAVIOR_PARITY_KEYWORD_RE = re.compile(
    r"\b("
    r"delete|deletes|deleted|"
    r"remove|removes|removed|"
    r"replace|replaces|replaced|"
    r"rewrite|rewrites|rewritten|"
    r"supersede|supersedes|superseded|"
    r"delegate|delegates|delegated"
    r")\b",
    re.IGNORECASE,
)
# Scope condition (§ Decision Rules condition 1): only these sections name a
# replacement target; ### Similar Patterns/Documentation/Tests and Current
# Behavior/Session Log cite files as evidence or precedent, not as targets.
_BEHAVIOR_PARITY_SCOPE_H2_SECTIONS = ("Summary", "Proposed Solution")
_BEHAVIOR_PARITY_SCOPE_HEADINGS = ("Files to Modify",)


def _behavior_parity_scope_text(content: str) -> str:
    """Concatenate the sections the missing_behavior_parity scope condition covers."""
    parts = [
        body
        for name in _BEHAVIOR_PARITY_SCOPE_H2_SECTIONS
        for body in [_section_body(content, name)]
        if body
    ]
    for name in _BEHAVIOR_PARITY_SCOPE_HEADINGS:
        parts.extend(_heading_bodies(content, name))
    return "\n".join(parts)


# Current-state allowlist for stale_symbol_ref (BUG-3063, § Proposed Solution A1):
# only these H2 sections describe existing code, so only claims inside their
# H2 span (_section_body — swallows nested H3s, matching the behavior-parity
# helper's H2 branch) are read as existence assertions. Chosen over a denylist
# of "future state" section names: measured on the active backlog, the
# denylist clears 10% of false-positive hits versus this allowlist's 73%.
_STALE_SYMBOL_SCOPE_H2_SECTIONS = ("Summary", "Current Behavior", "Root Cause", "Context")


def _symbol_claim_scope_text(content: str) -> str:
    """Concatenate the sections the stale_symbol_ref scope condition covers."""
    return "\n".join(
        body
        for name in _STALE_SYMBOL_SCOPE_H2_SECTIONS
        for body in [_section_body(content, name)]
        if body
    )


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


# ENH-3244: `[bracket]`-shaped tokens and "TBD ..." bullet lines are the two
# shapes every shipped template's `creation_template` values use for unfilled
# placeholders (verified against all four `templates/*-sections.json`
# files). Anything else in a creation_template — headings, "N/A" defaults,
# static label text — is not a placeholder and must not be extracted, or a
# well-filled section would report a defect forever.
_PLACEHOLDER_BRACKET_RE = re.compile(r"\[[^\[\]\n]+\]")
_PLACEHOLDER_TBD_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*(TBD\b.*?)\s*$", re.MULTILINE)

# Mirrors `symbol_claims._BACKTICK_SPAN_RE` / `cli_claims._BACKTICK_SPAN_RE` /
# `prose_deps._BACKTICK_SPAN_RE` — same single-backtick-pair pattern, kept as
# its own copy per that existing (independently-defined, cross-referenced)
# convention rather than a new shared import.
_PLACEHOLDER_BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")

# Decision Rules › Masking part 3: `Program Design` is the only section whose
# `creation_template` already wraps every placeholder in backticks
# (`` `[FieldName]` ``, `` `[function_name]` ``, ...), so inline-code masking
# (part 2 below) would silently swallow it anyway. Excluding it here costs no
# coverage: a fully-templated `Program Design` body is already caught by the
# `boilerplate` gap class (whole-section equality against creation_template,
# a few dozen lines up in this function), and a partially-filled one is
# already caught by `program_design_nonspecific` (ENH-2852).
_TEMPLATE_PLACEHOLDER_EXCLUDED_SECTIONS = frozenset({_PROGRAM_DESIGN_TITLE})


def _template_placeholder_patterns(
    issue_type: str, templates_dir: Path | None = None
) -> dict[str, list[str]]:
    """Per-section placeholder strings derived from *issue_type*'s templates (ENH-3244).

    Runtime derivation, not a hand-copied list: reads the same
    ``creation_template`` values the ``boilerplate`` gap class already reads
    (a few dozen lines up in :func:`check_format_gaps`), so a placeholder
    line added to ``scripts/little_loops/templates/*-sections.json`` is
    picked up here with zero Python changes. ``Program Design`` is skipped
    entirely (see :data:`_TEMPLATE_PLACEHOLDER_EXCLUDED_SECTIONS`).

    Returns:
        A mapping of section name -> list of distinct placeholder strings
        that section's ``creation_template`` emits. Empty dict when the
        type's template cannot be loaded (fails open, mirroring
        :func:`check_format_gaps`).
    """
    from little_loops.issue_template import load_issue_sections

    try:
        sections_data = load_issue_sections(issue_type, templates_dir)
    except Exception:
        return {}

    patterns: dict[str, list[str]] = {}
    for group in ("common_sections", "type_sections"):
        for name, defn in sections_data.get(group, {}).items():
            if not isinstance(defn, dict) or name in _TEMPLATE_PLACEHOLDER_EXCLUDED_SECTIONS:
                continue
            template = defn.get("creation_template", "")
            if not template:
                continue
            tokens: list[str] = []
            seen: set[str] = set()
            for m in _PLACEHOLDER_BRACKET_RE.finditer(template):
                token = m.group(0)
                if token not in seen:
                    seen.add(token)
                    tokens.append(token)
            for m in _PLACEHOLDER_TBD_LINE_RE.finditer(template):
                token = m.group(1).strip()
                if token and token not in seen:
                    seen.add(token)
                    tokens.append(token)
            if tokens:
                patterns[name] = tokens
    return patterns


def _template_placeholders(
    content: str, issue_type: str, templates_dir: Path | None = None
) -> list[str]:
    """Gap-report strings for the ``template_placeholders`` class (ENH-3244).

    Applies the three-part masking rule (Decision Rules › Masking,
    ENH-3244's own Program Design section):

    1. **Section-scoped** — a placeholder counts only inside the body of the
       section whose ``creation_template`` emits it
       (:func:`_section_body_with_offset`), not any other section.
    2. **Inline-code masked, composed with fence masking** — a backtick-pair
       span scan whose matches are appended into the same list
       :func:`~little_loops.text_utils.fence_spans` produces, then
       :func:`~little_loops.text_utils.in_fence` is reused unmodified to
       check containment — the composition ``issues/prose_deps.py`` already
       uses for the same reason (a section's own prose legitimately names
       its own placeholder string as documentation).
    3. **``Program Design`` excluded** from the pattern set entirely (see
       :data:`_TEMPLATE_PLACEHOLDER_EXCLUDED_SECTIONS`).

    Each distinct placeholder is reported at most once per section, even if
    it occurs multiple times (mirrors ``duplicate_heading``'s one-entry-per-
    group shape) — but a masked occurrence does not suppress a later
    unmasked occurrence of the same token in the same section.
    """
    patterns = _template_placeholder_patterns(issue_type, templates_dir)
    if not patterns:
        return []

    inline_spans = [(m.start(), m.end()) for m in _PLACEHOLDER_BACKTICK_SPAN_RE.finditer(content)]
    masks = fence_spans(content) + inline_spans

    gaps: list[str] = []
    for name, tokens in patterns.items():
        section = _section_body_with_offset(content, name)
        if section is None:
            continue
        body, offset = section
        for token in tokens:
            start = 0
            while True:
                idx = body.find(token, start)
                if idx == -1:
                    break
                abs_start = offset + idx
                abs_end = abs_start + len(token)
                if not in_fence(abs_start, abs_end, masks):
                    gaps.append(f"{name}: {token}")
                    break
                start = idx + 1
    return gaps


def _replace_template_placeholder_tokens(content: str, values: dict[str, str]) -> str:
    """Replace masked, section-scoped placeholder tokens with derived values (ENH-3248).

    *values* maps ``"{section}: {token}"`` gap strings — the exact format
    :func:`_template_placeholders` reports — to their replacement text.
    Mirrors that function's section-scoping and fence/inline-code masking
    exactly, but replaces the first unmasked occurrence per entry instead of
    only recording it, matching its "each distinct placeholder is reported
    at most once per section" contract — so a second pass over an already-
    filled file finds no remaining unmasked occurrence and is a no-op
    (idempotent), and a section's own prose naming its placeholder as
    documentation is left untouched.
    """
    inline_spans = [(m.start(), m.end()) for m in _PLACEHOLDER_BACKTICK_SPAN_RE.finditer(content)]
    masks = fence_spans(content) + inline_spans

    replacements: list[tuple[int, int, str]] = []
    for entry, replacement in values.items():
        section, _, token = entry.partition(": ")
        result = _section_body_with_offset(content, section)
        if result is None:
            continue
        body, offset = result
        start = 0
        while True:
            idx = body.find(token, start)
            if idx == -1:
                break
            abs_start = offset + idx
            abs_end = abs_start + len(token)
            if not in_fence(abs_start, abs_end, masks):
                replacements.append((abs_start, abs_end, replacement))
                break
            start = idx + 1

    out = content
    for start, end, replacement in sorted(replacements, key=lambda r: r[0], reverse=True):
        out = out[:start] + replacement + out[end:]
    return out


def placeholder_count(issue_path: Path, templates_dir: Path | None = None) -> int:
    """Count unfilled template placeholders in *issue_path* (ENH-3244).

    The deterministic public accessor over :func:`_template_placeholders`,
    mirroring :func:`superseded_marker_count`'s shape: reused by both
    ``check_format_gaps`` (via ``FormatGaps.template_placeholders``) and any
    non-LLM gate that wants the scalar count directly. Returns 0 for an
    unreadable/missing file or a file whose type cannot be determined —
    fails open like every other deterministic accessor in this module.
    """
    try:
        content = issue_path.read_text()
    except OSError:
        return 0
    type_match = _ISSUE_TYPE_RE.search(issue_path.name)
    if not type_match:
        return 0
    return len(_template_placeholders(content, type_match.group(1), templates_dir))


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

# ENH-2966 Option F1c: optional trailing plural "s" only on the high-signal
# multi-word/rare keywords, never on doc/docs/guide/documentation — an
# unrestricted plural (F1b) reopens the `docs/guides/…_GUIDE.md` false-positive
# hole the leading `_` guard below was added to close.
_PLURAL_SAFE = frozenset(
    {"broken link", "broken anchor", "fix link", "typo", "readme", "changelog"}
)
# Word-boundary match: the leading guard excludes `[a-z0-9_]` so a keyword
# doesn't match inside an identifier or underscore-separated filename
# (`subdoc`, `HARNESS_OPTIMIZATION_GUIDE.md`); the trailing guard excludes
# `[a-z]` so `doc` doesn't match the head of `documentation`/`docs`. Precompiled
# once at module load so an `--all` sweep doesn't recompile 11 patterns per issue.
_TESTABLE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(rf"(?<![a-z0-9_]){re.escape(kw)}{'s?' if kw in _PLURAL_SAFE else ''}(?![a-z])")
    for kw in _TESTABLE_SIGNAL_KEYWORDS
)


def _count_testable_keyword_matches(text: str) -> int:
    """Count distinct `_TESTABLE_SIGNAL_KEYWORDS` present (word-boundary, case-insensitive) in *text*."""
    lowered = text.lower()
    return sum(1 for pattern in _TESTABLE_PATTERNS if pattern.search(lowered))


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
# ENH-3031: widened with hedge vocabulary that accumulates via --gap-analysis
# (additive, never removes content) and is never subsequently closed.
#
# BUG-3169: `open question` is split into a DECLARATION alternative and a
# citation-suppressing prose alternative, because a CITATION of a numbered
# question ("On Open Question 1: option (c) is confirmed not free", "relevant to
# Open Question 1's option (a)") is exactly the prose /ll:refine-issue
# --gap-analysis deposits when it ANSWERS a question. Counting those made the
# tally rise with every refine pass, so refine-to-ready-issue's check_hedges gate
# became unclearable — burning the refine budget and reaching breakdown_issue
# without ever running confidence_check.
#
# The discriminator is POSITION plus a declaration boundary, not the mere
# presence of a digit:
#   - Declaration (counts): the item OPENS with the phrase and the phrase is
#     followed by `:` / `.` / `—` / `**` / end — "- **Open Question 2:** Should
#     the policy be enforced at build time?", "- Open Question 3. Decide the
#     default transport." This must not depend on the `\?\s*$` alternative,
#     which anchors to the END of the joined item and therefore misses any
#     question carrying a wrapped continuation line (see
#     _count_unresolved_items_in_text).
#   - Citation (suppressed): the phrase appears mid-item after other prose, is
#     plural ("Open Questions 2 and 3 were folded in"), or continues into a verb
#     phrase / possessive rather than a declaration boundary.
# An unnumbered prose hedge ("this remains an open question") — the ENH-2446
# case the phrase was originally added for — still matches anywhere via the
# second alternative.
_OPEN_QUESTION_SIGNAL_RE = re.compile(
    r"\?\s*$"  # ends with question mark
    r"|^\s*-\s*\*\*Q\d*"  # **Q1.** style
    r"|^\s*-\s*Q:"  # Q: prefix
    # BUG-3169: item-leading declaration, numbered or not
    r"|^\s*(?:[-*]|\d+[.)])\s*[*_]{0,2}open question\b(?:\s*#?\s*\d+)?\s*(?:[:.*_—]|$)"
    # BUG-3169: prose hedge anywhere, but never a numbered citation
    r"|\bopen questions?\b(?!\s*[#:]?\s*\d)"
    r"|\bneeds decision\b"
    r"|\bdecision needed\b"
    r"|\bopen decision\b"
    r"|\bunresolved decision\b"
    r"|\bdecision point\b"
    r"|\bworth confirming\b"
    r"|\bworth checking\b"
    r"|\bshould be considered\b"
    # ENH-3244: `\bTBD\b` moved to the `template_placeholders` structural gap
    # (deterministic, uncapped) — this hedge scan's capped budget
    # (BUG-3170) now spends only on genuine prose hedges below.
    r"|\bto be determined\b"
    r"|\bneeds confirmation\b"
    r"|\bworth a decision\b"
    r"|\bworth deciding\b",
    re.IGNORECASE,
)


# ENH-3031: widened to the sections refine/wire actually deposit prose into —
# the original three-section scan missed hedges left in research findings and
# design notes, which is where the additive --gap-analysis pass accumulates them.
_OPEN_QUESTION_SECTIONS = (
    "Edge Cases",
    "Confidence Check Notes",
    "Open Questions",
    "Integration Map",
    "Codebase Research Findings",
    "Suggested Fix Direction",
    "Program Design",
)


def _is_list_item_start(stripped: str) -> bool:
    """Return True if *stripped* starts a new bullet/numbered list item."""
    return stripped.startswith(("-", "*")) or (
        len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in (".", ")")
    )


def _count_unresolved_items_in_text(text: str) -> int:
    """Count bullet/numbered items carrying an open-question signal and NOT a RESOLVED marker.

    ENH-3031: wrapped continuation lines (prose that spills onto subsequent
    physical lines without a leading bullet marker — the common shape for
    refine/wire-deposited paragraphs) are joined onto the item that started
    them before signal matching, so a hedge phrase split across a line wrap
    (e.g. "Worth\\nconfirming ...") is still detected.
    """
    if not text:
        return 0
    unresolved = 0
    item_lines: list[str] = []

    def _flush() -> None:
        nonlocal unresolved
        if not item_lines:
            return
        joined = " ".join(item_lines)
        if not _RESOLVED_QUESTION_MARKER_RE.search(joined) and _OPEN_QUESTION_SIGNAL_RE.search(
            joined
        ):
            unresolved += 1

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            _flush()
            item_lines = []
            continue
        if _is_list_item_start(stripped):
            _flush()
            item_lines = [stripped]
        elif item_lines and not stripped.startswith("#"):
            item_lines.append(stripped)
        else:
            _flush()
            item_lines = []
    _flush()
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
        effort = self._coerce_optional_int(frontmatter.get("effort"))
        impact = self._coerce_optional_int(frontmatter.get("impact"))
        confidence_score = self._coerce_optional_int(frontmatter.get("confidence_score"))
        outcome_confidence = self._coerce_optional_int(frontmatter.get("outcome_confidence"))
        score_complexity = self._coerce_optional_int(frontmatter.get("score_complexity"))
        score_test_coverage = self._coerce_optional_int(frontmatter.get("score_test_coverage"))
        score_ambiguity = self._coerce_optional_int(frontmatter.get("score_ambiguity"))
        score_change_surface = self._coerce_optional_int(frontmatter.get("score_change_surface"))
        testable_value = self._coerce_tristate_bool(frontmatter.get("testable"))
        decision_needed_value = self._coerce_tristate_bool(frontmatter.get("decision_needed"))
        missing_artifacts_value = self._coerce_tristate_bool(frontmatter.get("missing_artifacts"))
        implementation_order_risk_value = self._coerce_tristate_bool(
            frontmatter.get("implementation_order_risk")
        )

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

    def _coerce_optional_int(self, raw: Any) -> int | None:
        """Coerce a frontmatter value to int, rejecting non-digit strings.

        Args:
            raw: Raw frontmatter value

        Returns:
            The coerced int, or None if raw is None or not a digit string.
            Uses ``str.isdigit()``, so negatives, floats, and signed strings
            all coerce to None rather than a numeric value.
        """
        return int(raw) if raw is not None and str(raw).isdigit() else None

    def _coerce_tristate_bool(self, raw: Any) -> Any:
        """Coerce a frontmatter value to a tri-state bool.

        Args:
            raw: Raw frontmatter value

        Returns:
            For string input: True/False if it lowercases to "true"/"false",
            else None. Non-string input (including native YAML bool/None) is
            returned unchanged, so the return type is intentionally not
            ``bool | None`` — annotated as ``Any`` to reflect that pass-through.
        """
        if isinstance(raw, str):
            return raw.lower() == "true" if raw.lower() in ("true", "false") else None
        return raw


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
        except Exception:  # pragma: no cover - defensive, mirrors sprint.py
            logger.debug("Dependency mapping unavailable — falling back to active ID set")
            all_known_ids = {info.issue_id for info in all_active}
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

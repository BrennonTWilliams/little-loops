"""Issue file parsing for little-loops.

Parses issue markdown files to extract metadata like priority, ID, type, and title.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.cli_args import _id_matches
from little_loops.frontmatter import parse_frontmatter

if TYPE_CHECKING:
    from little_loops.config import BRConfig


logger = logging.getLogger(__name__)

# Regex pattern for issue IDs in list items
# Matches: "- FEAT-001", "- BUG-123", "* ENH-005", "- FEAT-001 (some note)"
# Also handles bold markdown: "- **ENH-1000**: description"
ISSUE_ID_PATTERN = re.compile(r"^[-*]\s+\*{0,2}([A-Z]+-\d+)", re.MULTILINE)


_NORMALIZED_RE = re.compile(r"^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$")
_ISSUE_TYPE_RE = re.compile(r"-(BUG|FEAT|ENH|EPIC)-")


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

    required = _required_sections(sections_data)
    if not required:
        return True

    headings = {m.strip() for m in re.findall(r"^##\s+(.+)$", content, re.MULTILINE)}
    return required.issubset(headings)


# Extracts a canonical replacement name from a deprecation_reason string, e.g.
# "Renamed to 'Proposed Solution' in v2.0" or "Consolidated into 'API/Interface' section".
_DEPRECATION_CANONICAL_RE = re.compile(r"(?:Renamed to|Consolidated into|Redundant with) '([^']+)'")


def _section_body(content: str, heading: str) -> str | None:
    """Return the raw text between a ``## heading`` line and the next ``##`` line.

    Returns None when the heading is absent.
    """
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, content, re.MULTILINE)
    if match is None:
        return None
    start = match.end()
    next_match = re.search(r"^##\s", content[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(content)
    return content[start:end]


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

    @property
    def has_gaps(self) -> bool:
        """True when any gap category is non-empty."""
        return bool(self.missing or self.renamed or self.empty or self.boilerplate)

    def to_dict(self) -> dict[str, list[str]]:
        """Serialize to a JSON-serializable dict for --format json output."""
        return {
            "missing": self.missing,
            "renamed": self.renamed,
            "empty": self.empty,
            "boilerplate": self.boilerplate,
        }


def check_format_gaps(issue_path: Path, templates_dir: Path | None = None) -> FormatGaps:
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

    Args:
        issue_path: Path to the issue markdown file.
        templates_dir: Optional override for the templates directory.

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

    type_match = _ISSUE_TYPE_RE.search(issue_path.name)
    if not type_match:
        return gaps
    issue_type = type_match.group(1)

    try:
        sections_data = load_issue_sections(issue_type, templates_dir)
    except Exception:
        return gaps

    required = _required_sections(sections_data)
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

    return gaps


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
        depends_on: List of issue IDs this issue depends on (soft prerequisite)
        relates_to: List of related issue IDs; populated from frontmatter `relates_to:` or deprecated `related:`
        duplicate_of: Issue ID that this issue duplicates
    """

    path: Path
    issue_type: str
    priority: str
    issue_id: str
    title: str
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    parent: str | None = None
    depends_on: list[str] = field(default_factory=list)
    relates_to: list[str] = field(default_factory=list)
    duplicate_of: str | None = None
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
            logger.warning(
                "%s: deprecated frontmatter key 'parent_issue' — rename to 'parent'",
                issue_path.name,
            )
            parent = alias_val

        duplicate_of = frontmatter.get("duplicate_of")

        relates_to: list[str] = []
        if alias_val := frontmatter.get("related"):
            logger.warning(
                "%s: deprecated frontmatter key 'related' — rename to 'relates_to'",
                issue_path.name,
            )
            relates_to = (
                [id.strip() for id in alias_val.strip("\"'").split(",") if id.strip()]
                if isinstance(alias_val, str)
                else list(alias_val)
            )

        depends_on: list[str] = []

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
            depends_on=depends_on,
            relates_to=relates_to,
            duplicate_of=duplicate_of,
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

    for cat in categories:
        issue_dir = config.get_issue_dir(cat)
        if not issue_dir.exists():
            continue

        for issue_file in issue_dir.glob("*.md"):
            info = parser.parse_file(issue_file)
            # Status-based filter
            if status_filter is None:
                if info.status in ("done", "cancelled", "deferred"):
                    continue
            elif info.status not in status_filter:
                continue
            # Apply skip filter
            if info.issue_id in skip_ids:
                continue
            # Apply only filter (if specified)
            if only_ids is not None and not any(_id_matches(info.issue_id, p) for p in only_ids):
                continue
            # Apply type filter (if specified)
            if type_prefixes is not None:
                prefix = info.issue_id.split("-", 1)[0]
                if prefix not in type_prefixes:
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

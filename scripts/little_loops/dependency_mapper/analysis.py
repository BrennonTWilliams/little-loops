"""Dependency analysis functions.

Functions for computing conflict scores, finding file overlaps,
validating dependency references, and orchestrating full dependency analysis.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from little_loops.dependency_graph import DependencyGraph
from little_loops.dependency_mapper.models import (
    DependencyProposal,
    DependencyReport,
    ParallelSafePair,
    ValidationResult,
)
from little_loops.text_utils import extract_file_paths

if TYPE_CHECKING:
    from little_loops.config import DependencyMappingConfig
    from little_loops.issue_parser import IssueInfo

logger = logging.getLogger(__name__)

_CODE_FENCE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

# Semantic target extraction patterns
_PASCAL_CASE = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b")
_FUNCTION_REF = re.compile(r"`(\w+)\(\)`")
_COMPONENT_SCOPE = re.compile(
    r"(?:component|module|class|widget|section)[:\s]+[`\"']?([a-zA-Z0-9_./\-]{3,})[`\"']?",
    re.IGNORECASE,
)

# UI region / section keywords mapped to canonical names
_SECTION_KEYWORDS: dict[str, frozenset[str]] = {
    "header": frozenset({"header", "navbar", "toolbar", "top bar"}),
    "body": frozenset({"droppable"}),
    "footer": frozenset({"footer", "status bar", "action bar"}),
    "sidebar": frozenset({"sidebar", "side panel", "drawer"}),
    "card": frozenset({"card", "tile"}),
    "modal": frozenset({"modal", "dialog", "popup", "overlay"}),
    "form": frozenset({"form"}),
}

# Modification type classification keywords
_MODIFICATION_TYPES: dict[str, frozenset[str]] = {
    "structural": frozenset(
        {
            "extract",
            "split",
            "refactor",
            "restructure",
            "reorganize",
            "create new component",
            "break out",
            "separate",
            "decompose",
        }
    ),
    "infrastructure": frozenset(
        {
            "listener",
            "provider",
            "state management",
            "routing",
            "middleware",
            "dragging",
            "drag",
            "drop",
            "dnd",
        }
    ),
    "enhancement": frozenset(
        {
            "add button",
            "add field",
            "add column",
            "add stats",
            "add icon",
            "add toggle",
            "empty state",
            "placeholder",
            "tooltip",
            "badge",
        }
    ),
}


def _extract_semantic_targets(content: str) -> set[str]:
    """Extract component and function references from issue content.

    Identifies PascalCase component names, function references,
    and explicitly mentioned component/module scopes.

    Args:
        content: Issue file content

    Returns:
        Set of normalized semantic target names
    """
    if not content:
        return set()

    stripped = _CODE_FENCE.sub("", content)
    targets: set[str] = set()

    for match in _PASCAL_CASE.finditer(stripped):
        targets.add(match.group(1).lower())

    for match in _FUNCTION_REF.finditer(stripped):
        targets.add(match.group(1).lower())

    for match in _COMPONENT_SCOPE.finditer(stripped):
        targets.add(match.group(1).lower())

    return targets


def _extract_section_mentions(content: str) -> set[str]:
    """Extract UI region/section references from issue content.

    Maps keywords like "header", "body", "sidebar" to canonical
    section names using word-boundary matching.

    Args:
        content: Issue file content

    Returns:
        Set of canonical section names mentioned
    """
    if not content:
        return set()

    content_lower = content.lower()
    sections: set[str] = set()

    for section_name, keywords in _SECTION_KEYWORDS.items():
        for keyword in keywords:
            # Use word boundary for single words, substring for multi-word phrases
            if " " in keyword:
                if keyword in content_lower:
                    sections.add(section_name)
                    break
            else:
                if re.search(rf"\b{re.escape(keyword)}\b", content_lower):
                    sections.add(section_name)
                    break

    return sections


def _classify_modification_type(content: str) -> str:
    """Classify the modification type of an issue.

    Returns one of: "structural", "infrastructure", "enhancement".
    Falls back to "enhancement" if no clear match.

    Args:
        content: Issue file content

    Returns:
        Modification type classification string
    """
    if not content:
        return "enhancement"

    content_lower = content.lower()

    for mod_type in ("structural", "infrastructure", "enhancement"):
        keywords = _MODIFICATION_TYPES[mod_type]
        for keyword in keywords:
            if keyword in content_lower:
                return mod_type

    return "enhancement"


def compute_conflict_score(
    content_a: str,
    content_b: str,
    *,
    config: DependencyMappingConfig | None = None,
) -> float:
    """Compute semantic conflict score between two issues.

    Combines three signals with configurable weights:
    - Semantic target overlap (component/function names)
    - Section mention overlap (UI regions)
    - Modification type match

    Args:
        content_a: First issue's file content
        content_b: Second issue's file content
        config: Optional dependency mapping config for custom scoring weights.
            Falls back to default weights (0.5/0.3/0.2) when not provided.

    Returns:
        Conflict score from 0.0 (parallel-safe) to 1.0 (definite conflict)
    """
    targets_a = _extract_semantic_targets(content_a)
    targets_b = _extract_semantic_targets(content_b)

    sections_a = _extract_section_mentions(content_a)
    sections_b = _extract_section_mentions(content_b)

    type_a = _classify_modification_type(content_a)
    type_b = _classify_modification_type(content_b)

    # Resolve scoring weights from config or defaults
    w_semantic = config.scoring_weights.semantic if config else 0.5
    w_section = config.scoring_weights.section if config else 0.3
    w_type = config.scoring_weights.type if config else 0.2

    # Signal 1: Semantic target overlap (0.0 - 1.0)
    if targets_a and targets_b:
        target_union = len(targets_a | targets_b)
        target_score = len(targets_a & targets_b) / target_union if target_union > 0 else 0.0
    else:
        target_score = 0.5  # Unknown — default to moderate

    # Signal 2: Section overlap (0.0 or 1.0)
    if sections_a and sections_b:
        section_score = 1.0 if sections_a & sections_b else 0.0
    else:
        section_score = 0.5  # Unknown

    # Signal 3: Modification type match (0.0 or 1.0)
    type_score = 1.0 if type_a == type_b else 0.0

    return round(target_score * w_semantic + section_score * w_section + type_score * w_type, 2)


def find_file_overlaps(
    issues: list[IssueInfo],
    issue_contents: dict[str, str],
    *,
    config: DependencyMappingConfig | None = None,
) -> tuple[list[DependencyProposal], list[ParallelSafePair]]:
    """Find issues that reference overlapping files and propose dependencies.

    For each pair of issues where both reference the same file(s), computes
    a semantic conflict score. High-conflict pairs get dependency proposals;
    low-conflict pairs are reported as parallel-safe.

    Pairs that already have a dependency relationship are skipped.

    Args:
        issues: List of parsed issue objects
        issue_contents: Mapping from issue_id to file content
        config: Optional dependency mapping config for custom thresholds.
            Falls back to hardcoded defaults when not provided.

    Returns:
        Tuple of (proposed dependencies, parallel-safe pairs)
    """
    # Build existing dependency set for skip check
    existing_deps: set[tuple[str, str]] = set()
    for issue in issues:
        for blocker_id in issue.blocked_by:
            existing_deps.add((issue.issue_id, blocker_id))

    # Extract file paths per issue
    issue_paths: dict[str, set[str]] = {}
    for issue in issues:
        content = issue_contents.get(issue.issue_id, "")
        paths = extract_file_paths(content)
        if paths:
            issue_paths[issue.issue_id] = paths

    proposals: list[DependencyProposal] = []
    parallel_safe: list[ParallelSafePair] = []
    issue_ids = sorted(issue_paths.keys())

    _type_order = {"structural": 0, "infrastructure": 1, "enhancement": 2}

    for i, id_a in enumerate(issue_ids):
        for id_b in issue_ids[i + 1 :]:
            overlap = issue_paths[id_a] & issue_paths[id_b]
            if not overlap:
                continue

            # Skip if dependency already exists (in either direction)
            if (id_a, id_b) in existing_deps or (id_b, id_a) in existing_deps:
                continue

            content_a = issue_contents.get(id_a, "")
            content_b = issue_contents.get(id_b, "")
            conflict = compute_conflict_score(content_a, content_b, config=config)

            overlap_list = sorted(overlap)

            # Resolve conflict threshold from config or default
            conflict_threshold = config.conflict_threshold if config else 0.4

            # Low-conflict pairs are parallel-safe
            if conflict < conflict_threshold:
                sections_a = _extract_section_mentions(content_a)
                sections_b = _extract_section_mentions(content_b)
                if sections_a and sections_b:
                    reason = (
                        f"Different sections ({', '.join(sorted(sections_a))}"
                        f" vs {', '.join(sorted(sections_b))})"
                    )
                else:
                    reason = "Low semantic conflict score"
                parallel_safe.append(
                    ParallelSafePair(
                        issue_a=id_a,
                        issue_b=id_b,
                        shared_files=overlap_list,
                        conflict_score=conflict,
                        reason=reason,
                    )
                )
                continue

            # Determine direction for high-conflict pairs
            issue_a = next(iss for iss in issues if iss.issue_id == id_a)
            issue_b = next(iss for iss in issues if iss.issue_id == id_b)

            confidence_modifier = 1.0

            if issue_a.priority_int != issue_b.priority_int:
                # Different priorities: higher priority blocks lower
                if issue_a.priority_int < issue_b.priority_int:
                    target_id, source_id = id_a, id_b
                else:
                    target_id, source_id = id_b, id_a
            else:
                # Same priority: use modification type ordering
                type_a = _classify_modification_type(content_a)
                type_b = _classify_modification_type(content_b)
                order_a = _type_order.get(type_a, 2)
                order_b = _type_order.get(type_b, 2)

                if order_a != order_b:
                    if order_a < order_b:
                        target_id, source_id = id_a, id_b
                    else:
                        target_id, source_id = id_b, id_a
                else:
                    # Fall back to ID ordering with reduced confidence
                    if id_a < id_b:
                        target_id, source_id = id_a, id_b
                    else:
                        target_id, source_id = id_b, id_a
                    confidence_modifier = config.confidence_modifier if config else 0.5

            min_paths = min(len(issue_paths[id_a]), len(issue_paths[id_b]))
            confidence = len(overlap) / min_paths if min_paths > 0 else 0.0
            confidence *= confidence_modifier

            rationale = (
                f"{source_id} and {target_id} both reference "
                f"{', '.join(overlap_list[:3])}"
                f"{' and more' if len(overlap_list) > 3 else ''}. "
                f"{target_id} has higher priority and should be completed first."
            )

            proposals.append(
                DependencyProposal(
                    source_id=source_id,
                    target_id=target_id,
                    reason="file_overlap",
                    confidence=round(confidence, 2),
                    rationale=rationale,
                    overlapping_files=overlap_list,
                    conflict_score=conflict,
                )
            )

    # Sort by confidence descending
    proposals.sort(key=lambda p: -p.confidence)
    return proposals, parallel_safe


def validate_dependencies(
    issues: list[IssueInfo],
    completed_ids: set[str] | None = None,
    all_known_ids: set[str] | None = None,
) -> ValidationResult:
    """Validate existing dependency references for integrity.

    Checks:
    - Broken refs: blocked_by entries referencing nonexistent issues
    - Missing backlinks: A blocks B but B doesn't list A in blocked_by
    - Cycles: circular dependency chains
    - Stale completed refs: blocked_by entries referencing completed issues

    Args:
        issues: List of parsed issue objects
        completed_ids: Set of completed issue IDs
        all_known_ids: Set of all issue IDs that exist on disk (across all
            categories and completed). When provided, references to issues
            in this set are not flagged as broken even if they are not in
            the working ``issues`` list.

    Returns:
        ValidationResult with all detected problems
    """
    completed = completed_ids or set()
    result = ValidationResult()

    active_ids = {issue.issue_id for issue in issues}
    all_known = active_ids | completed
    if all_known_ids:
        all_known = all_known | all_known_ids

    # Build lookup maps
    blocked_by_map: dict[str, set[str]] = {}
    blocks_map: dict[str, set[str]] = {}
    for issue in issues:
        blocked_by_map[issue.issue_id] = set(issue.blocked_by)
        blocks_map[issue.issue_id] = set(issue.blocks)

    for issue in issues:
        for ref_id in issue.blocked_by:
            if ref_id not in all_known:
                result.broken_refs.append((issue.issue_id, ref_id))
            elif ref_id in completed:
                result.stale_completed_refs.append((issue.issue_id, ref_id))

        # Check backlinks: if A.blocked_by contains B, then B.blocks should contain A
        for ref_id in issue.blocked_by:
            if ref_id in active_ids:
                target_blocks = blocks_map.get(ref_id, set())
                if issue.issue_id not in target_blocks:
                    result.missing_backlinks.append((issue.issue_id, ref_id))

    # Cycle detection using DependencyGraph
    graph = DependencyGraph.from_issues(issues, completed, all_known_ids=all_known_ids)
    result.cycles = graph.detect_cycles()

    return result


def analyze_dependencies(
    issues: list[IssueInfo],
    issue_contents: dict[str, str],
    completed_ids: set[str] | None = None,
    all_known_ids: set[str] | None = None,
    *,
    config: DependencyMappingConfig | None = None,
) -> DependencyReport:
    """Run full dependency analysis: discovery and validation.

    Args:
        issues: List of parsed issue objects
        issue_contents: Mapping from issue_id to file content
        completed_ids: Set of completed issue IDs
        all_known_ids: Set of all issue IDs that exist on disk
        config: Optional dependency mapping config for custom thresholds.

    Returns:
        Comprehensive dependency report
    """
    proposals, parallel_safe = find_file_overlaps(issues, issue_contents, config=config)
    validation = validate_dependencies(issues, completed_ids, all_known_ids)

    existing_dep_count = sum(len(issue.blocked_by) for issue in issues)

    return DependencyReport(
        proposals=proposals,
        parallel_safe=parallel_safe,
        validation=validation,
        issue_count=len(issues),
        existing_dep_count=existing_dep_count,
    )

"""Dependency mapper data models.

Dataclasses for cross-issue dependency discovery and validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DependencyProposal:
    """A proposed dependency relationship between two issues.

    Attributes:
        source_id: Issue that would be blocked
        target_id: Issue that would block (the blocker)
        reason: Category of discovery method
        confidence: Score from 0.0 to 1.0
        rationale: Human-readable explanation
        overlapping_files: Files referenced by both issues
        conflict_score: Semantic conflict score from 0.0 to 1.0
    """

    source_id: str
    target_id: str
    reason: str
    confidence: float
    rationale: str
    overlapping_files: list[str] = field(default_factory=list)
    conflict_score: float = 0.5


@dataclass
class ParallelSafePair:
    """A pair of issues that share files but can safely run in parallel.

    Attributes:
        issue_a: First issue ID
        issue_b: Second issue ID
        shared_files: Files referenced by both issues
        conflict_score: Semantic conflict score (< 0.4)
        reason: Why these are parallel-safe
    """

    issue_a: str
    issue_b: str
    shared_files: list[str] = field(default_factory=list)
    conflict_score: float = 0.0
    reason: str = ""


@dataclass
class ValidationResult:
    """Result of validating existing dependency references.

    Attributes:
        broken_refs: (issue_id, missing_ref_id) pairs
        missing_backlinks: (issue_id, should_have_backlink_from) pairs
        cycles: Cycle paths from DependencyGraph.detect_cycles()
        stale_completed_refs: (issue_id, completed_ref_id) pairs
    """

    broken_refs: list[tuple[str, str]] = field(default_factory=list)
    missing_backlinks: list[tuple[str, str]] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    stale_completed_refs: list[tuple[str, str]] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """Return True if any validation problems were found."""
        return bool(
            self.broken_refs or self.missing_backlinks or self.cycles or self.stale_completed_refs
        )


@dataclass
class DependencyReport:
    """Complete dependency analysis report.

    Attributes:
        proposals: Proposed new dependency relationships
        parallel_safe: Pairs of issues that share files but can run in parallel
        validation: Validation results for existing dependencies
        issue_count: Total issues analyzed
        existing_dep_count: Number of existing dependency edges
    """

    proposals: list[DependencyProposal] = field(default_factory=list)
    parallel_safe: list[ParallelSafePair] = field(default_factory=list)
    validation: ValidationResult = field(default_factory=ValidationResult)
    issue_count: int = 0
    existing_dep_count: int = 0


@dataclass
class FixResult:
    """Result of auto-fixing dependency validation issues.

    Attributes:
        changes: Human-readable descriptions of each fix applied
        modified_files: Set of file paths that were modified
        skipped_cycles: Number of cycles skipped (out of scope for auto-fix)
    """

    changes: list[str] = field(default_factory=list)
    modified_files: set[str] = field(default_factory=set)
    skipped_cycles: int = 0

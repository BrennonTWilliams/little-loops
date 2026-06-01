"""Cross-issue dependency discovery and mapping.

Analyzes active issues to discover potential dependencies based on
file overlap and validates existing dependency references for integrity.

Complements dependency_graph.py:
- dependency_graph.py = execution ordering (existing, unchanged)
- dependency_mapper    = discovery and proposal of new relationships

Public exports:
    # Models
    DependencyProposal: A proposed dependency relationship between two issues
    ParallelSafePair: A pair of issues safe to run in parallel
    ValidationResult: Result of validating existing dependency references
    DependencyReport: Complete dependency analysis report
    FixResult: Result of auto-fixing dependency validation issues

    # Analysis
    compute_conflict_score: Compute semantic conflict score between two issues
    find_file_overlaps: Find issues with overlapping file references
    validate_dependencies: Validate existing dependency references
    validate_frontmatter_fields: Warn about deprecated relationship frontmatter keys
    analyze_dependencies: Run full dependency analysis

    # Formatting
    format_report: Format a dependency report as markdown
    format_text_graph: Generate an ASCII dependency graph
    format_epic_tree: Render an EPIC's child hierarchy as a Unicode box-drawing tree

    # Operations
    apply_proposals: Write approved proposals to issue files
    fix_dependencies: Auto-repair broken dependency references
    gather_all_issue_ids: Scan all issue directories for issue IDs

    # Utilities
    extract_file_paths: Extract file paths from issue content (from text_utils)

    # CLI
    main: Entry point for ll-deps command
"""

from little_loops.dependency_mapper.analysis import (
    analyze_dependencies,
    compute_conflict_score,
    find_file_overlaps,
    validate_dependencies,
    validate_frontmatter_fields,
)
from little_loops.dependency_mapper.formatting import (
    format_epic_tree,
    format_report,
    format_text_graph,
)
from little_loops.dependency_mapper.models import (
    DependencyProposal,
    DependencyReport,
    FixResult,
    ParallelSafePair,
    ValidationResult,
)
from little_loops.dependency_mapper.operations import (
    _remove_from_section,
    apply_proposals,
    fix_dependencies,
    gather_all_issue_ids,
)
from little_loops.text_utils import extract_file_paths

__all__ = [
    # Models
    "DependencyProposal",
    "ParallelSafePair",
    "ValidationResult",
    "DependencyReport",
    "FixResult",
    # Analysis
    "compute_conflict_score",
    "find_file_overlaps",
    "validate_dependencies",
    "validate_frontmatter_fields",
    "analyze_dependencies",
    # Formatting
    "format_epic_tree",
    "format_report",
    "format_text_graph",
    # Operations
    "apply_proposals",
    "fix_dependencies",
    "gather_all_issue_ids",
    # Utilities
    "extract_file_paths",
    # Private functions re-exported for test access
    "_remove_from_section",
]

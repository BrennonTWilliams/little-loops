"""Dependency graph for issue management.

Constructs a directed acyclic graph (DAG) from issue dependencies,
providing topological sorting and cycle detection.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.issue_parser import IssueInfo

logger = logging.getLogger(__name__)


@dataclass
class WaveContentionNote:
    """Annotation for a wave that was split due to file contention."""

    contended_paths: list[str]
    sub_wave_index: int
    total_sub_waves: int


@dataclass
class DependencyGraph:
    """Directed acyclic graph of issue dependencies.

    Builds a graph from issue dependencies where edges represent
    "blocked by" relationships. Provides methods for:
    - Topological sorting (dependency order)
    - Cycle detection
    - Ready issue queries (blockers resolved)
    - Blocking issue queries

    Attributes:
        issues: Mapping from issue_id to IssueInfo
        blocked_by: Mapping from issue_id to set of blocking issue_ids
        blocks: Mapping from issue_id to set of blocked issue_ids
    """

    issues: dict[str, IssueInfo] = field(default_factory=dict)
    blocked_by: dict[str, set[str]] = field(default_factory=dict)
    blocks: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def from_issues(
        cls,
        issues: list[IssueInfo],
        completed_ids: set[str] | None = None,
    ) -> DependencyGraph:
        """Build graph from list of issues.

        Constructs a dependency graph where:
        - Each issue is a node
        - blocked_by relationships create edges from blockers to blocked issues
        - Completed issues are treated as satisfied (not blocking)
        - Missing issues are logged as warnings but don't block

        Args:
            issues: List of IssueInfo objects with blocked_by/blocks fields
            completed_ids: Set of completed issue IDs (treated as resolved)

        Returns:
            Constructed DependencyGraph

        Example:
            >>> issues = [issue_a, issue_b, issue_c]
            >>> completed = {"FEAT-001"}  # Already done
            >>> graph = DependencyGraph.from_issues(issues, completed)
        """
        completed = completed_ids or set()
        graph = cls()

        # Index all issues by ID
        for issue in issues:
            graph.issues[issue.issue_id] = issue
            graph.blocked_by[issue.issue_id] = set()
            graph.blocks[issue.issue_id] = set()

        # Build dependency edges
        all_issue_ids = set(graph.issues.keys())
        for issue in issues:
            for blocker_id in issue.blocked_by:
                # Skip completed blockers (already satisfied)
                if blocker_id in completed:
                    continue
                # Skip missing blockers with warning
                if blocker_id not in all_issue_ids:
                    logger.warning(f"Issue {issue.issue_id} blocked by unknown issue {blocker_id}")
                    continue
                # Add bidirectional edge
                graph.blocked_by[issue.issue_id].add(blocker_id)
                graph.blocks[blocker_id].add(issue.issue_id)

        return graph

    def get_ready_issues(self, completed: set[str] | None = None) -> list[IssueInfo]:
        """Return issues whose blockers are all completed.

        An issue is "ready" if:
        - It is not already completed
        - All its blockers are either completed or not in the graph

        Args:
            completed: Set of completed issue IDs

        Returns:
            List of IssueInfo for issues with no active blockers,
            sorted by priority (highest first) then issue_id
        """
        completed = completed or set()
        ready = []
        for issue_id, issue in self.issues.items():
            if issue_id in completed:
                continue
            blockers = self.get_blocking_issues(issue_id, completed)
            if not blockers:
                ready.append(issue)
        # Sort by priority then issue_id for consistent ordering
        ready.sort(key=lambda x: (x.priority_int, x.issue_id))
        return ready

    def get_execution_waves(self, completed: set[str] | None = None) -> list[list[IssueInfo]]:
        """Return issues grouped into parallel execution waves.

        Wave 1: All issues with no blockers (or blockers already completed)
        Wave 2: Issues whose blockers are all in wave 1
        Wave N: Issues whose blockers are all in waves 1..N-1

        This is similar to topological_sort but groups issues by "level"
        rather than returning a flat list.

        Args:
            completed: Set of already-completed issue IDs

        Returns:
            List of waves, each wave is a list of issues that can run in parallel.
            Empty list if graph is empty or all issues are completed.

        Raises:
            ValueError: If graph contains cycles (not a DAG)

        Example:
            If A blocks B and C, and B and C block D:
            - Wave 1: [A]
            - Wave 2: [B, C]
            - Wave 3: [D]
        """
        completed = completed or set()
        waves: list[list[IssueInfo]] = []
        processed: set[str] = set(completed)

        while True:
            # Get issues ready to run (all blockers in processed set)
            wave = self.get_ready_issues(completed=processed)
            if not wave:
                break
            waves.append(wave)
            # Mark this wave as processed for next iteration
            for issue in wave:
                processed.add(issue.issue_id)

        # Check for cycles - if we have unprocessed issues, there's a cycle
        remaining = set(self.issues.keys()) - processed
        if remaining:
            cycles = self.detect_cycles()
            cycle_str = ", ".join(" -> ".join(cycle) for cycle in cycles)
            raise ValueError(f"Dependency graph contains cycles: {cycle_str}")

        return waves

    def is_blocked(self, issue_id: str, completed: set[str] | None = None) -> bool:
        """Check if an issue is still blocked.

        Args:
            issue_id: Issue ID to check
            completed: Set of completed issue IDs

        Returns:
            True if issue has unresolved blockers, False otherwise
        """
        return bool(self.get_blocking_issues(issue_id, completed))

    def get_blocking_issues(self, issue_id: str, completed: set[str] | None = None) -> set[str]:
        """Return incomplete issues blocking this one.

        Args:
            issue_id: Issue ID to check
            completed: Set of completed issue IDs

        Returns:
            Set of issue IDs still blocking this issue
        """
        completed = completed or set()
        blockers = self.blocked_by.get(issue_id, set())
        return blockers - completed

    def get_blocked_by_issue(self, issue_id: str) -> set[str]:
        """Return issues that this issue blocks.

        Args:
            issue_id: Issue ID to check

        Returns:
            Set of issue IDs that are blocked by this issue
        """
        return self.blocks.get(issue_id, set()).copy()

    def topological_sort(self) -> list[IssueInfo]:
        """Return issues in dependency order (Kahn's algorithm).

        Issues with no dependencies come first, followed by issues
        whose dependencies have been satisfied. Within each "level",
        issues are sorted by priority then issue_id.

        Returns:
            List of IssueInfo in topological order

        Raises:
            ValueError: If graph contains cycles (not a DAG)

        Example:
            If A blocks B, and B blocks C, returns [A, B, C]
        """
        # Calculate in-degree for each node (number of blockers)
        in_degree: dict[str, int] = {
            issue_id: len(blockers) for issue_id, blockers in self.blocked_by.items()
        }

        # Start with nodes that have no blockers, sorted by priority
        zero_degree = [
            self.issues[issue_id] for issue_id, degree in in_degree.items() if degree == 0
        ]
        zero_degree.sort(key=lambda x: (x.priority_int, x.issue_id))
        queue: deque[str] = deque(issue.issue_id for issue in zero_degree)

        result: list[IssueInfo] = []
        while queue:
            issue_id = queue.popleft()
            result.append(self.issues[issue_id])

            # Reduce in-degree for nodes this one blocks
            # Collect newly ready nodes, then sort before adding to queue
            newly_ready: list[IssueInfo] = []
            for blocked_id in self.blocks.get(issue_id, set()):
                in_degree[blocked_id] -= 1
                if in_degree[blocked_id] == 0:
                    newly_ready.append(self.issues[blocked_id])

            # Sort newly ready by priority for consistent ordering
            newly_ready.sort(key=lambda x: (x.priority_int, x.issue_id))
            for issue in newly_ready:
                queue.append(issue.issue_id)

        # Check for cycles - if we didn't process all nodes, there's a cycle
        if len(result) != len(self.issues):
            cycles = self.detect_cycles()
            cycle_str = ", ".join(" -> ".join(cycle) for cycle in cycles)
            raise ValueError(f"Dependency graph contains cycles: {cycle_str}")

        return result

    def detect_cycles(self) -> list[list[str]]:
        """Detect and return any dependency cycles.

        Uses DFS with coloring to find back edges indicating cycles.
        A cycle exists when we encounter a node that is currently being
        visited (GRAY state) in the DFS traversal.

        Returns:
            List of cycles, each cycle is a list of issue IDs forming
            a path from the cycle start back to itself.
            Empty list if no cycles exist.

        Example:
            If A -> B -> C -> A (circular), returns [["A", "B", "C", "A"]]
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = dict.fromkeys(self.issues, WHITE)
        cycles: list[list[str]] = []
        path: list[str] = []

        def dfs(node: str) -> None:
            color[node] = GRAY
            path.append(node)

            # Traverse blockers (edges point from blocked to blocker)
            for neighbor in self.blocked_by.get(node, set()):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    # Found cycle - extract from path
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
                elif color[neighbor] == WHITE:
                    dfs(neighbor)

            path.pop()
            color[node] = BLACK

        for issue_id in self.issues:
            if color[issue_id] == WHITE:
                dfs(issue_id)

        return cycles

    def has_cycles(self) -> bool:
        """Check if the graph contains any cycles.

        Returns:
            True if cycles exist, False otherwise
        """
        return len(self.detect_cycles()) > 0

    def __len__(self) -> int:
        """Return number of issues in the graph."""
        return len(self.issues)

    def __contains__(self, issue_id: str) -> bool:
        """Check if an issue is in the graph."""
        return issue_id in self.issues


def refine_waves_for_contention(
    waves: list[list[IssueInfo]],
) -> tuple[list[list[IssueInfo]], list[WaveContentionNote | None]]:
    """Refine execution waves by splitting on file contention.

    For each wave with multiple issues, extracts file hints from issue
    content and checks for pairwise overlaps. Overlapping issues are
    split into sub-waves using greedy graph coloring so no two issues
    in the same sub-wave modify the same files.

    Args:
        waves: Execution waves from get_execution_waves()

    Returns:
        Tuple of (refined_waves, contention_notes).
        refined_waves: Wave list with contention-free sub-waves.
        contention_notes: Parallel list (same length as refined_waves).
            None for waves that weren't split, WaveContentionNote for sub-waves.
    """
    from little_loops.parallel.file_hints import FileHints, extract_file_hints

    refined: list[list[IssueInfo]] = []
    annotations: list[WaveContentionNote | None] = []

    for wave in waves:
        if len(wave) <= 1:
            refined.append(wave)
            annotations.append(None)
            continue

        # Extract file hints for each issue in the wave
        hints: dict[str, FileHints] = {}
        for issue in wave:
            content = issue.path.read_text() if issue.path.exists() else ""
            hints[issue.issue_id] = extract_file_hints(content, issue.issue_id)

        # Build conflict adjacency: issue_id -> set of conflicting issue_ids
        conflicts: dict[str, set[str]] = {issue.issue_id: set() for issue in wave}
        for i, a in enumerate(wave):
            for b in wave[i + 1 :]:
                if hints[a.issue_id].overlaps_with(hints[b.issue_id]):
                    conflicts[a.issue_id].add(b.issue_id)
                    conflicts[b.issue_id].add(a.issue_id)

        # If no conflicts, keep wave as-is
        if not any(conflicts.values()):
            refined.append(wave)
            annotations.append(None)
            continue

        # Collect all contended paths for display
        contended: set[str] = set()
        for i, a in enumerate(wave):
            for b in wave[i + 1 :]:
                contended.update(
                    hints[a.issue_id].get_overlapping_paths(hints[b.issue_id])
                )
        contended_paths = sorted(contended)

        # Greedy graph coloring — assign each issue the lowest color
        # not used by any conflicting neighbor
        color: dict[str, int] = {}
        for issue in wave:  # iterate in priority order (preserved from get_ready_issues)
            used_colors = {color[c] for c in conflicts[issue.issue_id] if c in color}
            c = 0
            while c in used_colors:
                c += 1
            color[issue.issue_id] = c

        # Group issues by color into sub-waves, preserving priority order
        max_color = max(color.values())
        total_sub_waves = max_color + 1
        for c in range(total_sub_waves):
            sub_wave = [issue for issue in wave if color[issue.issue_id] == c]
            if sub_wave:
                refined.append(sub_wave)
                annotations.append(
                    WaveContentionNote(
                        contended_paths=contended_paths,
                        sub_wave_index=c,
                        total_sub_waves=total_sub_waves,
                    )
                )

        logger.info(
            f"  Wave split into {total_sub_waves} sub-waves due to file contention"
        )

    return refined, annotations

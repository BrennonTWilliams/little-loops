"""Tests for little_loops.dependency_graph module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from little_loops.dependency_graph import DependencyGraph, refine_waves_for_contention
from little_loops.issue_parser import IssueInfo


def make_issue(
    issue_id: str,
    priority: str = "P1",
    blocked_by: list[str] | None = None,
    blocks: list[str] | None = None,
) -> IssueInfo:
    """Helper to create test IssueInfo objects."""
    return IssueInfo(
        path=Path(f"{issue_id.lower()}.md"),
        issue_type="features",
        priority=priority,
        issue_id=issue_id,
        title=f"Test {issue_id}",
        blocked_by=blocked_by or [],
        blocks=blocks or [],
    )


class TestDependencyGraphConstruction:
    """Tests for DependencyGraph.from_issues()."""

    def test_empty_graph(self) -> None:
        """Test constructing graph with no issues."""
        graph = DependencyGraph.from_issues([])

        assert len(graph) == 0
        assert graph.issues == {}
        assert graph.blocked_by == {}
        assert graph.blocks == {}

    def test_single_issue_no_deps(self) -> None:
        """Test graph with single issue having no dependencies."""
        issue = make_issue("FEAT-001")
        graph = DependencyGraph.from_issues([issue])

        assert len(graph) == 1
        assert "FEAT-001" in graph
        assert graph.blocked_by["FEAT-001"] == set()
        assert graph.blocks["FEAT-001"] == set()

    def test_linear_chain(self) -> None:
        """Test graph with linear dependency chain A -> B -> C."""
        issue_a = make_issue("FEAT-001", blocked_by=[], blocks=["FEAT-002"])
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"], blocks=["FEAT-003"])
        issue_c = make_issue("FEAT-003", blocked_by=["FEAT-002"], blocks=[])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        assert len(graph) == 3
        assert graph.blocked_by["FEAT-001"] == set()
        assert graph.blocked_by["FEAT-002"] == {"FEAT-001"}
        assert graph.blocked_by["FEAT-003"] == {"FEAT-002"}
        assert graph.blocks["FEAT-001"] == {"FEAT-002"}
        assert graph.blocks["FEAT-002"] == {"FEAT-003"}
        assert graph.blocks["FEAT-003"] == set()

    def test_multiple_blockers(self) -> None:
        """Test issue blocked by multiple others."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002")
        issue_c = make_issue("FEAT-003", blocked_by=["FEAT-001", "FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        assert graph.blocked_by["FEAT-003"] == {"FEAT-001", "FEAT-002"}
        assert graph.blocks["FEAT-001"] == {"FEAT-003"}
        assert graph.blocks["FEAT-002"] == {"FEAT-003"}

    def test_missing_blocker_logged_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that missing blockers are logged as warnings."""
        issue = make_issue("FEAT-001", blocked_by=["NONEXISTENT-999"])

        graph = DependencyGraph.from_issues([issue])

        assert "NONEXISTENT-999" not in graph.blocked_by["FEAT-001"]
        assert "blocked by unknown issue NONEXISTENT-999" in caplog.text

    def test_known_id_not_in_graph_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that a blocker in all_known_ids but not in graph produces no warning."""
        issue = make_issue("BUG-359", blocked_by=["ENH-342"])

        graph = DependencyGraph.from_issues([issue], all_known_ids={"BUG-359", "ENH-342"})

        # ENH-342 is not in the graph but exists on disk — no warning
        assert "ENH-342" not in graph.blocked_by["BUG-359"]
        assert "unknown issue" not in caplog.text

    def test_truly_unknown_id_still_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that a blocker not in all_known_ids still produces a warning."""
        issue = make_issue("BUG-001", blocked_by=["NONEXISTENT-999"])

        graph = DependencyGraph.from_issues([issue], all_known_ids={"BUG-001", "ENH-342"})

        assert "NONEXISTENT-999" not in graph.blocked_by["BUG-001"]
        assert "blocked by unknown issue NONEXISTENT-999" in caplog.text

    def test_all_known_ids_backward_compatible(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that omitting all_known_ids preserves original warning behavior."""
        issue = make_issue("FEAT-001", blocked_by=["NONEXISTENT-999"])

        DependencyGraph.from_issues([issue])

        assert "blocked by unknown issue NONEXISTENT-999" in caplog.text

    def test_completed_blocker_not_added(self) -> None:
        """Test that completed blockers are not added as edges."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001", "COMPLETED-999"])

        # FEAT-001 is in graph, COMPLETED-999 is in completed set
        graph = DependencyGraph.from_issues(
            [issue_a, issue_b],
            completed_ids={"COMPLETED-999"},
        )

        # FEAT-001 should still block FEAT-002, but COMPLETED-999 should not
        assert graph.blocked_by["FEAT-002"] == {"FEAT-001"}

    def test_completed_issue_in_graph(self) -> None:
        """Test with blocker that exists in issues but is also completed."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])

        # FEAT-001 exists in issues AND is marked completed
        graph = DependencyGraph.from_issues(
            [issue_a, issue_b],
            completed_ids={"FEAT-001"},
        )

        # FEAT-001 should not block FEAT-002 since it's completed
        assert graph.blocked_by["FEAT-002"] == set()


class TestGetReadyIssues:
    """Tests for get_ready_issues()."""

    def test_all_ready_no_deps(self) -> None:
        """Test all issues ready when none have dependencies."""
        issues = [
            make_issue("FEAT-001", priority="P0"),
            make_issue("FEAT-002", priority="P1"),
            make_issue("FEAT-003", priority="P2"),
        ]
        graph = DependencyGraph.from_issues(issues)

        ready = graph.get_ready_issues()

        assert len(ready) == 3
        # Should be sorted by priority
        assert [i.issue_id for i in ready] == ["FEAT-001", "FEAT-002", "FEAT-003"]

    def test_only_root_ready(self) -> None:
        """Test only root issues (no blockers) are ready initially."""
        issue_a = make_issue("FEAT-001", priority="P0")
        issue_b = make_issue("FEAT-002", priority="P0", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", priority="P0", blocked_by=["FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        ready = graph.get_ready_issues()

        assert len(ready) == 1
        assert ready[0].issue_id == "FEAT-001"

    def test_ready_after_completion(self) -> None:
        """Test issues become ready after blockers are completed."""
        issue_a = make_issue("FEAT-001", priority="P0")
        issue_b = make_issue("FEAT-002", priority="P1", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([issue_a, issue_b])

        # Initially only A is ready
        ready = graph.get_ready_issues()
        assert [i.issue_id for i in ready] == ["FEAT-001"]

        # After A completed, B is ready
        ready = graph.get_ready_issues(completed={"FEAT-001"})
        assert [i.issue_id for i in ready] == ["FEAT-002"]

    def test_completed_issues_excluded(self) -> None:
        """Test completed issues are not included in ready list."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002")

        graph = DependencyGraph.from_issues([issue_a, issue_b])

        ready = graph.get_ready_issues(completed={"FEAT-001"})

        assert len(ready) == 1
        assert ready[0].issue_id == "FEAT-002"

    def test_multiple_blockers_all_must_complete(self) -> None:
        """Test issue with multiple blockers needs all completed."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002")
        issue_c = make_issue("FEAT-003", blocked_by=["FEAT-001", "FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        # Only A completed - C still blocked
        ready = graph.get_ready_issues(completed={"FEAT-001"})
        assert "FEAT-003" not in [i.issue_id for i in ready]

        # Both A and B completed - C ready
        ready = graph.get_ready_issues(completed={"FEAT-001", "FEAT-002"})
        assert "FEAT-003" in [i.issue_id for i in ready]


class TestIsBlocked:
    """Tests for is_blocked()."""

    def test_not_blocked_no_deps(self) -> None:
        """Test issue with no dependencies is not blocked."""
        issue = make_issue("FEAT-001")
        graph = DependencyGraph.from_issues([issue])

        assert not graph.is_blocked("FEAT-001")

    def test_blocked_with_deps(self) -> None:
        """Test issue with active dependencies is blocked."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([issue_a, issue_b])

        assert not graph.is_blocked("FEAT-001")
        assert graph.is_blocked("FEAT-002")

    def test_not_blocked_after_completion(self) -> None:
        """Test issue becomes unblocked when blocker completes."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([issue_a, issue_b])

        assert graph.is_blocked("FEAT-002")
        assert not graph.is_blocked("FEAT-002", completed={"FEAT-001"})


class TestGetBlockingIssues:
    """Tests for get_blocking_issues()."""

    def test_no_blockers(self) -> None:
        """Test issue with no blockers returns empty set."""
        issue = make_issue("FEAT-001")
        graph = DependencyGraph.from_issues([issue])

        assert graph.get_blocking_issues("FEAT-001") == set()

    def test_active_blockers(self) -> None:
        """Test returns active blockers."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002")
        issue_c = make_issue("FEAT-003", blocked_by=["FEAT-001", "FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        blockers = graph.get_blocking_issues("FEAT-003")
        assert blockers == {"FEAT-001", "FEAT-002"}

    def test_completed_blockers_excluded(self) -> None:
        """Test completed blockers are excluded."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002")
        issue_c = make_issue("FEAT-003", blocked_by=["FEAT-001", "FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        blockers = graph.get_blocking_issues("FEAT-003", completed={"FEAT-001"})
        assert blockers == {"FEAT-002"}


class TestGetBlockedByIssue:
    """Tests for get_blocked_by_issue()."""

    def test_blocks_nothing(self) -> None:
        """Test issue that blocks nothing."""
        issue = make_issue("FEAT-001")
        graph = DependencyGraph.from_issues([issue])

        assert graph.get_blocked_by_issue("FEAT-001") == set()

    def test_blocks_multiple(self) -> None:
        """Test issue that blocks multiple others."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        blocked = graph.get_blocked_by_issue("FEAT-001")
        assert blocked == {"FEAT-002", "FEAT-003"}


class TestTopologicalSort:
    """Tests for topological_sort()."""

    def test_no_deps_sorted_by_priority(self) -> None:
        """Test issues with no deps sorted by priority."""
        issues = [
            make_issue("FEAT-003", priority="P2"),
            make_issue("FEAT-001", priority="P0"),
            make_issue("FEAT-002", priority="P1"),
        ]
        graph = DependencyGraph.from_issues(issues)

        sorted_issues = graph.topological_sort()

        assert [i.issue_id for i in sorted_issues] == ["FEAT-001", "FEAT-002", "FEAT-003"]

    def test_linear_chain_order(self) -> None:
        """Test linear chain maintains dependency order."""
        issue_a = make_issue("FEAT-001", priority="P2")  # Low priority but must come first
        issue_b = make_issue("FEAT-002", priority="P0", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", priority="P0", blocked_by=["FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        sorted_issues = graph.topological_sort()

        assert [i.issue_id for i in sorted_issues] == ["FEAT-001", "FEAT-002", "FEAT-003"]

    def test_diamond_dependency(self) -> None:
        """Test diamond pattern: A -> B,C -> D."""
        issue_a = make_issue("FEAT-001", priority="P0")
        issue_b = make_issue("FEAT-002", priority="P1", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", priority="P2", blocked_by=["FEAT-001"])
        issue_d = make_issue("FEAT-004", priority="P0", blocked_by=["FEAT-002", "FEAT-003"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c, issue_d])

        sorted_issues = graph.topological_sort()
        ids = [i.issue_id for i in sorted_issues]

        # A must come first, D must come last
        assert ids[0] == "FEAT-001"
        assert ids[-1] == "FEAT-004"
        # B and C must come before D
        assert ids.index("FEAT-002") < ids.index("FEAT-004")
        assert ids.index("FEAT-003") < ids.index("FEAT-004")

    def test_empty_graph(self) -> None:
        """Test topological sort of empty graph."""
        graph = DependencyGraph.from_issues([])

        assert graph.topological_sort() == []

    def test_cycle_raises_value_error(self) -> None:
        """Test cycle detection raises ValueError."""
        issue_a = make_issue("FEAT-001", blocked_by=["FEAT-002"])
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([issue_a, issue_b])

        with pytest.raises(ValueError, match="cycles"):
            graph.topological_sort()


class TestCycleDetection:
    """Tests for detect_cycles()."""

    def test_no_cycles(self) -> None:
        """Test graph with no cycles."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([issue_a, issue_b])

        cycles = graph.detect_cycles()
        assert cycles == []
        assert not graph.has_cycles()

    def test_simple_cycle(self) -> None:
        """Test detection of simple A <-> B cycle."""
        issue_a = make_issue("FEAT-001", blocked_by=["FEAT-002"])
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([issue_a, issue_b])

        cycles = graph.detect_cycles()
        assert len(cycles) > 0
        assert graph.has_cycles()

    def test_longer_cycle(self) -> None:
        """Test detection of A -> B -> C -> A cycle."""
        issue_a = make_issue("FEAT-001", blocked_by=["FEAT-003"])
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", blocked_by=["FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        cycles = graph.detect_cycles()
        assert len(cycles) > 0
        # Cycle should contain all three nodes
        cycle_nodes = set(cycles[0])
        assert "FEAT-001" in cycle_nodes
        assert "FEAT-002" in cycle_nodes
        assert "FEAT-003" in cycle_nodes

    def test_multiple_independent_subgraphs(self) -> None:
        """Test graph with multiple disconnected components."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003")  # Disconnected
        issue_d = make_issue("FEAT-004", blocked_by=["FEAT-003"])  # Disconnected

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c, issue_d])

        assert not graph.has_cycles()
        sorted_issues = graph.topological_sort()
        assert len(sorted_issues) == 4


class TestContains:
    """Tests for __contains__ method."""

    def test_contains_existing(self) -> None:
        """Test __contains__ for existing issue."""
        issue = make_issue("FEAT-001")
        graph = DependencyGraph.from_issues([issue])

        assert "FEAT-001" in graph

    def test_not_contains_missing(self) -> None:
        """Test __contains__ for missing issue."""
        issue = make_issue("FEAT-001")
        graph = DependencyGraph.from_issues([issue])

        assert "FEAT-999" not in graph


class TestLen:
    """Tests for __len__ method."""

    def test_len_empty(self) -> None:
        """Test len of empty graph."""
        graph = DependencyGraph.from_issues([])
        assert len(graph) == 0

    def test_len_with_issues(self) -> None:
        """Test len with multiple issues."""
        issues = [make_issue(f"FEAT-{i:03d}") for i in range(5)]
        graph = DependencyGraph.from_issues(issues)
        assert len(graph) == 5


class TestIntegration:
    """Integration tests with real-world scenarios."""

    def test_feature_branch_dependencies(self) -> None:
        """Test realistic feature branch dependency scenario."""
        # Authentication feature (foundation)
        auth = make_issue("FEAT-001", priority="P0")

        # User profile needs auth
        profile = make_issue("FEAT-002", priority="P1", blocked_by=["FEAT-001"])

        # Settings needs auth
        settings = make_issue("FEAT-003", priority="P1", blocked_by=["FEAT-001"])

        # Dashboard needs profile and settings
        dashboard = make_issue(
            "FEAT-004",
            priority="P2",
            blocked_by=["FEAT-002", "FEAT-003"],
        )

        # Bug fix (independent)
        bugfix = make_issue("BUG-001", priority="P0")

        graph = DependencyGraph.from_issues([auth, profile, settings, dashboard, bugfix])

        # Initially ready: auth (no blockers) and bugfix (independent)
        ready = graph.get_ready_issues()
        ready_ids = [i.issue_id for i in ready]
        assert "FEAT-001" in ready_ids
        assert "BUG-001" in ready_ids
        assert len(ready_ids) == 2

        # After auth completed
        ready = graph.get_ready_issues(completed={"FEAT-001"})
        ready_ids = [i.issue_id for i in ready]
        assert "FEAT-002" in ready_ids
        assert "FEAT-003" in ready_ids
        assert "FEAT-004" not in ready_ids  # Still blocked

        # After auth, profile, settings completed
        ready = graph.get_ready_issues(completed={"FEAT-001", "FEAT-002", "FEAT-003"})
        ready_ids = [i.issue_id for i in ready]
        assert "FEAT-004" in ready_ids

        # Topological sort should work
        sorted_issues = graph.topological_sort()
        ids = [i.issue_id for i in sorted_issues]

        # Auth must come before profile, settings
        assert ids.index("FEAT-001") < ids.index("FEAT-002")
        assert ids.index("FEAT-001") < ids.index("FEAT-003")

        # Profile and settings must come before dashboard
        assert ids.index("FEAT-002") < ids.index("FEAT-004")
        assert ids.index("FEAT-003") < ids.index("FEAT-004")


class TestGetExecutionWaves:
    """Tests for get_execution_waves()."""

    def test_single_wave_no_deps(self) -> None:
        """All issues in one wave when no dependencies."""
        issues = [
            make_issue("FEAT-001", priority="P0"),
            make_issue("FEAT-002", priority="P1"),
            make_issue("FEAT-003", priority="P2"),
        ]
        graph = DependencyGraph.from_issues(issues)

        waves = graph.get_execution_waves()

        assert len(waves) == 1
        assert len(waves[0]) == 3
        # Should be sorted by priority
        assert [i.issue_id for i in waves[0]] == ["FEAT-001", "FEAT-002", "FEAT-003"]

    def test_linear_chain_three_waves(self) -> None:
        """Linear chain A -> B -> C produces three waves."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", blocked_by=["FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        waves = graph.get_execution_waves()

        assert len(waves) == 3
        assert waves[0][0].issue_id == "FEAT-001"
        assert waves[1][0].issue_id == "FEAT-002"
        assert waves[2][0].issue_id == "FEAT-003"

    def test_diamond_three_waves(self) -> None:
        """Diamond pattern A -> B,C -> D produces three waves."""
        issue_a = make_issue("FEAT-001", priority="P0")
        issue_b = make_issue("FEAT-002", priority="P1", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", priority="P2", blocked_by=["FEAT-001"])
        issue_d = make_issue("FEAT-004", priority="P0", blocked_by=["FEAT-002", "FEAT-003"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c, issue_d])

        waves = graph.get_execution_waves()

        assert len(waves) == 3
        # Wave 1: A only
        assert [i.issue_id for i in waves[0]] == ["FEAT-001"]
        # Wave 2: B and C (sorted by priority)
        assert {i.issue_id for i in waves[1]} == {"FEAT-002", "FEAT-003"}
        # Wave 3: D only
        assert [i.issue_id for i in waves[2]] == ["FEAT-004"]

    def test_with_completed_issues(self) -> None:
        """Completed issues are skipped in wave generation."""
        issue_a = make_issue("FEAT-001")
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])
        issue_c = make_issue("FEAT-003", blocked_by=["FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])

        # FEAT-001 already completed
        waves = graph.get_execution_waves(completed={"FEAT-001"})

        assert len(waves) == 2
        assert waves[0][0].issue_id == "FEAT-002"
        assert waves[1][0].issue_id == "FEAT-003"

    def test_cycle_raises_value_error(self) -> None:
        """Cycles raise ValueError."""
        issue_a = make_issue("FEAT-001", blocked_by=["FEAT-002"])
        issue_b = make_issue("FEAT-002", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([issue_a, issue_b])

        with pytest.raises(ValueError, match="cycles"):
            graph.get_execution_waves()

    def test_empty_graph(self) -> None:
        """Empty graph returns empty waves."""
        graph = DependencyGraph.from_issues([])

        waves = graph.get_execution_waves()

        assert waves == []

    def test_independent_and_dependent_mixed(self) -> None:
        """Mix of independent and dependent issues."""
        # Independent
        bugfix = make_issue("BUG-001", priority="P0")
        # Dependent chain
        feat_a = make_issue("FEAT-001", priority="P1")
        feat_b = make_issue("FEAT-002", priority="P2", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([bugfix, feat_a, feat_b])

        waves = graph.get_execution_waves()

        assert len(waves) == 2
        # Wave 1: BUG-001 and FEAT-001 (sorted by priority)
        wave1_ids = [i.issue_id for i in waves[0]]
        assert "BUG-001" in wave1_ids
        assert "FEAT-001" in wave1_ids
        # Wave 2: FEAT-002
        assert waves[1][0].issue_id == "FEAT-002"

    def test_all_completed_returns_empty(self) -> None:
        """All issues completed returns empty waves."""
        issues = [
            make_issue("FEAT-001"),
            make_issue("FEAT-002"),
        ]
        graph = DependencyGraph.from_issues(issues)

        waves = graph.get_execution_waves(completed={"FEAT-001", "FEAT-002"})

        assert waves == []


def _make_issue_with_content(
    issue_id: str,
    content: str = "",
    priority: str = "P1",
    blocked_by: list[str] | None = None,
    blocks: list[str] | None = None,
) -> IssueInfo:
    """Helper to create IssueInfo with mock path returning given content."""
    mock_path = Mock(spec=Path)
    mock_path.exists.return_value = bool(content)
    mock_path.read_text.return_value = content
    return IssueInfo(
        path=mock_path,
        issue_type="features",
        priority=priority,
        issue_id=issue_id,
        title=f"Test {issue_id}",
        blocked_by=blocked_by or [],
        blocks=blocks or [],
    )


class TestRefineWavesForContention:
    """Tests for refine_waves_for_contention()."""

    def test_single_issue_wave_unchanged(self) -> None:
        """Single-issue waves pass through unchanged."""
        issue = _make_issue_with_content("FEAT-001", "modifies src/cli.py")
        waves: list[list[IssueInfo]] = [[issue]]

        result, notes = refine_waves_for_contention(waves)

        assert len(result) == 1
        assert result[0] == [issue]
        assert notes[0] is None

    def test_no_overlaps_unchanged(self) -> None:
        """Multi-issue wave with no file contention stays as one wave."""
        a = _make_issue_with_content("FEAT-001", "modifies src/cli.py")
        b = _make_issue_with_content("FEAT-002", "modifies src/sprint.py")
        waves: list[list[IssueInfo]] = [[a, b]]

        result, notes = refine_waves_for_contention(waves)

        assert len(result) == 1
        assert [i.issue_id for i in result[0]] == ["FEAT-001", "FEAT-002"]
        assert notes[0] is None

    def test_two_issues_same_file_split(self) -> None:
        """Two issues sharing a file split into 2 sub-waves."""
        a = _make_issue_with_content("FEAT-001", "modifies src/cli.py")
        b = _make_issue_with_content("FEAT-002", "modifies src/cli.py")
        waves: list[list[IssueInfo]] = [[a, b]]

        result, notes = refine_waves_for_contention(waves)

        assert len(result) == 2
        assert result[0][0].issue_id == "FEAT-001"
        assert result[1][0].issue_id == "FEAT-002"

    def test_three_issues_two_overlap_one_independent(self) -> None:
        """3 issues where A overlaps B but C is independent -> 2 sub-waves."""
        a = _make_issue_with_content("FEAT-001", "modifies src/page.tsx", priority="P0")
        b = _make_issue_with_content("FEAT-002", "modifies src/page.tsx", priority="P1")
        c = _make_issue_with_content("FEAT-003", "modifies src/api.py", priority="P2")
        waves: list[list[IssueInfo]] = [[a, b, c]]

        result, notes = refine_waves_for_contention(waves)

        assert len(result) == 2
        # Sub-wave 1: A and C (no overlap), sub-wave 2: B
        sub1_ids = {i.issue_id for i in result[0]}
        sub2_ids = {i.issue_id for i in result[1]}
        assert "FEAT-001" in sub1_ids
        assert "FEAT-003" in sub1_ids
        assert "FEAT-002" in sub2_ids

    def test_all_three_overlap_pairwise(self) -> None:
        """3 issues all overlapping each other -> 3 sub-waves."""
        a = _make_issue_with_content("FEAT-001", "modifies src/shared.py")
        b = _make_issue_with_content("FEAT-002", "modifies src/shared.py")
        c = _make_issue_with_content("FEAT-003", "modifies src/shared.py")
        waves: list[list[IssueInfo]] = [[a, b, c]]

        result, notes = refine_waves_for_contention(waves)

        assert len(result) == 3
        assert result[0][0].issue_id == "FEAT-001"
        assert result[1][0].issue_id == "FEAT-002"
        assert result[2][0].issue_id == "FEAT-003"

    def test_empty_hints_no_split(self) -> None:
        """Issues with no file hints (empty content) don't trigger splitting."""
        a = _make_issue_with_content("FEAT-001", "")
        b = _make_issue_with_content("FEAT-002", "")
        waves: list[list[IssueInfo]] = [[a, b]]

        result, notes = refine_waves_for_contention(waves)

        assert len(result) == 1
        assert len(result[0]) == 2
        assert notes[0] is None

    def test_mixed_waves_only_multi_refined(self) -> None:
        """Multiple waves: only multi-issue waves with overlaps get refined."""
        single = _make_issue_with_content("FEAT-001", "modifies src/a.py")
        multi_a = _make_issue_with_content("FEAT-002", "modifies src/b.py", priority="P0")
        multi_b = _make_issue_with_content("FEAT-003", "modifies src/b.py", priority="P1")
        no_overlap_a = _make_issue_with_content("FEAT-004", "modifies src/c.py", priority="P0")
        no_overlap_b = _make_issue_with_content("FEAT-005", "modifies src/d.py", priority="P1")
        waves: list[list[IssueInfo]] = [[single], [multi_a, multi_b], [no_overlap_a, no_overlap_b]]

        result, notes = refine_waves_for_contention(waves)

        # Wave 1: single issue passthrough
        assert len(result[0]) == 1
        assert result[0][0].issue_id == "FEAT-001"
        # Wave 2: split into 2 sub-waves
        assert result[1][0].issue_id == "FEAT-002"
        assert result[2][0].issue_id == "FEAT-003"
        # Wave 3: no overlap, stays as one wave
        assert len(result[3]) == 2
        assert {i.issue_id for i in result[3]} == {"FEAT-004", "FEAT-005"}

    def test_preserves_priority_order(self) -> None:
        """Issues within sub-waves maintain priority ordering."""
        a = _make_issue_with_content("FEAT-001", "modifies src/x.py", priority="P0")
        b = _make_issue_with_content("FEAT-002", "modifies src/shared.py", priority="P1")
        c = _make_issue_with_content("FEAT-003", "modifies src/y.py", priority="P2")
        # b overlaps with nobody (different files), a and c are independent
        waves: list[list[IssueInfo]] = [[a, b, c]]

        result, notes = refine_waves_for_contention(waves)

        # No overlaps -> single wave, order preserved
        assert len(result) == 1
        assert [i.issue_id for i in result[0]] == ["FEAT-001", "FEAT-002", "FEAT-003"]

    def test_empty_waves_input(self) -> None:
        """Empty input returns empty output."""
        result, notes = refine_waves_for_contention([])
        assert result == []
        assert notes == []

    def test_contention_notes_for_split_wave(self) -> None:
        """Split waves should have WaveContentionNote annotations."""
        a = _make_issue_with_content("FEAT-001", "modifies src/cli.py")
        b = _make_issue_with_content("FEAT-002", "modifies src/cli.py")
        waves: list[list[IssueInfo]] = [[a, b]]

        result, notes = refine_waves_for_contention(waves)

        assert len(notes) == 2
        assert notes[0] is not None
        assert notes[0].sub_wave_index == 0
        assert notes[0].total_sub_waves == 2
        assert notes[0].parent_wave_index == 0
        assert "src/cli.py" in notes[0].contended_paths
        assert notes[1] is not None
        assert notes[1].sub_wave_index == 1
        assert notes[1].total_sub_waves == 2
        assert notes[1].parent_wave_index == 0

    def test_contention_notes_mixed_waves(self) -> None:
        """Notes should be None for non-split waves and populated for split ones."""
        single = _make_issue_with_content("FEAT-001", "modifies src/a.py")
        overlap_a = _make_issue_with_content("FEAT-002", "modifies src/b.py", priority="P0")
        overlap_b = _make_issue_with_content("FEAT-003", "modifies src/b.py", priority="P1")
        waves: list[list[IssueInfo]] = [[single], [overlap_a, overlap_b]]

        result, notes = refine_waves_for_contention(waves)

        assert len(notes) == 3  # 1 passthrough + 2 sub-waves
        assert notes[0] is None  # single issue wave
        assert notes[1] is not None  # sub-wave 1
        assert notes[1].parent_wave_index == 1  # from original wave index 1
        assert notes[2] is not None  # sub-wave 2
        assert notes[2].parent_wave_index == 1
        assert "src/b.py" in notes[1].contended_paths

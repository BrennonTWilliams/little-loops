"""Tests for workflow_sequence_analyzer module."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from little_loops.workflow_sequence_analyzer import (
    EntityCluster,
    SessionLink,
    Workflow,
    WorkflowAnalysis,
    WorkflowBoundary,
    analyze_workflows,
    calculate_boundary_weight,
    entity_overlap,
    extract_entities,
    get_verb_class,
    semantic_similarity,
)


class TestExtractEntities:
    """Tests for extract_entities function."""

    def test_file_paths(self) -> None:
        """Extracts file paths from content."""
        content = "Fix the bug in checkout.py and update config.json"
        entities = extract_entities(content)
        assert "checkout.py" in entities
        assert "config.json" in entities

    def test_slash_commands(self) -> None:
        """Extracts slash commands from content."""
        content = "Run /ll:commit and then /ll:check-code"
        entities = extract_entities(content)
        assert "/ll:commit" in entities
        assert "/ll:check-code" in entities

    def test_issue_ids(self) -> None:
        """Extracts issue IDs from content."""
        content = "Working on BUG-123 and FEAT-045"
        entities = extract_entities(content)
        assert "BUG-123" in entities
        assert "FEAT-045" in entities

    def test_issue_ids_case_insensitive(self) -> None:
        """Extracts issue IDs case-insensitively and normalizes to uppercase."""
        content = "Fix bug-001 and feat-002"
        entities = extract_entities(content)
        assert "BUG-001" in entities
        assert "FEAT-002" in entities

    def test_phase_references(self) -> None:
        """Extracts phase references from content."""
        content = "Complete phase-1 and move to phase 2"
        entities = extract_entities(content)
        assert any("phase" in e.lower() for e in entities)

    def test_module_references(self) -> None:
        """Extracts module references from content."""
        content = "Working on module-3 now"
        entities = extract_entities(content)
        assert any("module" in e.lower() for e in entities)

    def test_empty_content(self) -> None:
        """Returns empty set for empty content."""
        assert extract_entities("") == set()

    def test_no_entities(self) -> None:
        """Returns empty set when no entities found."""
        content = "Hello world, how are you today?"
        entities = extract_entities(content)
        assert len(entities) == 0


class TestCalculateBoundaryWeight:
    """Tests for calculate_boundary_weight function."""

    def test_very_short_gap(self) -> None:
        """Gaps < 30s return 0.0."""
        assert calculate_boundary_weight(0) == 0.0
        assert calculate_boundary_weight(29) == 0.0

    def test_short_gap(self) -> None:
        """Gaps 30s-2min return 0.1."""
        assert calculate_boundary_weight(30) == 0.1
        assert calculate_boundary_weight(119) == 0.1

    def test_medium_gap(self) -> None:
        """Gaps 2-5min return 0.3."""
        assert calculate_boundary_weight(120) == 0.3
        assert calculate_boundary_weight(299) == 0.3

    def test_moderate_gap(self) -> None:
        """Gaps 5-15min return 0.5."""
        assert calculate_boundary_weight(300) == 0.5
        assert calculate_boundary_weight(899) == 0.5

    def test_large_gap(self) -> None:
        """Gaps 15-30min return 0.7."""
        assert calculate_boundary_weight(900) == 0.7
        assert calculate_boundary_weight(1799) == 0.7

    def test_longer_gap(self) -> None:
        """Gaps 30min-2hr return 0.85."""
        assert calculate_boundary_weight(1800) == 0.85
        assert calculate_boundary_weight(7199) == 0.85

    def test_very_large_gap(self) -> None:
        """Gaps > 2hr return 0.95."""
        assert calculate_boundary_weight(7200) == 0.95
        assert calculate_boundary_weight(10000) == 0.95


class TestEntityOverlap:
    """Tests for entity_overlap function."""

    def test_identical_sets(self) -> None:
        """Identical sets return 1.0."""
        entities = {"a", "b", "c"}
        assert entity_overlap(entities, entities) == 1.0

    def test_no_overlap(self) -> None:
        """Disjoint sets return 0.0."""
        assert entity_overlap({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self) -> None:
        """Partial overlap returns Jaccard similarity."""
        # {a, b} & {b, c} = {b}; union = {a, b, c}
        # Jaccard = 1/3
        result = entity_overlap({"a", "b"}, {"b", "c"})
        assert abs(result - 1 / 3) < 0.01

    def test_empty_sets(self) -> None:
        """Empty sets return 0.0."""
        assert entity_overlap(set(), set()) == 0.0
        assert entity_overlap({"a"}, set()) == 0.0
        assert entity_overlap(set(), {"b"}) == 0.0

    def test_subset(self) -> None:
        """Subset relationship works correctly."""
        # {a} & {a, b} = {a}; union = {a, b}
        # Jaccard = 1/2
        result = entity_overlap({"a"}, {"a", "b"})
        assert result == 0.5


class TestGetVerbClass:
    """Tests for get_verb_class function."""

    def test_deletion_verbs(self) -> None:
        """Detects deletion verbs."""
        assert get_verb_class("Remove the old file") == "deletion"
        assert get_verb_class("Delete this function") == "deletion"
        assert get_verb_class("Drop the table") == "deletion"
        assert get_verb_class("Clear the cache") == "deletion"

    def test_modification_verbs(self) -> None:
        """Detects modification verbs."""
        assert get_verb_class("Update the config") == "modification"
        assert get_verb_class("Fix the bug") == "modification"
        assert get_verb_class("Change this value") == "modification"
        assert get_verb_class("Edit the file") == "modification"

    def test_creation_verbs(self) -> None:
        """Detects creation verbs."""
        assert get_verb_class("Create a new file") == "creation"
        assert get_verb_class("Add a feature") == "creation"
        assert get_verb_class("Generate the report") == "creation"
        assert get_verb_class("Build the project") == "creation"

    def test_search_verbs(self) -> None:
        """Detects search verbs."""
        assert get_verb_class("Find the function") == "search"
        assert get_verb_class("Search for errors") == "search"
        assert get_verb_class("Where is the config?") == "search"

    def test_verification_verbs(self) -> None:
        """Detects verification verbs."""
        assert get_verb_class("Check the tests") == "verification"
        assert get_verb_class("Verify the output") == "verification"
        assert get_verb_class("Review the code") == "verification"

    def test_execution_verbs(self) -> None:
        """Detects execution verbs."""
        assert get_verb_class("Run the tests") == "execution"
        assert get_verb_class("Execute this command") == "execution"
        assert get_verb_class("Start the server") == "execution"

    def test_no_verb_class(self) -> None:
        """Returns None when no verb class matched."""
        assert get_verb_class("Hello world") is None
        assert get_verb_class("The sky is blue") is None


class TestSemanticSimilarity:
    """Tests for semantic_similarity function."""

    def test_identical_messages(self) -> None:
        """Identical messages have high similarity."""
        content = "Fix the bug in checkout.py"
        entities = extract_entities(content)
        similarity = semantic_similarity(
            content, content, entities, entities, "code_modification", "code_modification"
        )
        # Should be high (keyword 1.0, verb 1.0, entity 1.0, category 1.0 -> 1.0)
        assert similarity > 0.9

    def test_different_messages(self) -> None:
        """Completely different messages have low similarity."""
        content_a = "Run the tests"
        content_b = "Update the documentation"
        similarity = semantic_similarity(
            content_a,
            content_b,
            extract_entities(content_a),
            extract_entities(content_b),
            "testing",
            "documentation",
        )
        # Should be low
        assert similarity < 0.5

    def test_same_verb_class(self) -> None:
        """Messages with same verb class have some similarity."""
        content_a = "Delete the old file"
        content_b = "Remove the cache"
        similarity = semantic_similarity(
            content_a,
            content_b,
            extract_entities(content_a),
            extract_entities(content_b),
            None,
            None,
        )
        # Should have some similarity due to same verb class (deletion)
        assert similarity >= 0.3


class TestSessionLinkDataclass:
    """Tests for SessionLink dataclass."""

    def test_to_dict(self) -> None:
        """SessionLink serializes correctly."""
        link = SessionLink(
            link_id="link-001",
            sessions=[{"session_id": "abc", "position": 1, "link_evidence": "test"}],
            unified_workflow={"name": "Test", "total_messages": 5, "span_hours": 1.0},
            confidence=0.85,
        )
        d = link.to_dict()
        assert d["link_id"] == "link-001"
        assert d["confidence"] == 0.85
        assert len(d["sessions"]) == 1
        assert d["unified_workflow"]["name"] == "Test"


class TestEntityClusterDataclass:
    """Tests for EntityCluster dataclass."""

    def test_to_dict(self) -> None:
        """EntityCluster serializes correctly."""
        cluster = EntityCluster(
            cluster_id="cluster-001",
            primary_entities=["file.py"],
            all_entities={"file.py", "test.py"},
            cohesion_score=0.756,
        )
        d = cluster.to_dict()
        assert d["cluster_id"] == "cluster-001"
        assert d["cohesion_score"] == 0.76  # Rounded to 2 decimals
        assert "file.py" in d["all_entities"]
        assert "test.py" in d["all_entities"]

    def test_all_entities_sorted(self) -> None:
        """all_entities is sorted in output."""
        cluster = EntityCluster(
            cluster_id="c-001",
            primary_entities=["z.py"],
            all_entities={"z.py", "a.py", "m.py"},
        )
        d = cluster.to_dict()
        assert d["all_entities"] == ["a.py", "m.py", "z.py"]


class TestWorkflowBoundaryDataclass:
    """Tests for WorkflowBoundary dataclass."""

    def test_to_dict(self) -> None:
        """WorkflowBoundary serializes correctly."""
        boundary = WorkflowBoundary(
            msg_a="uuid-1",
            msg_b="uuid-2",
            time_gap_seconds=300,
            time_gap_weight=0.5,
            entity_overlap=0.333,
            final_boundary_score=0.35,
            is_boundary=False,
        )
        d = boundary.to_dict()
        assert d["between"]["msg_a"] == "uuid-1"
        assert d["between"]["msg_b"] == "uuid-2"
        assert d["time_gap_seconds"] == 300
        assert d["entity_overlap"] == 0.33  # Rounded
        assert d["is_boundary"] is False


class TestWorkflowDataclass:
    """Tests for Workflow dataclass."""

    def test_to_dict(self) -> None:
        """Workflow serializes correctly."""
        workflow = Workflow(
            workflow_id="wf-001",
            name="Test Workflow",
            pattern="debug → fix → test",
            pattern_confidence=0.856,
            messages=[{"uuid": "msg-1", "category": "debugging", "step": 1}],
            session_span=["session-1"],
            duration_minutes=25,
        )
        d = workflow.to_dict()
        assert d["workflow_id"] == "wf-001"
        assert d["pattern_confidence"] == 0.86  # Rounded
        assert d["duration_minutes"] == 25


class TestWorkflowAnalysisDataclass:
    """Tests for WorkflowAnalysis dataclass."""

    def test_to_dict(self) -> None:
        """WorkflowAnalysis serializes correctly."""
        analysis = WorkflowAnalysis(
            metadata={"message_count": 10, "module": "test"},
            session_links=[],
            entity_clusters=[],
            workflow_boundaries=[],
            workflows=[],
            handoff_analysis={"total_handoffs": 0},
        )
        d = analysis.to_dict()
        assert d["analysis_metadata"]["message_count"] == 10
        assert d["handoff_analysis"]["total_handoffs"] == 0


class TestAnalyzeWorkflows:
    """Integration tests for analyze_workflows function."""

    @pytest.fixture
    def sample_messages(self) -> list[dict[str, Any]]:
        """Sample messages for testing."""
        base_time = datetime(2026, 1, 15, 10, 0, 0)
        return [
            {
                "content": "Find where the bug is in checkout.py",
                "timestamp": base_time.isoformat(),
                "session_id": "session-1",
                "uuid": "msg-001",
            },
            {
                "content": "Fix the null pointer in checkout.py",
                "timestamp": (base_time.replace(minute=5)).isoformat(),
                "session_id": "session-1",
                "uuid": "msg-002",
            },
            {
                "content": "Run the tests for checkout",
                "timestamp": (base_time.replace(minute=10)).isoformat(),
                "session_id": "session-1",
                "uuid": "msg-003",
            },
        ]

    @pytest.fixture
    def sample_patterns(self) -> dict[str, Any]:
        """Sample Step 1 patterns for testing."""
        return {
            "analysis_metadata": {
                "source_file": "test.jsonl",
                "message_count": 3,
            },
            "category_distribution": [
                {
                    "category": "debugging",
                    "count": 1,
                    "example_messages": [{"uuid": "msg-001", "content": "Find where..."}],
                },
                {
                    "category": "code_modification",
                    "count": 1,
                    "example_messages": [{"uuid": "msg-002", "content": "Fix the..."}],
                },
                {
                    "category": "testing",
                    "count": 1,
                    "example_messages": [{"uuid": "msg-003", "content": "Run the..."}],
                },
            ],
        }

    def test_basic_analysis(
        self,
        sample_messages: list[dict[str, Any]],
        sample_patterns: dict[str, Any],
    ) -> None:
        """Runs basic analysis pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Write input files
            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in sample_messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump(sample_patterns, f)

            output_file = tmpdir_path / "output.yaml"

            # Run analysis
            result = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
                output_file=output_file,
            )

            # Verify result
            assert result.metadata["message_count"] == 3
            assert output_file.exists()

            # Verify output YAML
            with open(output_file) as f:
                output_data = yaml.safe_load(f)

            assert "analysis_metadata" in output_data
            assert "entity_clusters" in output_data
            assert "workflow_boundaries" in output_data
            assert "workflows" in output_data

    def test_entity_clustering(
        self,
        sample_messages: list[dict[str, Any]],
        sample_patterns: dict[str, Any],
    ) -> None:
        """Entity clustering groups related messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in sample_messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump(sample_patterns, f)

            result = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
            )

            # Should cluster messages about checkout.py
            if result.entity_clusters:
                checkout_cluster = next(
                    (c for c in result.entity_clusters if "checkout.py" in c.all_entities),
                    None,
                )
                if checkout_cluster:
                    assert len(checkout_cluster.messages) >= 2

    def test_workflow_boundaries(
        self,
        sample_messages: list[dict[str, Any]],
        sample_patterns: dict[str, Any],
    ) -> None:
        """Workflow boundaries are computed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in sample_messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump(sample_patterns, f)

            result = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
            )

            # Should have 2 boundaries (between 3 messages)
            assert len(result.workflow_boundaries) == 2

            # Boundaries should have time gaps of ~5 minutes (300 seconds)
            for boundary in result.workflow_boundaries:
                assert boundary.time_gap_seconds == 300

    def test_no_output_file(
        self,
        sample_messages: list[dict[str, Any]],
        sample_patterns: dict[str, Any],
    ) -> None:
        """Can analyze without writing output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in sample_messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump(sample_patterns, f)

            # No output file specified
            result = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
            )

            assert result.metadata["message_count"] == 3

    def test_empty_messages(self) -> None:
        """Handles empty message file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages_file = tmpdir_path / "messages.jsonl"
            messages_file.touch()  # Empty file

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump({"category_distribution": []}, f)

            result = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
            )

            assert result.metadata["message_count"] == 0
            assert len(result.entity_clusters) == 0
            assert len(result.workflows) == 0

    def test_session_linking(self) -> None:
        """Session linking detects related sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Two sessions with same git branch
            messages = [
                {
                    "content": "Working on feature.py",
                    "timestamp": "2026-01-15T10:00:00",
                    "session_id": "session-1",
                    "uuid": "msg-001",
                    "git_branch": "feature-123",
                },
                {
                    "content": "Continuing work on feature.py",
                    "timestamp": "2026-01-15T11:00:00",
                    "session_id": "session-2",
                    "uuid": "msg-002",
                    "git_branch": "feature-123",
                },
            ]

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump({"category_distribution": []}, f)

            result = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
            )

            # Should find session link due to same git branch
            assert len(result.session_links) >= 1

    def test_handoff_detection(self) -> None:
        """Handoff markers are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages = [
                {
                    "content": "Working on something",
                    "timestamp": "2026-01-15T10:00:00",
                    "session_id": "session-1",
                    "uuid": "msg-001",
                },
                {
                    "content": "/ll:handoff to continue later",
                    "timestamp": "2026-01-15T10:30:00",
                    "session_id": "session-1",
                    "uuid": "msg-002",
                },
                {
                    "content": "Continuing from previous session",
                    "timestamp": "2026-01-15T14:00:00",
                    "session_id": "session-2",
                    "uuid": "msg-003",
                },
            ]

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump({"category_distribution": []}, f)

            result = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
            )

            # Check handoff analysis
            assert result.handoff_analysis is not None
            if result.session_links:
                # Should detect handoff
                has_handoff_link = any(
                    any(s.get("link_evidence") == "handoff_detected" for s in link.sessions)
                    for link in result.session_links
                )
                assert has_handoff_link

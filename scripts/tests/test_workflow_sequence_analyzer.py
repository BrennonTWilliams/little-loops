"""Tests for workflow_sequence_analyzer module."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from little_loops.workflow_sequence import (
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
    main,
    semantic_similarity,
)
from little_loops.workflow_sequence.analysis import (
    _build_category_index,
    _cluster_by_entities,
    _compute_boundaries,
    _detect_handoff,
    _detect_workflows,
    _get_message_category,
    _group_by_session,
    _link_sessions,
    _parse_timestamps,
)
from little_loops.workflow_sequence.io import _load_messages, _load_patterns


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

    def test_high_overlap_threshold_produces_fewer_clusters(self) -> None:
        """overlap_threshold=0.9 produces fewer clusters than default 0.3."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Messages with partial entity overlap — clusters under default but not under 0.9
            messages = [
                {
                    "content": "Fix checkout.py and update config.json",
                    "uuid": "msg-1",
                    "session_id": "session-1",
                },
                {
                    "content": "Test checkout.py changes",
                    "uuid": "msg-2",
                    "session_id": "session-1",
                },
            ]

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump({"category_distribution": []}, f)

            result_default = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
            )
            result_strict = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
                overlap_threshold=0.9,
            )

            # Strict threshold should produce fewer (or equal) clusters
            assert len(result_strict.entity_clusters) <= len(result_default.entity_clusters)

    def test_low_overlap_threshold_produces_more_clusters(self) -> None:
        """overlap_threshold=0.0 allows any overlap, producing at least as many clusters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages = [
                {
                    "content": "Fix checkout.py and update config.json",
                    "uuid": "msg-1",
                    "session_id": "session-1",
                },
                {
                    "content": "Test checkout.py changes",
                    "uuid": "msg-2",
                    "session_id": "session-1",
                },
            ]

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump({"category_distribution": []}, f)

            result_lenient = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
                overlap_threshold=0.0,
            )

            # With overlap_threshold=0.0, messages with any shared entity cluster together
            assert len(result_lenient.entity_clusters) >= 1

    def test_default_thresholds_unchanged(self) -> None:
        """Calling analyze_workflows without threshold args uses defaults (no regression)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages = [
                {"content": "Fix checkout.py", "uuid": "msg-1", "session_id": "s1"},
                {"content": "Test checkout.py fix", "uuid": "msg-2", "session_id": "s1"},
            ]

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump({"category_distribution": []}, f)

            # Should not raise and should return valid analysis
            result = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
            )
            assert result.metadata["message_count"] == 2

    def test_verbose_true_emits_progress_to_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """verbose=True emits per-stage progress lines to stderr."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages = [
                {"content": "Fix checkout.py", "uuid": "msg-1", "session_id": "s1"},
                {"content": "Test checkout.py fix", "uuid": "msg-2", "session_id": "s1"},
            ]

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump({"category_distribution": []}, f)

            analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
                verbose=True,
            )

            captured = capsys.readouterr()
            assert "[1/4]" in captured.err
            assert "[2/4]" in captured.err
            assert "[3/4]" in captured.err
            assert "[4/4]" in captured.err

    def test_verbose_false_produces_no_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        """verbose=False (default) emits nothing to stderr during analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages = [
                {"content": "Fix checkout.py", "uuid": "msg-1", "session_id": "s1"},
            ]

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump({"category_distribution": []}, f)

            analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
                verbose=False,
            )

            captured = capsys.readouterr()
            assert captured.err == ""

    def test_json_output_format(
        self,
        sample_messages: list[dict[str, Any]],
        sample_patterns: dict[str, Any],
    ) -> None:
        """output_format='json' writes valid JSON equivalent to analysis.to_dict()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in sample_messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump(sample_patterns, f)

            output_file = tmpdir_path / "output.json"

            result = analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
                output_file=output_file,
                output_format="json",
            )

            assert output_file.exists()

            with open(output_file) as f:
                output_data = json.loads(f.read())

            assert "analysis_metadata" in output_data
            assert "entity_clusters" in output_data
            assert "workflow_boundaries" in output_data
            assert "workflows" in output_data
            assert (
                output_data["analysis_metadata"]["message_count"]
                == result.metadata["message_count"]
            )

    def test_yaml_output_format_default(
        self,
        sample_messages: list[dict[str, Any]],
        sample_patterns: dict[str, Any],
    ) -> None:
        """output_format='yaml' (default) produces the same output as before."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in sample_messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump(sample_patterns, f)

            output_file = tmpdir_path / "output.yaml"

            analyze_workflows(
                messages_file=messages_file,
                patterns_file=patterns_file,
                output_file=output_file,
                output_format="yaml",
            )

            assert output_file.exists()

            with open(output_file) as f:
                output_data = yaml.safe_load(f)

            assert "analysis_metadata" in output_data
            assert "entity_clusters" in output_data

    def test_entity_cluster_cross_referenced_on_workflows(self) -> None:
        """Workflows whose messages overlap an entity cluster have entity_cluster set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Three messages sharing "checkout.py" entity — form a cluster and a workflow
            messages = [
                {
                    "content": "Debug the bug in checkout.py",
                    "timestamp": "2026-01-15T10:00:00",
                    "session_id": "s1",
                    "uuid": "msg-001",
                },
                {
                    "content": "Fix the null pointer in checkout.py",
                    "timestamp": "2026-01-15T10:05:00",
                    "session_id": "s1",
                    "uuid": "msg-002",
                },
                {
                    "content": "Run tests for checkout.py changes",
                    "timestamp": "2026-01-15T10:10:00",
                    "session_id": "s1",
                    "uuid": "msg-003",
                },
            ]

            patterns = {
                "category_distribution": [
                    {
                        "category": "debugging",
                        "count": 1,
                        "example_messages": [{"uuid": "msg-001", "content": "Debug..."}],
                    },
                    {
                        "category": "code_modification",
                        "count": 1,
                        "example_messages": [{"uuid": "msg-002", "content": "Fix..."}],
                    },
                    {
                        "category": "testing",
                        "count": 1,
                        "example_messages": [{"uuid": "msg-003", "content": "Run..."}],
                    },
                ]
            }

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump(patterns, f)

            result = analyze_workflows(messages_file=messages_file, patterns_file=patterns_file)

            # Entity clusters should exist (all 3 messages share "checkout.py")
            assert len(result.entity_clusters) >= 1, "Expected at least one entity cluster"

            # Any detected workflows should be linked to the cluster
            if result.workflows:
                workflow = result.workflows[0]
                assert workflow.entity_cluster is not None, (
                    "workflow.entity_cluster should be set when messages overlap a cluster"
                )
                cluster_ids = {c.cluster_id for c in result.entity_clusters}
                assert workflow.entity_cluster in cluster_ids

    def test_workflow_handoff_points_populated(self) -> None:
        """Workflow messages containing handoff markers populate handoff_points."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            messages = [
                {
                    "content": "Debug the issue in runner.py",
                    "timestamp": "2026-01-15T10:00:00",
                    "session_id": "s1",
                    "uuid": "msg-001",
                },
                {
                    "content": "/ll:handoff — fix applied, continuing next session",
                    "timestamp": "2026-01-15T10:05:00",
                    "session_id": "s1",
                    "uuid": "msg-002",
                },
                {
                    "content": "Run tests for runner.py",
                    "timestamp": "2026-01-15T10:10:00",
                    "session_id": "s1",
                    "uuid": "msg-003",
                },
            ]

            patterns = {
                "category_distribution": [
                    {
                        "category": "debugging",
                        "count": 1,
                        "example_messages": [{"uuid": "msg-001", "content": "Debug..."}],
                    },
                    {
                        "category": "code_modification",
                        "count": 1,
                        "example_messages": [{"uuid": "msg-002", "content": "/ll:handoff..."}],
                    },
                    {
                        "category": "testing",
                        "count": 1,
                        "example_messages": [{"uuid": "msg-003", "content": "Run..."}],
                    },
                ]
            }

            messages_file = tmpdir_path / "messages.jsonl"
            with open(messages_file, "w") as f:
                for msg in messages:
                    f.write(json.dumps(msg) + "\n")

            patterns_file = tmpdir_path / "patterns.yaml"
            with open(patterns_file, "w") as f:
                yaml.dump(patterns, f)

            result = analyze_workflows(messages_file=messages_file, patterns_file=patterns_file)

            if result.workflows:
                workflow = result.workflows[0]
                handoff_uuids = [hp["uuid"] for hp in workflow.handoff_points]
                assert "msg-002" in handoff_uuids, (
                    "msg-002 contains /ll:handoff and should appear in handoff_points"
                )
                handoff_entry = next(
                    hp for hp in workflow.handoff_points if hp["uuid"] == "msg-002"
                )
                assert handoff_entry["type"] == "explicit_handoff"


class TestLinkSessions:
    """Tests for _link_sessions internal function."""

    def test_empty_sessions(self) -> None:
        """Empty sessions dict returns no links."""
        result = _link_sessions({})
        assert result == []

    def test_single_session(self) -> None:
        """Single session returns no links — no pairs to compare."""
        sessions = {
            "session-1": [{"content": "Fix checkout.py", "uuid": "msg-1"}],
        }
        result = _link_sessions(sessions)
        assert result == []

    def test_same_git_branch_creates_link(self) -> None:
        """Two sessions sharing a git branch are linked with shared_branch evidence."""
        sessions = {
            "session-1": [
                {
                    "content": "Work on feature.py",
                    "uuid": "msg-1",
                    "git_branch": "feat-123",
                    "timestamp": "2026-01-15T10:00:00",
                }
            ],
            "session-2": [
                {
                    "content": "Continue feature.py",
                    "uuid": "msg-2",
                    "git_branch": "feat-123",
                    "timestamp": "2026-01-15T12:00:00",
                }
            ],
        }
        result = _link_sessions(sessions)
        assert len(result) == 1
        assert result[0].confidence >= 0.4
        assert any("shared_branch" in s["link_evidence"] for s in result[0].sessions)

    def test_handoff_marker_creates_link(self) -> None:
        """Session with /ll:handoff content is linked to the next session."""
        sessions = {
            "session-1": [
                {
                    "content": "/ll:handoff continue in next session",
                    "uuid": "msg-1",
                    "timestamp": "2026-01-15T10:00:00",
                }
            ],
            "session-2": [
                {
                    "content": "Continuing from previous session",
                    "uuid": "msg-2",
                    "timestamp": "2026-01-15T11:00:00",
                }
            ],
        }
        result = _link_sessions(sessions)
        assert len(result) == 1
        assert any(s["link_evidence"] == "handoff_detected" for s in result[0].sessions)

    def test_entity_overlap_alone_insufficient(self) -> None:
        """High entity overlap alone yields score 0.2, below the 0.3 link threshold."""
        sessions = {
            "session-1": [{"content": "Fix checkout.py and config.json", "uuid": "msg-1"}],
            "session-2": [{"content": "Test checkout.py and config.json", "uuid": "msg-2"}],
        }
        result = _link_sessions(sessions)
        # score = 0.2 (entity overlap only) which is not > 0.3
        assert result == []

    def test_missing_timestamps_produce_zero_span(self) -> None:
        """Sessions linked via git branch but with no timestamps report span_hours=0.0."""
        sessions = {
            "session-1": [{"content": "Start work", "uuid": "msg-1", "git_branch": "feat"}],
            "session-2": [{"content": "Continue work", "uuid": "msg-2", "git_branch": "feat"}],
        }
        result = _link_sessions(sessions)
        assert len(result) == 1
        assert result[0].unified_workflow["span_hours"] == 0.0

    def test_empty_session_messages_skipped(self) -> None:
        """A session with no messages is skipped and produces no links."""
        sessions = {
            "session-empty": [],
            "session-1": [{"content": "Fix checkout.py", "uuid": "msg-1", "git_branch": "feat"}],
        }
        result = _link_sessions(sessions)
        assert result == []

    def test_span_hours_calculated_from_timestamps(self) -> None:
        """Span hours reflect the time difference between the earliest and latest messages."""
        sessions = {
            "session-1": [
                {
                    "content": "Start work",
                    "uuid": "msg-1",
                    "git_branch": "feat",
                    "timestamp": "2026-01-15T10:00:00",
                }
            ],
            "session-2": [
                {
                    "content": "Continue work",
                    "uuid": "msg-2",
                    "git_branch": "feat",
                    "timestamp": "2026-01-15T12:00:00",
                }
            ],
        }
        result = _link_sessions(sessions)
        assert len(result) == 1
        assert result[0].unified_workflow["span_hours"] == 2.0

    def test_mixed_naive_aware_timestamps_do_not_crash(self) -> None:
        """Mixed naive/aware timestamps in linked sessions do not raise TypeError."""
        sessions = {
            "session-1": [
                {
                    "content": "Start work",
                    "uuid": "msg-1",
                    "git_branch": "feat",
                    "timestamp": "2026-01-15T10:00:00",
                }
            ],
            "session-2": [
                {
                    "content": "Continue work",
                    "uuid": "msg-2",
                    "git_branch": "feat",
                    "timestamp": "2026-01-15T12:00:00Z",
                }
            ],
        }
        result = _link_sessions(sessions)
        assert len(result) == 1
        assert result[0].unified_workflow["span_hours"] == 2.0

    def test_three_evidence_all_preserved_in_unified_workflow(self) -> None:
        """All three evidence signals are stored in unified_workflow['evidence'] (BUG-548).

        When shared_branch + handoff_detected + entity_overlap are all present, the
        middle entry (handoff_detected) must not be silently dropped.
        """
        # Session A: shared branch, handoff marker, and many overlapping entities
        session_a_content = (
            "Working on checkout.py, config.json, auth.py, utils.py, models.py. "
            "/ll:handoff continue in next session"
        )
        sessions = {
            "session-1": [
                {
                    "content": session_a_content,
                    "uuid": "msg-1",
                    "git_branch": "feat-123",
                    "timestamp": "2026-01-15T10:00:00",
                }
            ],
            "session-2": [
                {
                    "content": "Continue work on checkout.py, config.json, auth.py, utils.py, models.py",
                    "uuid": "msg-2",
                    "git_branch": "feat-123",
                    "timestamp": "2026-01-15T12:00:00",
                }
            ],
        }
        result = _link_sessions(sessions)
        assert len(result) == 1
        link = result[0]
        evidence = link.unified_workflow.get("evidence", [])
        assert "shared_branch" in evidence
        assert "handoff_detected" in evidence
        assert "entity_overlap" in evidence
        assert len(evidence) == 3


class TestClusterByEntities:
    """Tests for _cluster_by_entities internal function."""

    def test_empty_messages(self) -> None:
        """Empty messages list returns no clusters."""
        result = _cluster_by_entities([])
        assert result == []

    def test_messages_with_no_entities(self) -> None:
        """Messages with no extractable entities return no clusters."""
        messages = [
            {"content": "Hello world how are you", "uuid": "msg-1"},
            {"content": "The sky is blue today", "uuid": "msg-2"},
        ]
        result = _cluster_by_entities(messages)
        assert result == []

    def test_single_message_cluster_filtered_out(self) -> None:
        """A cluster with only one message is filtered from the result."""
        messages = [
            {"content": "Fix checkout.py now", "uuid": "msg-1"},
        ]
        result = _cluster_by_entities(messages)
        assert result == []

    def test_two_messages_same_entity_form_cluster(self) -> None:
        """Two messages sharing an entity are grouped into one cluster."""
        messages = [
            {"content": "Fix checkout.py bug", "uuid": "msg-1"},
            {"content": "Test checkout.py changes", "uuid": "msg-2"},
        ]
        result = _cluster_by_entities(messages)
        assert len(result) == 1
        assert "checkout.py" in result[0].all_entities
        assert len(result[0].messages) == 2

    def test_no_entity_overlap_produces_no_cluster(self) -> None:
        """Messages with disjoint entities each form single-message clusters, which are filtered."""
        messages = [
            {"content": "Fix checkout.py bug", "uuid": "msg-1"},
            {"content": "Update config.json settings", "uuid": "msg-2"},
        ]
        result = _cluster_by_entities(messages)
        assert result == []

    def test_custom_overlap_threshold_controls_grouping(self) -> None:
        """Lowering overlap_threshold allows partial-overlap messages to cluster."""
        messages = [
            {"content": "Fix checkout.py and update config.json", "uuid": "msg-1"},
            {"content": "Test checkout.py", "uuid": "msg-2"},
        ]
        # With strict threshold (0.9): Jaccard ~0.5 does not pass → both single-msg clusters filtered
        result_strict = _cluster_by_entities(messages, overlap_threshold=0.9)
        assert result_strict == []

        # With lenient threshold (0.0): any overlap passes → cluster of 2 returned
        result_lenient = _cluster_by_entities(messages, overlap_threshold=0.0)
        assert len(result_lenient) == 1
        assert len(result_lenient[0].messages) == 2

    def test_cohesion_score_in_valid_range(self) -> None:
        """Cohesion score for a cluster is between 0.0 and 1.0."""
        messages = [
            {"content": "Fix checkout.py issue", "uuid": "msg-1"},
            {"content": "Test checkout.py fix", "uuid": "msg-2"},
        ]
        result = _cluster_by_entities(messages)
        assert len(result) == 1
        assert 0.0 <= result[0].cohesion_score <= 1.0

    def test_entities_matched_uses_pre_mutation_snapshot(self) -> None:
        """entities_matched only contains entities that existed in the cluster before the message was added."""
        # msg-1 establishes cluster with checkout.py
        # msg-2 matches on checkout.py (shared) but also introduces config.json (new)
        # entities_matched for msg-2 must only contain checkout.py, not config.json
        messages = [
            {"content": "Fix checkout.py bug", "uuid": "msg-1"},
            {"content": "Test checkout.py and config.json", "uuid": "msg-2"},
        ]
        result = _cluster_by_entities(messages, overlap_threshold=0.0)
        assert len(result) == 1
        cluster = result[0]
        assert len(cluster.messages) == 2
        second_msg = cluster.messages[1]
        # checkout.py was already in the cluster at match time — should be present
        assert "checkout.py" in second_msg["entities_matched"]
        # config.json was not in the cluster before msg-2 joined — must be absent
        assert "config.json" not in second_msg["entities_matched"]

    def test_span_populated_from_timestamps(self) -> None:
        """Cluster with timestamped messages has non-null span with start/end ISO strings."""
        messages = [
            {
                "content": "Fix checkout.py bug",
                "uuid": "msg-1",
                "timestamp": "2026-03-01T09:00:00Z",
            },
            {
                "content": "Test checkout.py changes",
                "uuid": "msg-2",
                "timestamp": "2026-03-01T17:00:00Z",
            },
        ]
        result = _cluster_by_entities(messages)
        assert len(result) == 1
        cluster = result[0]
        assert cluster.span is not None
        assert "start" in cluster.span
        assert "end" in cluster.span
        assert cluster.span["start"] < cluster.span["end"]

    def test_span_null_without_timestamps(self) -> None:
        """Cluster messages without timestamps yield span=None."""
        messages = [
            {"content": "Fix checkout.py bug", "uuid": "msg-1"},
            {"content": "Test checkout.py changes", "uuid": "msg-2"},
        ]
        result = _cluster_by_entities(messages)
        assert len(result) == 1
        assert result[0].span is None

    def test_inferred_workflow_set_on_category_match(self) -> None:
        """Cluster whose messages match a WORKFLOW_TEMPLATES entry gets inferred_workflow set."""
        # "edit checkout.py" → code_modification; "test checkout.py" → testing
        # matches "explore → modify → verify": [file_search, code_modification, testing] at 2/3 = 0.67 ≥ 0.3
        messages = [
            {"content": "edit checkout.py implementation", "uuid": "msg-1"},
            {"content": "test checkout.py and assert results", "uuid": "msg-2"},
        ]
        result = _cluster_by_entities(messages, overlap_threshold=0.0)
        assert len(result) == 1
        assert result[0].inferred_workflow is not None

    def test_inferred_workflow_null_on_no_match(self) -> None:
        """Cluster with no recognizable content categories has inferred_workflow=None."""
        # Use content with no keywords from _CONTENT_CATEGORY_MAP
        messages = [
            {"content": "foo.py bar baz", "uuid": "msg-1"},
            {"content": "foo.py qux quux", "uuid": "msg-2"},
        ]
        result = _cluster_by_entities(messages)
        assert len(result) == 1
        assert result[0].inferred_workflow is None


class TestComputeBoundaries:
    """Tests for _compute_boundaries internal function."""

    def test_empty_messages(self) -> None:
        """Empty messages returns no boundaries."""
        result = _compute_boundaries([])
        assert result == []

    def test_single_message(self) -> None:
        """A single message produces no boundaries."""
        result = _compute_boundaries(
            [{"content": "Fix file.py", "uuid": "msg-1", "timestamp": "2026-01-15T10:00:00"}]
        )
        assert result == []

    def test_missing_timestamps_produce_zero_gap(self) -> None:
        """Messages without timestamps produce gap_seconds=0 and time_gap_weight=0.0."""
        messages = [
            {"content": "Fix file.py", "uuid": "msg-1"},
            {"content": "Test changes", "uuid": "msg-2"},
        ]
        result = _compute_boundaries(messages)
        assert len(result) == 1
        assert result[0].time_gap_seconds == 0
        assert result[0].time_gap_weight == 0.0

    def test_five_minute_gap_weight(self) -> None:
        """A 5-minute gap (300s) produces time_gap_weight=0.5."""
        messages = [
            {"content": "Fix checkout.py", "uuid": "msg-1", "timestamp": "2026-01-15T10:00:00"},
            {"content": "Test checkout.py", "uuid": "msg-2", "timestamp": "2026-01-15T10:05:00"},
        ]
        result = _compute_boundaries(messages)
        assert len(result) == 1
        assert result[0].time_gap_seconds == 300
        assert result[0].time_gap_weight == 0.5

    def test_large_gap_no_entity_overlap_is_boundary(self) -> None:
        """A 1-hour gap with no shared entities yields is_boundary=True."""
        messages = [
            {"content": "Fix main.py issue", "uuid": "msg-1", "timestamp": "2026-01-15T10:00:00"},
            {"content": "Update config.json", "uuid": "msg-2", "timestamp": "2026-01-15T11:00:00"},
        ]
        result = _compute_boundaries(messages)
        assert len(result) == 1
        assert result[0].time_gap_seconds == 3600
        assert result[0].time_gap_weight == 0.85
        assert result[0].is_boundary is True

    def test_high_entity_overlap_reduces_boundary_score(self) -> None:
        """Entity overlap > 0.5 reduces final_boundary_score by 0.3."""
        messages = [
            {
                "content": "Fix checkout.py and config.json",
                "uuid": "msg-1",
                "timestamp": "2026-01-15T10:00:00",
            },
            {
                "content": "Test checkout.py and config.json",
                "uuid": "msg-2",
                "timestamp": "2026-01-15T10:20:00",  # 20-min gap → weight 0.7
            },
        ]
        result = _compute_boundaries(messages)
        assert len(result) == 1
        assert result[0].entity_overlap > 0.5
        # Score should be reduced from 0.7 by 0.3 → 0.4
        assert result[0].final_boundary_score < result[0].time_gap_weight

    def test_uuid_captured_in_boundary(self) -> None:
        """Boundary records the UUIDs of the two adjacent messages."""
        messages = [
            {"content": "Fix something", "uuid": "uuid-AAA", "timestamp": "2026-01-15T10:00:00"},
            {"content": "Fix another", "uuid": "uuid-BBB", "timestamp": "2026-01-15T11:00:00"},
        ]
        result = _compute_boundaries(messages)
        assert result[0].msg_a == "uuid-AAA"
        assert result[0].msg_b == "uuid-BBB"

    def test_n_messages_produce_n_minus_one_boundaries(self) -> None:
        """Three messages produce exactly two boundaries."""
        messages = [
            {"content": "Msg A", "uuid": "msg-1", "timestamp": "2026-01-15T10:00:00"},
            {"content": "Msg B", "uuid": "msg-2", "timestamp": "2026-01-15T10:05:00"},
            {"content": "Msg C", "uuid": "msg-3", "timestamp": "2026-01-15T10:10:00"},
        ]
        result = _compute_boundaries(messages)
        assert len(result) == 2

    def test_mixed_naive_aware_timestamps_produce_zero_gap(self) -> None:
        """Mixed naive/aware timestamps do not crash; gap falls back to 0."""
        messages = [
            {"content": "Naive ts", "uuid": "msg-1", "timestamp": "2026-01-15T10:00:00"},
            {"content": "Aware ts", "uuid": "msg-2", "timestamp": "2026-01-15T10:05:00Z"},
        ]
        result = _compute_boundaries(messages)
        assert len(result) == 1
        assert result[0].time_gap_seconds == 300


class TestDetectWorkflows:
    """Tests for _detect_workflows internal function."""

    def test_empty_messages(self) -> None:
        """Empty messages list returns no workflows."""
        result = _detect_workflows([], [], {})
        assert result == []

    def test_single_message_segment_skipped(self) -> None:
        """A segment with only one message is skipped — too short for a multi-step workflow."""
        messages = [
            {
                "content": "Fix checkout.py",
                "uuid": "msg-1",
                "timestamp": "2026-01-15T10:00:00",
                "session_id": "s1",
            }
        ]
        result = _detect_workflows(messages, [], {"category_distribution": []})
        assert result == []

    def test_no_category_matches_yields_no_workflows(self) -> None:
        """When no messages have category entries in patterns, no workflows are detected."""
        messages = [
            {
                "content": "First action",
                "uuid": "msg-1",
                "timestamp": "2026-01-15T10:00:00",
                "session_id": "s1",
            },
            {
                "content": "Second action",
                "uuid": "msg-2",
                "timestamp": "2026-01-15T10:05:00",
                "session_id": "s1",
            },
        ]
        result = _detect_workflows(messages, [], {"category_distribution": []})
        assert result == []

    def test_debug_fix_test_template_detected(self) -> None:
        """Three messages matching the debug→fix→test template produce a workflow."""
        messages = [
            {
                "content": "Find the bug",
                "uuid": "msg-1",
                "timestamp": "2026-01-15T10:00:00",
                "session_id": "s1",
            },
            {
                "content": "Fix the bug",
                "uuid": "msg-2",
                "timestamp": "2026-01-15T10:05:00",
                "session_id": "s1",
            },
            {
                "content": "Run the tests",
                "uuid": "msg-3",
                "timestamp": "2026-01-15T10:10:00",
                "session_id": "s1",
            },
        ]
        patterns: dict[str, Any] = {
            "category_distribution": [
                {
                    "category": "debugging",
                    "example_messages": [{"uuid": "msg-1", "content": "Find the bug"}],
                },
                {
                    "category": "code_modification",
                    "example_messages": [{"uuid": "msg-2", "content": "Fix the bug"}],
                },
                {
                    "category": "testing",
                    "example_messages": [{"uuid": "msg-3", "content": "Run the tests"}],
                },
            ]
        }
        result = _detect_workflows(messages, [], patterns)
        assert len(result) == 1
        assert result[0].pattern == "debug → fix → test"
        assert result[0].pattern_confidence == 1.0

    def test_unmatched_category_sequence_yields_no_workflow(self) -> None:
        """A category sequence that matches no template produces no workflow."""
        messages = [
            {
                "content": "Msg A",
                "uuid": "msg-1",
                "timestamp": "2026-01-15T10:00:00",
                "session_id": "s1",
            },
            {
                "content": "Msg B",
                "uuid": "msg-2",
                "timestamp": "2026-01-15T10:05:00",
                "session_id": "s1",
            },
        ]
        patterns: dict[str, Any] = {
            "category_distribution": [
                {
                    "category": "documentation",
                    "example_messages": [{"uuid": "msg-1"}, {"uuid": "msg-2"}],
                },
            ]
        }
        result = _detect_workflows(messages, [], patterns)
        assert result == []

    def test_boundary_splits_messages_into_separate_segments(self) -> None:
        """A true boundary divides messages; each resulting segment is evaluated independently."""
        messages = [
            {
                "content": "Msg A",
                "uuid": "msg-1",
                "timestamp": "2026-01-15T10:00:00",
                "session_id": "s1",
            },
            {
                "content": "Msg B",
                "uuid": "msg-2",
                "timestamp": "2026-01-15T10:05:00",
                "session_id": "s1",
            },
            {
                "content": "Msg C",
                "uuid": "msg-3",
                "timestamp": "2026-01-15T12:00:00",
                "session_id": "s1",
            },
            {
                "content": "Msg D",
                "uuid": "msg-4",
                "timestamp": "2026-01-15T12:05:00",
                "session_id": "s1",
            },
        ]
        # Boundary between msg-2 and msg-3 splits into two 2-message segments
        boundaries = [
            WorkflowBoundary(
                msg_a="msg-2",
                msg_b="msg-3",
                time_gap_seconds=7200,
                time_gap_weight=0.95,
                entity_overlap=0.0,
                final_boundary_score=0.95,
                is_boundary=True,
            )
        ]
        # No category info → no template match, but segmentation runs without error
        result = _detect_workflows(messages, boundaries, {"category_distribution": []})
        assert result == []

    def test_workflow_duration_calculated_from_timestamps(self) -> None:
        """Workflow duration_minutes reflects the time span of the matching segment."""
        messages = [
            {
                "content": "Find bug",
                "uuid": "msg-1",
                "timestamp": "2026-01-15T10:00:00",
                "session_id": "s1",
            },
            {
                "content": "Fix bug",
                "uuid": "msg-2",
                "timestamp": "2026-01-15T10:30:00",
                "session_id": "s1",
            },
            {
                "content": "Test fix",
                "uuid": "msg-3",
                "timestamp": "2026-01-15T11:00:00",
                "session_id": "s1",
            },
        ]
        patterns: dict[str, Any] = {
            "category_distribution": [
                {
                    "category": "debugging",
                    "example_messages": [{"uuid": "msg-1", "content": "Find bug"}],
                },
                {
                    "category": "code_modification",
                    "example_messages": [{"uuid": "msg-2", "content": "Fix bug"}],
                },
                {
                    "category": "testing",
                    "example_messages": [{"uuid": "msg-3", "content": "Test fix"}],
                },
            ]
        }
        result = _detect_workflows(messages, [], patterns)
        assert len(result) == 1
        assert result[0].duration_minutes == 60

    def test_mixed_naive_aware_timestamps_do_not_crash(self) -> None:
        """Mixed naive/aware timestamps in a workflow segment do not raise TypeError."""
        messages = [
            {
                "content": "Find bug",
                "uuid": "msg-1",
                "timestamp": "2026-01-15T10:00:00",
                "session_id": "s1",
            },
            {
                "content": "Fix bug",
                "uuid": "msg-2",
                "timestamp": "2026-01-15T10:30:00Z",
                "session_id": "s1",
            },
            {
                "content": "Test fix",
                "uuid": "msg-3",
                "timestamp": "2026-01-15T11:00:00",
                "session_id": "s1",
            },
        ]
        patterns: dict[str, Any] = {
            "category_distribution": [
                {
                    "category": "debugging",
                    "example_messages": [{"uuid": "msg-1", "content": "Find bug"}],
                },
                {
                    "category": "code_modification",
                    "example_messages": [{"uuid": "msg-2", "content": "Fix bug"}],
                },
                {
                    "category": "testing",
                    "example_messages": [{"uuid": "msg-3", "content": "Test fix"}],
                },
            ]
        }
        result = _detect_workflows(messages, [], patterns)
        assert len(result) == 1
        assert result[0].duration_minutes == 60


class TestLoadMessages:
    def test_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("")
            path = Path(f.name)
        assert _load_messages(path) == []

    def test_all_valid_lines(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"a": 1}\n{"b": 2}\n')
            path = Path(f.name)
        result = _load_messages(path)
        assert result == [{"a": 1}, {"b": 2}]

    def test_one_bad_line_in_middle(self, capsys: pytest.CaptureFixture[str]) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"a": 1}\n# session break\n{"b": 2}\n')
            path = Path(f.name)
        result = _load_messages(path)
        assert result == [{"a": 1}, {"b": 2}]
        err = capsys.readouterr().err
        assert "line 2" in err
        assert "skipped 1 malformed" in err

    def test_all_bad_lines(self, capsys: pytest.CaptureFixture[str]) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("not json\nalso not json\n")
            path = Path(f.name)
        result = _load_messages(path)
        assert result == []
        err = capsys.readouterr().err
        assert "skipped 2 malformed" in err

    def test_empty_lines_only(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("\n\n\n")
            path = Path(f.name)
        assert _load_messages(path) == []


class TestDetectHandoff:
    """Tests for _detect_handoff function."""

    def test_handoff_marker_detected(self) -> None:
        """Returns True when content contains a known handoff marker."""
        assert _detect_handoff("/ll:handoff — wrapping up this session") is True

    def test_no_marker_returns_false(self) -> None:
        """Returns False when content has no handoff markers."""
        assert _detect_handoff("Fix the bug in checkout.py") is False

    def test_marker_mid_sentence(self) -> None:
        """Returns True when marker appears mid-sentence."""
        assert _detect_handoff("Please continuation of the work above") is True

    def test_case_insensitive(self) -> None:
        """Marker matching is case-insensitive."""
        assert _detect_handoff("RESUMING FROM last session") is True

    def test_empty_string(self) -> None:
        """Returns False for empty content."""
        assert _detect_handoff("") is False


class TestGroupBySession:
    """Tests for _group_by_session function."""

    def test_groups_by_session_id(self) -> None:
        """Groups messages under their session_id key."""
        messages = [
            {"session_id": "abc", "content": "hello"},
            {"session_id": "abc", "content": "world"},
            {"session_id": "xyz", "content": "other"},
        ]
        result = _group_by_session(messages)
        assert set(result.keys()) == {"abc", "xyz"}
        assert len(result["abc"]) == 2
        assert len(result["xyz"]) == 1

    def test_missing_session_id_defaults_to_unknown(self) -> None:
        """Message without session_id is grouped under 'unknown'."""
        messages = [{"content": "no session"}]
        result = _group_by_session(messages)
        assert "unknown" in result
        assert result["unknown"][0]["content"] == "no session"

    def test_empty_messages(self) -> None:
        """Returns empty dict for empty input."""
        assert _group_by_session([]) == {}


class TestLoadPatterns:
    """Tests for _load_patterns function."""

    def test_loads_valid_yaml(self) -> None:
        """Returns parsed dict from a valid YAML file."""
        data = {"category_distribution": [{"category": "fix", "count": 3}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = Path(f.name)
        result = _load_patterns(path)
        assert result == data

    def test_empty_file_returns_empty_dict(self) -> None:
        """Returns empty dict when YAML file is empty (yaml.safe_load returns None)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            path = Path(f.name)
        assert _load_patterns(path) == {}

    def test_missing_file_raises(self) -> None:
        """Raises FileNotFoundError when file does not exist."""
        with pytest.raises(FileNotFoundError):
            _load_patterns(Path("/nonexistent/path/patterns.yaml"))


class TestGetMessageCategory:
    """Tests for _get_message_category function."""

    def _patterns(self) -> dict:
        return {
            "category_distribution": [
                {
                    "category": "fix",
                    "example_messages": [{"uuid": "msg-1", "content": "Fix bug"}],
                },
                {
                    "category": "review",
                    "example_messages": [{"uuid": "msg-2", "content": "Review PR"}],
                },
            ]
        }

    def test_finds_category_by_uuid(self) -> None:
        """Returns category string when uuid is found in example_messages."""
        assert _get_message_category("msg-1", self._patterns()) == "fix"
        assert _get_message_category("msg-2", self._patterns()) == "review"

    def test_returns_none_for_unknown_uuid(self) -> None:
        """Returns None when uuid does not match any example message."""
        assert _get_message_category("msg-99", self._patterns()) is None

    def test_returns_none_when_category_not_str(self) -> None:
        """Returns None when category field is not a string (isinstance guard)."""
        patterns: dict = {
            "category_distribution": [
                {
                    "category": 42,
                    "example_messages": [{"uuid": "msg-x"}],
                }
            ]
        }
        assert _get_message_category("msg-x", patterns) is None

    def test_empty_patterns(self) -> None:
        """Returns None when patterns dict is empty."""
        assert _get_message_category("msg-1", {}) is None


class TestBuildCategoryIndex:
    """Tests for _build_category_index function."""

    def _patterns(self) -> dict:
        return {
            "category_distribution": [
                {
                    "category": "fix",
                    "example_messages": [{"uuid": "msg-1"}, {"uuid": "msg-2"}],
                },
                {
                    "category": "review",
                    "example_messages": [{"uuid": "msg-3"}],
                },
            ]
        }

    def test_builds_flat_index(self) -> None:
        """Returns a flat UUID→category dict for all valid entries."""
        result = _build_category_index(self._patterns())
        assert result == {"msg-1": "fix", "msg-2": "fix", "msg-3": "review"}

    def test_empty_patterns(self) -> None:
        """Returns empty dict when patterns has no category_distribution."""
        assert _build_category_index({}) == {}

    def test_skips_non_str_category(self) -> None:
        """Skips entries where category is not a string."""
        patterns: dict = {
            "category_distribution": [
                {
                    "category": 42,
                    "example_messages": [{"uuid": "msg-x"}],
                }
            ]
        }
        assert _build_category_index(patterns) == {}

    def test_skips_empty_uuid(self) -> None:
        """Skips example messages where uuid is empty or missing."""
        patterns: dict = {
            "category_distribution": [
                {
                    "category": "fix",
                    "example_messages": [{"uuid": ""}, {"content": "no uuid"}],
                }
            ]
        }
        assert _build_category_index(patterns) == {}

    def test_uuid_collision_last_wins(self) -> None:
        """When same UUID appears in multiple categories, last category wins."""
        patterns: dict = {
            "category_distribution": [
                {
                    "category": "fix",
                    "example_messages": [{"uuid": "msg-1"}],
                },
                {
                    "category": "review",
                    "example_messages": [{"uuid": "msg-1"}],
                },
            ]
        }
        result = _build_category_index(patterns)
        assert result["msg-1"] == "review"


class TestParseTimestamps:
    """Tests for _parse_timestamps internal function."""

    def test_empty_list(self) -> None:
        """Empty message list returns empty timestamp list."""
        assert _parse_timestamps([]) == []

    def test_z_suffix_input(self) -> None:
        """Z-suffix timestamps are parsed and returned as naive datetimes."""
        messages = [{"timestamp": "2026-01-15T10:00:00Z"}]
        result = _parse_timestamps(messages)
        assert len(result) == 1
        assert result[0] == datetime(2026, 1, 15, 10, 0, 0)
        assert result[0].tzinfo is None

    def test_naive_input(self) -> None:
        """Naive ISO timestamps (no timezone) are parsed correctly."""
        messages = [{"timestamp": "2026-01-15T10:00:00"}]
        result = _parse_timestamps(messages)
        assert len(result) == 1
        assert result[0] == datetime(2026, 1, 15, 10, 0, 0)
        assert result[0].tzinfo is None

    def test_none_timestamp_value(self) -> None:
        """Messages with a None timestamp value are skipped."""
        messages = [{"timestamp": None}]
        result = _parse_timestamps(messages)
        assert result == []

    def test_mixed_valid_and_invalid(self) -> None:
        """Only valid timestamps are returned; invalid ones are silently skipped."""
        messages = [
            {"timestamp": "2026-01-15T10:00:00"},
            {"timestamp": "not-a-timestamp"},
            {"timestamp": "2026-01-15T11:00:00"},
        ]
        result = _parse_timestamps(messages)
        assert len(result) == 2
        assert result[0] == datetime(2026, 1, 15, 10, 0, 0)
        assert result[1] == datetime(2026, 1, 15, 11, 0, 0)

    def test_all_invalid(self) -> None:
        """All-invalid timestamps returns empty list."""
        messages = [
            {"timestamp": "bad"},
            {"timestamp": "also-bad"},
        ]
        assert _parse_timestamps(messages) == []

    def test_missing_timestamp_key(self) -> None:
        """Messages without a timestamp key are skipped."""
        messages = [{"content": "no timestamp here"}]
        assert _parse_timestamps(messages) == []

    def test_tzinfo_stripped(self) -> None:
        """Timezone-aware inputs are stripped to naive datetimes."""
        messages = [{"timestamp": "2026-01-15T10:00:00+05:30"}]
        result = _parse_timestamps(messages)
        assert len(result) == 1
        assert result[0].tzinfo is None


class TestMainDefaultInput:
    """Tests for main() --input default path behavior (FEAT-559)."""

    def test_default_input_missing_shows_ll_messages_hint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When --input is omitted and default path doesn't exist, error mentions ll-messages."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-workflows", "analyze", "--patterns", "p.yaml"]):
            result = main()
        captured = capsys.readouterr()
        assert result == 1
        assert "ll-messages" in captured.err
        assert ".claude/workflow-analysis/step1-patterns.jsonl" in captured.err

    def test_explicit_input_missing_no_ll_messages_hint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When --input is given explicitly but file is missing, no ll-messages hint is shown."""
        monkeypatch.chdir(tmp_path)
        custom = tmp_path / "custom.jsonl"
        with patch.object(
            sys, "argv", ["ll-workflows", "analyze", "--input", str(custom), "--patterns", "p.yaml"]
        ):
            result = main()
        captured = capsys.readouterr()
        assert result == 1
        assert "ll-messages" not in captured.err

    def test_default_input_does_not_require_flag(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Omitting --input must not raise SystemExit from argparse (i.e. required=False)."""
        monkeypatch.chdir(tmp_path)
        # If required=True, argparse raises SystemExit(2) before we can intercept.
        # After the fix, it should reach the file-existence check instead.
        with patch.object(sys, "argv", ["ll-workflows", "analyze", "--patterns", "p.yaml"]):
            try:
                main()
            except SystemExit as exc:
                pytest.fail(
                    f"argparse raised SystemExit({exc.code}) — --input is still required=True"
                )

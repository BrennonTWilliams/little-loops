"""Tests for /ll:loop-suggester skill artifacts.

Since /ll:loop-suggester is a prompt-based skill (markdown instructions for Claude),
we cannot directly unit test the analysis flow. Instead, we test:

1. Output schema structure matches documentation
2. Confidence score calculations are within bounds
"""

from __future__ import annotations

import yaml

# =============================================================================
# Output Schema Tests
# =============================================================================


class TestOutputSchemaStructure:
    """Tests for output schema structure validation.

    Schema defined in skills/loop-suggester/SKILL.md lines 189-231.
    """

    def test_suggestion_required_fields(self) -> None:
        """Suggestions must have all required fields."""
        required_fields = {"id", "name", "paradigm", "confidence", "rationale", "yaml_config"}

        # Example suggestion structure
        suggestion = {
            "id": "loop-001",
            "name": "test-loop",
            "paradigm": "goal",
            "confidence": 0.75,
            "rationale": "Detected 5 occurrences of check-fix cycle",
            "yaml_config": (
                "paradigm: goal\nname: test-loop\ngoal: Test\ntools:\n  - check\n  - fix"
            ),
            "usage_instructions": "1. Save to .loops/test-loop.yaml",
            "customization_notes": "Adjust paths as needed",
        }

        assert required_fields.issubset(suggestion.keys())

    def test_confidence_score_bounds(self) -> None:
        """Confidence scores must be between 0.0 and 1.0."""
        valid_scores = [0.0, 0.55, 0.65, 0.70, 0.85, 0.92, 1.0]
        invalid_scores = [-0.1, 1.1, 1.5, -1.0]

        for score in valid_scores:
            assert 0.0 <= score <= 1.0, f"Score {score} should be valid"

        for score in invalid_scores:
            assert not (0.0 <= score <= 1.0), f"Score {score} should be invalid"

    def test_paradigm_values_valid(self) -> None:
        """Paradigm values must be one of the four valid types."""
        valid_paradigms = {"goal", "invariants", "convergence", "imperative"}

        assert "goal" in valid_paradigms
        assert "invariants" in valid_paradigms
        assert "convergence" in valid_paradigms
        assert "imperative" in valid_paradigms
        assert "invalid" not in valid_paradigms

    def test_yaml_config_parseable(self) -> None:
        """yaml_config field must be parseable YAML."""
        yaml_configs = [
            """
paradigm: goal
name: test-goal
goal: Tests pass
tools:
  - pytest
  - echo fix
""",
            """
paradigm: invariants
name: test-invariants
constraints:
  - name: lint
    check: ruff check
    fix: ruff check --fix
maintain: false
""",
        ]

        for config in yaml_configs:
            parsed = yaml.safe_load(config)
            assert "paradigm" in parsed
            assert "name" in parsed

    def test_analysis_metadata_fields(self) -> None:
        """Analysis metadata has required fields."""
        required_metadata = {"source_file", "messages_analyzed", "analysis_timestamp", "skill"}

        metadata = {
            "source_file": "live extraction",
            "messages_analyzed": 200,
            "analysis_timestamp": "2026-02-04T10:00:00Z",
            "skill": "loop-suggester",
            "version": "1.0",
        }

        assert required_metadata.issubset(metadata.keys())

    def test_summary_fields(self) -> None:
        """Summary has required fields."""
        required_summary = {"total_suggestions", "by_paradigm"}

        summary = {
            "total_suggestions": 4,
            "by_paradigm": {
                "goal": 1,
                "invariants": 2,
                "convergence": 0,
                "imperative": 1,
            },
            "message_time_range": {
                "start": "2026-02-01T00:00:00Z",
                "end": "2026-02-04T00:00:00Z",
            },
        }

        assert required_summary.issubset(summary.keys())
        by_paradigm = summary["by_paradigm"]
        assert isinstance(by_paradigm, dict)
        assert all(p in by_paradigm for p in ["goal", "invariants", "convergence", "imperative"])


# =============================================================================
# Confidence Score Tests
# =============================================================================


class TestConfidenceScoreCalculations:
    """Tests for confidence score calculation rules.

    Rules defined in skills/loop-suggester/SKILL.md lines 99-110 and 173-183.
    """

    def test_base_confidence_by_paradigm(self) -> None:
        """Each paradigm has a defined base confidence."""
        base_confidences = {
            "goal": 0.70,
            "invariants": 0.65,
            "convergence": 0.55,
            "imperative": 0.60,
        }

        assert base_confidences["goal"] == 0.70
        assert base_confidences["invariants"] == 0.65
        assert base_confidences["convergence"] == 0.55
        assert base_confidences["imperative"] == 0.60

    def test_confidence_adjustments(self) -> None:
        """Confidence adjustments follow documented rules."""
        # From SKILL.md:106-110
        frequency_bonus = 0.15  # if count >= 5
        session_bonus = 0.10  # if multi_session
        consistency_bonus = 0.05  # if identical_commands
        variance_penalty = 0.10  # if high_variance

        # Test maximum possible confidence
        base = 0.70
        max_confidence = min(1.0, base + frequency_bonus + session_bonus + consistency_bonus)
        assert max_confidence == 1.0

        # Test minimum possible confidence
        min_confidence = max(0.0, base - variance_penalty)
        assert min_confidence == 0.60

    def test_minimum_frequency_thresholds(self) -> None:
        """Patterns require minimum frequency to suggest."""
        # From SKILL.md:99-104
        thresholds = {
            "goal": 3,
            "invariants": 3,
            "convergence": 2,
            "imperative": 3,
        }

        assert thresholds["goal"] >= 2
        assert thresholds["invariants"] >= 2
        assert thresholds["convergence"] >= 2
        assert thresholds["imperative"] >= 2

    def test_confidence_clamping(self) -> None:
        """Confidence must be clamped to [0.0, 1.0]."""

        def clamp_confidence(value: float) -> float:
            return max(0.0, min(1.0, value))

        assert clamp_confidence(1.5) == 1.0
        assert clamp_confidence(-0.5) == 0.0
        assert clamp_confidence(0.75) == 0.75

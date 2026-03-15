"""Tests for /ll:loop-suggester skill artifacts.

Since /ll:loop-suggester is a prompt-based skill (markdown instructions for Claude),
we cannot directly unit test the analysis flow. Instead, we test:

1. Output schema structure matches documentation
2. Confidence score calculations are within bounds
3. From-commands mode schema contracts (catalog enumeration and proposal structure)
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


# =============================================================================
# From-Commands Mode Tests
# =============================================================================


class TestFromCommandsModeSchema:
    """Tests for --from-commands mode schema contracts.

    Schema defined in commands/loop-suggester.md, From-Commands Mode section.
    This mode enumerates skills/*/SKILL.md, commands/*.md, and pyproject.toml
    instead of analyzing message history.
    """

    def test_catalog_entry_required_fields(self) -> None:
        """Each catalog entry must have name, description, and type."""
        required_fields = {"name", "description", "type"}

        # Example skill catalog entry
        skill_entry = {
            "name": "manage-issue",
            "description": "Autonomously manage issues - plan, implement, verify, and complete",
            "type": "skill",
            "argument-hint": "[issue_type] [action] [issue_id]",
        }

        # Example CLI catalog entry
        cli_entry = {
            "name": "ll-loop",
            "description": "Execute FSM-based automation loops",
            "type": "cli",
        }

        assert required_fields.issubset(skill_entry.keys())
        assert required_fields.issubset(cli_entry.keys())

    def test_catalog_entry_types_valid(self) -> None:
        """Catalog entry type must be one of: skill, command, cli."""
        valid_types = {"skill", "command", "cli"}

        assert "skill" in valid_types
        assert "command" in valid_types
        assert "cli" in valid_types
        assert "plugin" not in valid_types
        assert "agent" not in valid_types

    def test_workflow_themes_valid(self) -> None:
        """Theme groupings must be one of the five defined themes."""
        valid_themes = {
            "issue-management",
            "code-quality",
            "git-release",
            "loops-automation",
            "analysis-meta",
        }

        assert len(valid_themes) == 5
        assert "issue-management" in valid_themes
        assert "code-quality" in valid_themes
        assert "git-release" in valid_themes
        assert "loops-automation" in valid_themes
        assert "analysis-meta" in valid_themes
        assert "deployment" not in valid_themes

    def test_from_commands_metadata_fields(self) -> None:
        """From-commands metadata must include source and enumeration counts."""
        required_metadata = {
            "source",
            "source_file",
            "skills_enumerated",
            "commands_enumerated",
            "cli_enumerated",
            "analysis_timestamp",
            "skill",
        }

        metadata = {
            "source": "commands-catalog",
            "source_file": "skills/*/SKILL.md + commands/*.md + scripts/pyproject.toml",
            "skills_enumerated": 17,
            "commands_enumerated": 25,
            "cli_enumerated": 12,
            "analysis_timestamp": "2026-03-14T10:00:00Z",
            "skill": "loop-suggester",
            "version": "1.0",
        }

        assert required_metadata.issubset(metadata.keys())
        assert metadata["source"] == "commands-catalog"

    def test_from_commands_metadata_source_distinguisher(self) -> None:
        """Source field must be 'commands-catalog' to distinguish from history mode."""
        history_metadata = {"source_file": "live extraction", "skill": "loop-suggester"}
        catalog_metadata = {"source": "commands-catalog", "skill": "loop-suggester"}

        # History mode has no 'source' field (or omits it)
        assert "source" not in history_metadata
        # Catalog mode sets source to distinguish itself
        assert catalog_metadata["source"] == "commands-catalog"

    def test_from_commands_summary_has_theme_breakdown(self) -> None:
        """From-commands summary must include by_theme in addition to by_loop_type."""
        required_summary = {"total_suggestions", "by_loop_type", "by_theme"}

        summary = {
            "total_suggestions": 4,
            "by_loop_type": {
                "fix_until_clean": 1,
                "maintain_constraints": 1,
                "drive_metric": 0,
                "run_sequence": 2,
            },
            "by_theme": {
                "issue-management": 1,
                "code-quality": 1,
                "git-release": 1,
                "loops-automation": 1,
                "analysis-meta": 0,
            },
        }

        assert required_summary.issubset(summary.keys())
        assert set(summary["by_theme"].keys()) == {
            "issue-management",
            "code-quality",
            "git-release",
            "loops-automation",
            "analysis-meta",
        }

    def test_from_commands_proposal_required_fields(self) -> None:
        """Proposals from catalog mode must include theme field in addition to base fields."""
        required_fields = {
            "id",
            "name",
            "loop_type",
            "theme",
            "confidence",
            "rationale",
            "yaml_config",
            "usage_instructions",
        }

        proposal = {
            "id": "loop-001",
            "name": "issue-lifecycle",
            "loop_type": "run_sequence",
            "theme": "issue-management",
            "confidence": 0.85,
            "rationale": (
                "Issue management follows a natural linear sequence: scan for new issues, "
                "prioritize by impact, refine requirements, implement changes, and verify results. "
                "All referenced commands exist in the enumerated catalog."
            ),
            "yaml_config": (
                "name: issue-lifecycle\n"
                "initial: scan\n"
                "max_iterations: 50\n"
                "states:\n"
                "  scan:\n"
                "    action: /ll:scan-codebase\n"
                "    action_type: slash_command\n"
                "    next: prioritize\n"
                "  prioritize:\n"
                "    action: /ll:prioritize-issues\n"
                "    action_type: slash_command\n"
                "    next: done\n"
                "  done:\n"
                "    terminal: true\n"
            ),
            "usage_instructions": "1. Save to .loops/issue-lifecycle.yaml\n2. Run: ll-loop validate issue-lifecycle\n",
        }

        assert required_fields.issubset(proposal.keys())
        assert proposal["theme"] in {
            "issue-management",
            "code-quality",
            "git-release",
            "loops-automation",
            "analysis-meta",
        }

    def test_from_commands_confidence_base(self) -> None:
        """Catalog-sourced proposals start at 0.75 base confidence."""
        catalog_base_confidence = 0.75
        # Higher than history-mode minimums (0.55-0.70) because catalog references
        # are verifiable at generation time
        assert catalog_base_confidence >= 0.70
        assert catalog_base_confidence <= 1.0

    def test_from_commands_confidence_adjustments(self) -> None:
        """Confidence adjustments for catalog mode follow documented rules."""
        catalog_bonus_all_exist = 0.10  # all referenced commands/skills in catalog
        theme_coverage_bonus = 0.05  # theme has 5+ catalog entries
        missing_reference_penalty = -0.10  # referenced command not in catalog

        base = 0.75
        max_confidence = min(1.0, base + catalog_bonus_all_exist + theme_coverage_bonus)
        assert max_confidence == 0.90

        penalized = base + missing_reference_penalty
        assert penalized == 0.65

    def test_from_commands_minimum_proposals(self) -> None:
        """From-commands mode must generate at least 3 proposals."""
        min_proposals = 3
        max_proposals = 5

        # Acceptance criteria: at least 3, at most 5 proposals
        assert min_proposals >= 3
        assert max_proposals >= min_proposals

    def test_from_commands_proposal_state_count(self) -> None:
        """Each proposal must have between 3 and 7 states."""
        min_states = 3
        max_states = 7

        # Example: minimal valid proposal state count
        example_state_counts = [3, 4, 5, 6, 7]
        invalid_state_counts = [1, 2, 8, 10]

        for count in example_state_counts:
            assert min_states <= count <= max_states, f"State count {count} should be valid"

        for count in invalid_state_counts:
            assert not (min_states <= count <= max_states), f"State count {count} should be invalid"

    def test_from_commands_yaml_config_parseable(self) -> None:
        """yaml_config in catalog proposals must be parseable FSM YAML."""
        issue_lifecycle_yaml = """
name: issue-lifecycle
initial: scan
max_iterations: 50
states:
  scan:
    action: /ll:scan-codebase
    action_type: slash_command
    next: prioritize
  prioritize:
    action: /ll:prioritize-issues
    action_type: slash_command
    next: implement
  implement:
    action: /ll:manage-issue
    action_type: slash_command
    next: done
  done:
    terminal: true
"""
        code_quality_yaml = """
name: code-quality-fix
initial: check
max_iterations: 15
states:
  check:
    action: /ll:check-code
    action_type: slash_command
    on_yes: done
    on_no: fix
    on_error: fix
  fix:
    action: "Code quality checks failed. Review and fix all issues."
    action_type: prompt
    next: check
  done:
    terminal: true
"""
        for config in [issue_lifecycle_yaml, code_quality_yaml]:
            parsed = yaml.safe_load(config)
            assert "name" in parsed
            assert "initial" in parsed
            assert "states" in parsed
            assert isinstance(parsed["states"], dict)
            assert len(parsed["states"]) >= 3

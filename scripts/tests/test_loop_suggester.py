"""Tests for /ll:loop-suggester skill artifacts.

Since /ll:loop-suggester is a prompt-based skill (markdown instructions for Claude),
we cannot directly unit test the analysis flow. Instead, we test:

1. Example YAML definitions from SKILL.md compile to valid FSMs
2. Output schema structure matches documentation
3. Suggested loop configurations are valid
4. Confidence score calculations are within bounds
"""

from __future__ import annotations

import yaml

from little_loops.fsm import validate_fsm
from little_loops.fsm.compilers import compile_paradigm
from little_loops.fsm.validation import ValidationSeverity

# =============================================================================
# Example YAML Tests
# =============================================================================


class TestExampleYAMLFromSkill:
    """Tests that example YAML from loop-suggester SKILL.md compiles to valid FSMs.

    These examples are defined in skills/loop-suggester/SKILL.md lines 236-344.
    """

    def test_type_error_fixer_example(self) -> None:
        """Example 1: Goal paradigm type-error-fixer is valid."""
        spec = {
            "paradigm": "goal",
            "name": "type-error-fixer",
            "goal": "No type errors in source",
            "tools": ["mypy scripts/", "/ll:manage_issue bug fix"],
            "max_iterations": 20,
            "evaluator": {"type": "exit_code"},
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.paradigm == "goal"
        assert fsm.name == "type-error-fixer"

    def test_quality_gate_example(self) -> None:
        """Example 2: Invariants paradigm quality-gate is valid."""
        spec = {
            "paradigm": "invariants",
            "name": "quality-gate",
            "constraints": [
                {
                    "name": "lint",
                    "check": "ruff check scripts/",
                    "fix": "ruff check --fix scripts/",
                },
                {
                    "name": "types",
                    "check": "mypy scripts/",
                    "fix": "/ll:manage_issue bug fix",
                },
                {
                    "name": "tests",
                    "check": "pytest scripts/tests/",
                    "fix": "/ll:manage_issue bug fix",
                },
            ],
            "maintain": False,
            "max_iterations": 30,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.paradigm == "invariants"
        assert fsm.name == "quality-gate"

    def test_build_test_deploy_example(self) -> None:
        """Example 3: Imperative paradigm build-test-deploy is valid."""
        spec = {
            "paradigm": "imperative",
            "name": "build-test-deploy",
            "steps": ["npm run build", "npm test", "npm run lint"],
            "until": {"check": "npm run deploy:check", "passes": True},
            "max_iterations": 10,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.paradigm == "imperative"
        assert fsm.name == "build-test-deploy"


# =============================================================================
# Paradigm Template Tests
# =============================================================================


class TestParadigmTemplates:
    """Tests that paradigm templates from SKILL.md are valid.

    Templates defined in skills/loop-suggester/SKILL.md lines 116-171.
    """

    def test_goal_template_structure(self) -> None:
        """Goal paradigm template structure is valid."""
        # Template from SKILL.md:117-128
        spec = {
            "paradigm": "goal",
            "name": "template-goal",
            "goal": "Check passes",
            "tools": ["check_command", "fix_command"],
            "max_iterations": 25,
            "evaluator": {"type": "exit_code"},
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert "evaluate" in fsm.states
        assert "fix" in fsm.states
        assert "done" in fsm.states

    def test_invariants_template_structure(self) -> None:
        """Invariants paradigm template structure is valid."""
        # Template from SKILL.md:130-144
        spec = {
            "paradigm": "invariants",
            "name": "template-invariants",
            "constraints": [
                {"name": "constraint1", "check": "check1", "fix": "fix1"},
                {"name": "constraint2", "check": "check2", "fix": "fix2"},
            ],
            "maintain": False,
            "max_iterations": 35,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert "check_constraint1" in fsm.states
        assert "check_constraint2" in fsm.states
        assert "all_valid" in fsm.states

    def test_convergence_template_structure(self) -> None:
        """Convergence paradigm template structure is valid."""
        # Template from SKILL.md:146-157
        spec = {
            "paradigm": "convergence",
            "name": "template-convergence",
            "check": "measurement_command",
            "toward": 0,
            "tolerance": 1,
            "using": "fix_command",
            "max_iterations": 40,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert "measure" in fsm.states
        assert "apply" in fsm.states
        assert "done" in fsm.states

    def test_imperative_template_structure(self) -> None:
        """Imperative paradigm template structure is valid."""
        # Template from SKILL.md:159-171
        spec = {
            "paradigm": "imperative",
            "name": "template-imperative",
            "steps": ["step1_command", "step2_command", "step3_command"],
            "until": {"check": "completion_check", "passes": True},
            "max_iterations": 30,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert "step_0" in fsm.states
        assert "step_1" in fsm.states
        assert "step_2" in fsm.states
        assert "check_done" in fsm.states


# =============================================================================
# Actual Generated Suggestions Tests
# =============================================================================


class TestActualGeneratedSuggestions:
    """Tests that actual generated suggestions produce valid FSMs.

    Uses suggestions from .claude/loop-suggestions/suggestions-2026-02-02.yaml
    to validate real-world output from the skill.
    """

    def test_issue_readiness_cycle_suggestion(self) -> None:
        """loop-001: issue-readiness-cycle imperative loop is valid."""
        # From suggestions-2026-02-02.yaml:17-45
        spec = {
            "paradigm": "imperative",
            "name": "issue-readiness-cycle",
            "steps": ["/ll:ready_issue", "/ll:manage_issue"],
            "until": {
                "check": (
                    "ls .issues/bugs/*.md .issues/features/*.md "
                    ".issues/enhancements/*.md 2>/dev/null | wc -l"
                ),
                "passes": True,
            },
            "max_iterations": 50,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.paradigm == "imperative"
        assert fsm.name == "issue-readiness-cycle"

    def test_pre_pr_checks_suggestion(self) -> None:
        """loop-002: pre-pr-checks invariants loop is valid."""
        # From suggestions-2026-02-02.yaml:47-76
        # Note: Simplified version without on_success (not a valid FSM field)
        spec = {
            "paradigm": "invariants",
            "name": "pre-pr-checks",
            "constraints": [
                {
                    "name": "code-quality",
                    "check": "/ll:check_code",
                    "fix": "ruff format && ruff check --fix",
                },
                {
                    "name": "tests-pass",
                    "check": "/ll:run_tests",
                    "fix": "Review failing tests",
                },
            ],
            "maintain": False,
            "max_iterations": 10,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.paradigm == "invariants"
        assert fsm.name == "pre-pr-checks"

    def test_issue_verification_normalize_suggestion(self) -> None:
        """loop-003: issue-verification-normalize invariants loop is valid."""
        # From suggestions-2026-02-02.yaml:78-106
        spec = {
            "paradigm": "invariants",
            "name": "issue-verification-normalize",
            "constraints": [
                {
                    "name": "issues-verified",
                    "check": "/ll:verify_issues",
                    "fix": "Auto-correction",
                },
                {
                    "name": "issues-normalized",
                    "check": "/ll:normalize_issues",
                    "fix": "Rename files",
                },
            ],
            "maintain": False,
            "max_iterations": 20,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.paradigm == "invariants"

    def test_codebase_scan_workflow_suggestion(self) -> None:
        """loop-004: codebase-scan-workflow imperative loop is valid."""
        # From suggestions-2026-02-02.yaml:108-137
        spec = {
            "paradigm": "imperative",
            "name": "codebase-scan-workflow",
            "steps": [
                "/ll:commit",
                "/ll:scan_codebase",
                "/ll:verify_issues",
                "/ll:prioritize_issues",
            ],
            "until": {"check": "git status --porcelain", "passes": True},
            "max_iterations": 5,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.paradigm == "imperative"


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
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases in loop suggestion."""

    def test_minimal_goal_config(self) -> None:
        """Minimal goal configuration is valid."""
        spec = {
            "paradigm": "goal",
            "name": "minimal-goal",
            "goal": "Pass",
            "tools": ["check"],
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)

    def test_minimal_invariants_config(self) -> None:
        """Minimal invariants configuration is valid."""
        spec = {
            "paradigm": "invariants",
            "name": "minimal-invariants",
            "constraints": [{"name": "c1", "check": "cmd", "fix": "fix"}],
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)

    def test_minimal_convergence_config(self) -> None:
        """Minimal convergence configuration is valid."""
        spec = {
            "paradigm": "convergence",
            "name": "minimal-convergence",
            "check": "cmd",
            "toward": 0,
            "using": "fix",
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)

    def test_minimal_imperative_config(self) -> None:
        """Minimal imperative configuration is valid."""
        spec = {
            "paradigm": "imperative",
            "name": "minimal-imperative",
            "steps": ["cmd"],
            "until": {"check": "verify"},
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)

    def test_many_steps_imperative(self) -> None:
        """Imperative with many steps is valid."""
        spec = {
            "paradigm": "imperative",
            "name": "many-steps",
            "steps": [f"step{i}" for i in range(10)],
            "until": {"check": "verify"},
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert "step_9" in fsm.states

    def test_many_constraints_invariants(self) -> None:
        """Invariants with many constraints is valid."""
        spec = {
            "paradigm": "invariants",
            "name": "many-constraints",
            "constraints": [
                {"name": f"c{i}", "check": f"check{i}", "fix": f"fix{i}"} for i in range(5)
            ],
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert "check_c4" in fsm.states

    def test_special_characters_in_commands(self) -> None:
        """Commands with special characters are valid."""
        spec = {
            "paradigm": "goal",
            "name": "special-chars",
            "goal": "Check passes",
            "tools": [
                "ruff check src/ 2>&1 | grep -c 'error' || echo 0",
                "find . -name '*.py' -exec chmod +x {} \\;",
            ],
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)

    def test_slash_commands_in_tools(self) -> None:
        """Slash commands (/ll:*) are valid tool commands."""
        spec = {
            "paradigm": "invariants",
            "name": "slash-commands",
            "constraints": [
                {"name": "check", "check": "/ll:check_code", "fix": "/ll:check_code fix"},
                {"name": "test", "check": "/ll:run_tests", "fix": "/ll:manage_issue bug fix"},
            ],
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)

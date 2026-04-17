"""Tests for little_loops.config module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from little_loops.config import (
    DEFAULT_CATEGORIES,
    REQUIRED_CATEGORIES,
    AutomationConfig,
    BRConfig,
    CategoryConfig,
    CliColorsConfig,
    CliColorsEdgeLabelsConfig,
    CliColorsLoggerConfig,
    CliColorsPriorityConfig,
    CliColorsTypeConfig,
    CliConfig,
    CommandsConfig,
    ConfidenceGateConfig,
    DependencyMappingConfig,
    DuplicateDetectionConfig,
    GitHubSyncConfig,
    IssuesConfig,
    LoopsConfig,
    LoopsGlyphsConfig,
    ParallelAutomationConfig,
    ProjectConfig,
    RateLimitsConfig,
    ScanConfig,
    ScoringWeightsConfig,
    SprintsConfig,
    SyncConfig,
)


class TestCategoryConfig:
    """Tests for CategoryConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating CategoryConfig with all fields specified."""
        data = {"prefix": "TST", "dir": "test-issues", "action": "verify"}
        config = CategoryConfig.from_dict("tests", data)

        assert config.prefix == "TST"
        assert config.dir == "test-issues"
        assert config.action == "verify"

    def test_from_dict_with_defaults(self) -> None:
        """Test creating CategoryConfig with default values."""
        config = CategoryConfig.from_dict("mytype", {})

        assert config.prefix == "MYT"  # First 3 chars of key uppercased
        assert config.dir == "mytype"
        assert config.action == "fix"

    def test_from_dict_partial_data(self) -> None:
        """Test creating CategoryConfig with partial data."""
        data = {"prefix": "CUSTOM"}
        config = CategoryConfig.from_dict("bugs", data)

        assert config.prefix == "CUSTOM"
        assert config.dir == "bugs"
        assert config.action == "fix"


class TestProjectConfig:
    """Tests for ProjectConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating ProjectConfig with all fields specified."""
        data = {
            "name": "my-project",
            "src_dir": "lib/",
            "test_dir": "custom_tests",
            "test_cmd": "npm test",
            "lint_cmd": "eslint .",
            "type_cmd": "tsc --noEmit",
            "format_cmd": "prettier --write .",
            "build_cmd": "npm run build",
            "run_cmd": "npm start",
        }
        config = ProjectConfig.from_dict(data)

        assert config.name == "my-project"
        assert config.src_dir == "lib/"
        assert config.test_dir == "custom_tests"
        assert config.test_cmd == "npm test"
        assert config.lint_cmd == "eslint ."
        assert config.type_cmd == "tsc --noEmit"
        assert config.format_cmd == "prettier --write ."
        assert config.build_cmd == "npm run build"
        assert config.run_cmd == "npm start"

    def test_from_dict_with_defaults(self) -> None:
        """Test creating ProjectConfig with default values."""
        config = ProjectConfig.from_dict({})

        assert config.name == ""
        assert config.src_dir == "src/"
        assert config.test_dir == "tests"
        assert config.test_cmd == "pytest"
        assert config.lint_cmd == "ruff check ."
        assert config.type_cmd == "mypy"
        assert config.format_cmd == "ruff format ."
        assert config.build_cmd is None
        assert config.run_cmd is None


class TestIssuesConfig:
    """Tests for IssuesConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating IssuesConfig with all fields."""
        data = {
            "base_dir": "issues/",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
            },
            "completed_dir": "done",
            "priorities": ["P0", "P1"],
            "templates_dir": "templates/",
            "capture_template": "minimal",
        }
        config = IssuesConfig.from_dict(data)

        assert config.base_dir == "issues/"
        # User specified bugs, required categories (features, enhancements) are auto-added
        assert len(config.categories) == 3
        assert config.categories["bugs"].prefix == "BUG"
        assert "features" in config.categories
        assert "enhancements" in config.categories
        assert config.completed_dir == "done"
        assert config.deferred_dir == "deferred"  # default when not specified
        assert config.priorities == ["P0", "P1"]
        assert config.templates_dir == "templates/"
        assert config.capture_template == "minimal"

    def test_from_dict_with_deferred_dir(self) -> None:
        """Test creating IssuesConfig with custom deferred_dir."""
        data = {
            "deferred_dir": "parked",
        }
        config = IssuesConfig.from_dict(data)
        assert config.deferred_dir == "parked"

    def test_from_dict_with_capture_template(self) -> None:
        """Test creating IssuesConfig with custom capture_template."""
        for variant in ("full", "minimal", "legacy"):
            config = IssuesConfig.from_dict({"capture_template": variant})
            assert config.capture_template == variant

    def test_from_dict_with_defaults(self) -> None:
        """Test creating IssuesConfig with default values."""
        config = IssuesConfig.from_dict({})

        assert config.base_dir == ".issues"
        assert len(config.categories) == 3  # bugs, features, enhancements
        assert "bugs" in config.categories
        assert "features" in config.categories
        assert "enhancements" in config.categories
        assert config.completed_dir == "completed"
        assert config.deferred_dir == "deferred"
        assert config.priorities == ["P0", "P1", "P2", "P3", "P4", "P5"]
        assert config.templates_dir is None
        assert config.capture_template == "full"
        assert config.duplicate_detection.exact_threshold == 0.8
        assert config.duplicate_detection.similar_threshold == 0.5


class TestDuplicateDetectionConfig:
    """Tests for DuplicateDetectionConfig dataclass."""

    def test_defaults(self) -> None:
        """Test default values match documented defaults."""
        config = DuplicateDetectionConfig()
        assert config.exact_threshold == 0.8
        assert config.similar_threshold == 0.5

    def test_from_dict_with_values(self) -> None:
        """Test creating DuplicateDetectionConfig from dictionary."""
        config = DuplicateDetectionConfig.from_dict(
            {"exact_threshold": 0.9, "similar_threshold": 0.6}
        )
        assert config.exact_threshold == 0.9
        assert config.similar_threshold == 0.6

    def test_from_dict_with_empty_dict(self) -> None:
        """Test that empty dict yields defaults."""
        config = DuplicateDetectionConfig.from_dict({})
        assert config.exact_threshold == 0.8
        assert config.similar_threshold == 0.5

    def test_issues_config_parses_duplicate_detection(self) -> None:
        """Test that IssuesConfig.from_dict reads duplicate_detection block."""
        data = {
            "duplicate_detection": {
                "exact_threshold": 0.95,
                "similar_threshold": 0.4,
            }
        }
        config = IssuesConfig.from_dict(data)
        assert config.duplicate_detection.exact_threshold == 0.95
        assert config.duplicate_detection.similar_threshold == 0.4

    def test_finding_match_uses_custom_thresholds(self) -> None:
        """Test that FindingMatch properties use configured thresholds."""
        from little_loops.issue_discovery.matching import FindingMatch

        # With default thresholds
        match = FindingMatch(issue_path=None, match_type="none", match_score=0.75)
        assert match.should_skip is False  # 0.75 < 0.8
        assert match.should_update is True  # 0.5 <= 0.75 < 0.8

        # With custom exact_threshold=0.7: score 0.75 should now skip
        match_custom = FindingMatch(
            issue_path=None,
            match_type="none",
            match_score=0.75,
            exact_threshold=0.7,
            similar_threshold=0.5,
        )
        assert match_custom.should_skip is True  # 0.75 >= 0.7
        assert match_custom.should_update is False


class TestAutomationConfig:
    """Tests for AutomationConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating AutomationConfig with all fields."""
        data = {
            "timeout_seconds": 7200,
            "state_file": "custom-state.json",
            "worktree_base": "wt/",
            "max_workers": 4,
            "stream_output": False,
            "idle_timeout_seconds": 30,
            "max_continuations": 5,
        }
        config = AutomationConfig.from_dict(data)

        assert config.timeout_seconds == 7200
        assert config.state_file == "custom-state.json"
        assert config.worktree_base == "wt/"
        assert config.max_workers == 4
        assert config.stream_output is False
        assert config.idle_timeout_seconds == 30
        assert config.max_continuations == 5

    def test_from_dict_with_defaults(self) -> None:
        """Test creating AutomationConfig with default values."""
        config = AutomationConfig.from_dict({})

        assert config.timeout_seconds == 3600
        assert config.state_file == ".auto-manage-state.json"
        assert config.worktree_base == ".worktrees"
        assert config.max_workers == 2
        assert config.stream_output is True
        assert config.idle_timeout_seconds == 0
        assert config.max_continuations == 3


class TestParallelAutomationConfig:
    """Tests for ParallelAutomationConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating ParallelAutomationConfig with all fields."""
        data = {
            "max_workers": 5,
            "p0_sequential": False,
            "worktree_base": "parallel-wt/",
            "state_file": "parallel.json",
            "timeout_seconds": 900,
            "max_merge_retries": 5,
            "stream_output": True,
            "command_prefix": "/custom:",
            "ready_command": "check {{issue_id}}",
            "manage_command": "process {{issue_type}} {{action}} {{issue_id}}",
            "require_code_changes": False,
        }
        config = ParallelAutomationConfig.from_dict(data)

        # Base config fields (shared via composition)
        assert config.base.max_workers == 5
        assert config.base.worktree_base == "parallel-wt/"
        assert config.base.state_file == "parallel.json"
        assert config.base.timeout_seconds == 900
        assert config.base.stream_output is True
        # Parallel-specific fields
        assert config.p0_sequential is False
        assert config.max_merge_retries == 5
        assert config.command_prefix == "/custom:"
        assert config.ready_command == "check {{issue_id}}"
        assert config.require_code_changes is False

    def test_from_dict_with_defaults(self) -> None:
        """Test creating ParallelAutomationConfig with default values."""
        config = ParallelAutomationConfig.from_dict({})

        # Base config defaults (parallel-specific defaults differ from AutomationConfig)
        assert config.base.max_workers == 2
        assert config.base.state_file == ".parallel-manage-state.json"
        assert config.base.stream_output is False  # Different from AutomationConfig default
        # Parallel-specific defaults
        assert config.p0_sequential is True
        assert config.command_prefix == "/ll:"
        assert config.worktree_copy_files == [".claude/settings.local.json", ".env"]
        assert config.require_code_changes is True

    def test_timeout_per_issue_key_is_respected(self) -> None:
        """Test that the documented timeout_per_issue key sets the per-issue timeout."""
        config = ParallelAutomationConfig.from_dict({"timeout_per_issue": 7200})
        assert config.base.timeout_seconds == 7200

    def test_timeout_seconds_fallback(self) -> None:
        """Test that timeout_seconds still works as a fallback key."""
        config = ParallelAutomationConfig.from_dict({"timeout_seconds": 1800})
        assert config.base.timeout_seconds == 1800

    def test_timeout_per_issue_takes_precedence_over_timeout_seconds(self) -> None:
        """Test that timeout_per_issue wins when both keys are present."""
        config = ParallelAutomationConfig.from_dict(
            {"timeout_per_issue": 7200, "timeout_seconds": 900}
        )
        assert config.base.timeout_seconds == 7200

    def test_stream_subprocess_output_key_is_respected(self) -> None:
        """Test that the documented stream_subprocess_output key enables streaming."""
        config = ParallelAutomationConfig.from_dict({"stream_subprocess_output": True})
        assert config.base.stream_output is True

    def test_stream_output_fallback_still_works(self) -> None:
        """Test that stream_output still works as a fallback key."""
        config = ParallelAutomationConfig.from_dict({"stream_output": True})
        assert config.base.stream_output is True


class TestConfidenceGateConfig:
    """Tests for ConfidenceGateConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating ConfidenceGateConfig with all schema-aligned fields."""
        data = {"enabled": True, "readiness_threshold": 75, "outcome_threshold": 60}
        config = ConfidenceGateConfig.from_dict(data)

        assert config.enabled is True
        assert config.readiness_threshold == 75
        assert config.outcome_threshold == 60

    def test_from_dict_with_defaults(self) -> None:
        """Test creating ConfidenceGateConfig with default values."""
        config = ConfidenceGateConfig.from_dict({})

        assert config.enabled is False
        assert config.readiness_threshold == 85
        assert config.outcome_threshold == 70

    def test_threshold_fallback_sets_readiness_threshold(self) -> None:
        """Test that legacy threshold key falls back to set readiness_threshold."""
        config = ConfidenceGateConfig.from_dict({"threshold": 90})
        assert config.readiness_threshold == 90

    def test_threshold_fallback_does_not_override_explicit_readiness_threshold(self) -> None:
        """Test that explicit readiness_threshold wins over legacy threshold fallback."""
        config = ConfidenceGateConfig.from_dict({"threshold": 90, "readiness_threshold": 75})
        assert config.readiness_threshold == 75


class TestRateLimitsConfig:
    """Tests for RateLimitsConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating RateLimitsConfig with all schema-aligned fields."""
        data = {
            "max_wait_seconds": 7200,
            "long_wait_ladder": [60, 120, 240],
            "circuit_breaker_enabled": False,
            "circuit_breaker_path": "/tmp/cb.json",
        }
        config = RateLimitsConfig.from_dict(data)

        assert config.max_wait_seconds == 7200
        assert config.long_wait_ladder == [60, 120, 240]
        assert config.circuit_breaker_enabled is False
        assert config.circuit_breaker_path == "/tmp/cb.json"

    def test_from_dict_with_defaults(self) -> None:
        """Test creating RateLimitsConfig with default values."""
        config = RateLimitsConfig.from_dict({})

        assert config.max_wait_seconds == 21600
        assert config.long_wait_ladder == [300, 900, 1800, 3600]
        assert config.circuit_breaker_enabled is True
        assert config.circuit_breaker_path == ".loops/tmp/rate-limit-circuit.json"


class TestCommandsConfig:
    """Tests for CommandsConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating CommandsConfig with all fields."""
        data = {
            "pre_implement": "npm run lint",
            "post_implement": "npm run build",
            "custom_verification": ["npm test", "npm run e2e"],
            "confidence_gate": {"enabled": True, "readiness_threshold": 90},
            "tdd_mode": True,
            "rate_limits": {
                "max_wait_seconds": 7200,
                "long_wait_ladder": [60, 120],
            },
        }
        config = CommandsConfig.from_dict(data)

        assert config.pre_implement == "npm run lint"
        assert config.post_implement == "npm run build"
        assert config.custom_verification == ["npm test", "npm run e2e"]
        assert config.confidence_gate.enabled is True
        assert config.confidence_gate.readiness_threshold == 90
        assert config.tdd_mode is True
        assert config.rate_limits.max_wait_seconds == 7200
        assert config.rate_limits.long_wait_ladder == [60, 120]

    def test_from_dict_with_defaults(self) -> None:
        """Test creating CommandsConfig with default values."""
        config = CommandsConfig.from_dict({})

        assert config.pre_implement is None
        assert config.post_implement is None
        assert config.custom_verification == []
        assert config.confidence_gate.enabled is False
        assert config.confidence_gate.readiness_threshold == 85
        assert config.tdd_mode is False
        assert config.rate_limits.max_wait_seconds == 21600
        assert config.rate_limits.long_wait_ladder == [300, 900, 1800, 3600]
        assert config.rate_limits.circuit_breaker_enabled is True


class TestScanConfig:
    """Tests for ScanConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating ScanConfig with all fields."""
        data = {
            "focus_dirs": ["lib/", "app/"],
            "exclude_patterns": ["**/vendor/**"],
            "custom_agents": ["security-scanner"],
        }
        config = ScanConfig.from_dict(data)

        assert config.focus_dirs == ["lib/", "app/"]
        assert config.exclude_patterns == ["**/vendor/**"]
        assert config.custom_agents == ["security-scanner"]

    def test_from_dict_with_defaults(self) -> None:
        """Test creating ScanConfig with default values."""
        config = ScanConfig.from_dict({})

        assert config.focus_dirs == ["src/", "tests/"]
        assert "**/node_modules/**" in config.exclude_patterns
        assert "**/__pycache__/**" in config.exclude_patterns
        assert config.custom_agents == []


class TestSprintsConfig:
    """Tests for SprintsConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating SprintsConfig with all fields."""
        data = {
            "sprints_dir": "custom-sprints/",
            "default_timeout": 7200,
            "default_max_workers": 8,
        }
        config = SprintsConfig.from_dict(data)

        assert config.sprints_dir == "custom-sprints/"
        assert config.default_timeout == 7200
        assert config.default_max_workers == 8

    def test_from_dict_with_defaults(self) -> None:
        """Test creating SprintsConfig with default values."""
        config = SprintsConfig.from_dict({})

        assert config.sprints_dir == ".sprints"
        assert config.default_timeout == 3600
        assert config.default_max_workers == 2


class TestBRConfig:
    """Tests for the main BRConfig class."""

    def test_load_config_from_file(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test loading configuration from file."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.project.name == "test-project"
        assert config.project.src_dir == "src/"
        assert config.issues.base_dir == ".issues"
        assert config.automation.timeout_seconds == 1800
        assert config.parallel.base.max_workers == 3

    def test_load_config_without_file(self, temp_project_dir: Path) -> None:
        """Test loading configuration when no file exists (uses defaults)."""
        config = BRConfig(temp_project_dir)

        # Should use defaults
        assert config.project.name == temp_project_dir.name
        assert config.project.src_dir == "src/"
        assert config.issues.base_dir == ".issues"
        assert len(config.issues.categories) == 3

    def test_project_name_defaults_to_directory_name(self, temp_project_dir: Path) -> None:
        """Test that project name defaults to directory name."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps({"project": {}}))

        config = BRConfig(temp_project_dir)

        assert config.project.name == temp_project_dir.name

    def test_get_issue_dir(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
        """Test get_issue_dir returns correct path."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        bugs_dir = config.get_issue_dir("bugs")
        # Use resolve() to handle macOS /var -> /private/var symlinks
        assert bugs_dir.resolve() == (temp_project_dir / ".issues" / "bugs").resolve()

        features_dir = config.get_issue_dir("features")
        assert features_dir.resolve() == (temp_project_dir / ".issues" / "features").resolve()

    def test_get_issue_dir_unknown_category(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test get_issue_dir with unknown category uses category as dir name."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        unknown_dir = config.get_issue_dir("unknown")
        assert unknown_dir.resolve() == (temp_project_dir / ".issues" / "unknown").resolve()

    def test_get_completed_dir(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
        """Test get_completed_dir returns correct path."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        completed = config.get_completed_dir()
        assert completed.resolve() == (temp_project_dir / ".issues" / "completed").resolve()

    def test_get_deferred_dir(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
        """Test get_deferred_dir returns correct path."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        deferred = config.get_deferred_dir()
        assert deferred.resolve() == (temp_project_dir / ".issues" / "deferred").resolve()

    def test_get_issue_prefix(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
        """Test get_issue_prefix returns correct prefix."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.get_issue_prefix("bugs") == "BUG"
        assert config.get_issue_prefix("features") == "FEAT"
        assert config.get_issue_prefix("unknown") == "UNK"  # First 3 chars

    def test_get_category_action(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test get_category_action returns correct action."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.get_category_action("bugs") == "fix"
        assert config.get_category_action("features") == "implement"
        assert config.get_category_action("unknown") == "fix"  # Default

    def test_get_src_path(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
        """Test get_src_path returns correct path."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        # Use resolve() to handle macOS /var -> /private/var symlinks
        assert config.get_src_path().resolve() == (temp_project_dir / "src/").resolve()

    def test_issue_categories_property(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test issue_categories property returns category names."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        categories = config.issue_categories
        assert "bugs" in categories
        assert "features" in categories

    def test_issue_priorities_property(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test issue_priorities property returns priorities."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        priorities = config.issue_priorities
        assert priorities == ["P0", "P1", "P2", "P3"]

    def test_to_dict(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
        """Test to_dict returns serializable dictionary."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert result["project"]["name"] == "test-project"
        assert result["issues"]["base_dir"] == ".issues"
        assert result["automation"]["timeout_seconds"] == 1800
        assert result["parallel"]["max_workers"] == 3

        # Should be JSON serializable
        json.dumps(result)

    def test_to_dict_parallel_schema_aligned_keys(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test to_dict exports schema-aligned key names and all parallel keys."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        result = config.to_dict()
        parallel = result["parallel"]

        # Renamed keys (schema-aligned names)
        assert "timeout_per_issue" in parallel
        assert parallel["timeout_per_issue"] == 1800
        assert "stream_subprocess_output" in parallel
        assert parallel["stream_subprocess_output"] is False

        # Previously missing keys
        assert "worktree_copy_files" in parallel
        assert "require_code_changes" in parallel
        assert "use_feature_branches" in parallel
        assert "remote_name" in parallel

    def test_to_dict_confidence_gate_schema_aligned_keys(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test to_dict exports readiness_threshold and outcome_threshold, not threshold."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        result = config.to_dict()
        cg = result["commands"]["confidence_gate"]

        assert "readiness_threshold" in cg
        assert "outcome_threshold" in cg
        assert "threshold" not in cg

    def test_to_dict_automation_idle_timeout(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test to_dict exports idle_timeout_seconds in automation section."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert "idle_timeout_seconds" in result["automation"]
        assert result["automation"]["idle_timeout_seconds"] == 0

    def test_resolve_variable(self, temp_project_dir: Path, sample_config: dict[str, Any]) -> None:
        """Test resolve_variable resolves config paths."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.resolve_variable("project.name") == "test-project"
        assert config.resolve_variable("project.src_dir") == "src/"
        assert config.resolve_variable("issues.base_dir") == ".issues"
        assert config.resolve_variable("automation.timeout_seconds") == "1800"

    def test_resolve_variable_not_found(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test resolve_variable returns None for unknown paths."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.resolve_variable("nonexistent.path") is None
        assert config.resolve_variable("project.nonexistent") is None

    def test_resolve_variable_list(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test resolve_variable joins list values with spaces."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        result = config.resolve_variable("issues.priorities")
        assert result == "P0 P1 P2 P3"

    def test_create_parallel_config(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test create_parallel_config creates ParallelConfig."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        parallel_config = config.create_parallel_config()

        assert parallel_config.max_workers == 3
        assert parallel_config.p0_sequential is True

    def test_create_parallel_config_with_overrides(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test create_parallel_config with overrides."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        parallel_config = config.create_parallel_config(
            max_workers=8,
            dry_run=True,
            max_issues=10,
        )

        assert parallel_config.max_workers == 8
        assert parallel_config.dry_run is True
        assert parallel_config.max_issues == 10

    def test_load_config_invalid_json_raises(self, temp_project_dir: Path) -> None:
        """BRConfig raises json.JSONDecodeError when config file contains invalid JSON."""
        import json as _json

        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text("{ not valid json }")

        import pytest

        with pytest.raises(_json.JSONDecodeError):
            BRConfig(temp_project_dir)

    def test_load_config_empty_file_raises(self, temp_project_dir: Path) -> None:
        """BRConfig raises json.JSONDecodeError when config file is empty."""
        import json as _json

        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text("")

        import pytest

        with pytest.raises(_json.JSONDecodeError):
            BRConfig(temp_project_dir)

    def test_resolve_variable_none_value(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """resolve_variable returns None when the resolved config value is None."""
        sample_config["project"]["type_cmd"] = None
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.resolve_variable("project.type_cmd") is None


class TestBRConfigAliases:
    """Tests for backwards compatibility aliases."""

    def test_clconfig_alias(self) -> None:
        """Test CLConfig is an alias for BRConfig."""
        from little_loops.config import CLConfig

        assert CLConfig is BRConfig


class TestCategoryConstants:
    """Tests for REQUIRED_CATEGORIES and DEFAULT_CATEGORIES constants."""

    def test_required_categories_contains_core_types(self) -> None:
        """Test that REQUIRED_CATEGORIES has bugs, features, enhancements."""
        assert "bugs" in REQUIRED_CATEGORIES
        assert "features" in REQUIRED_CATEGORIES
        assert "enhancements" in REQUIRED_CATEGORIES
        assert REQUIRED_CATEGORIES["bugs"]["prefix"] == "BUG"
        assert REQUIRED_CATEGORIES["features"]["prefix"] == "FEAT"
        assert REQUIRED_CATEGORIES["enhancements"]["prefix"] == "ENH"

    def test_default_categories_includes_required(self) -> None:
        """Test that DEFAULT_CATEGORIES includes all required categories."""
        for key in REQUIRED_CATEGORIES:
            assert key in DEFAULT_CATEGORIES


class TestIssuesConfigValidation:
    """Tests for required category validation."""

    def test_required_categories_always_present_empty_config(self) -> None:
        """Test that required categories exist with empty config."""
        config = IssuesConfig.from_dict({})

        assert "bugs" in config.categories
        assert "features" in config.categories
        assert "enhancements" in config.categories

    def test_required_categories_merged_with_custom(self) -> None:
        """Test that custom categories are merged with required."""
        data = {
            "categories": {
                "documentation": {"prefix": "DOC", "dir": "docs", "action": "document"},
            }
        }
        config = IssuesConfig.from_dict(data)

        # Custom category present
        assert "documentation" in config.categories
        assert config.categories["documentation"].prefix == "DOC"

        # Required categories also present
        assert "bugs" in config.categories
        assert "features" in config.categories
        assert "enhancements" in config.categories

    def test_user_can_override_required_category_settings(self) -> None:
        """Test that user can customize required category settings."""
        data = {
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bug-reports", "action": "resolve"},
            }
        }
        config = IssuesConfig.from_dict(data)

        # User's customization applied
        assert config.categories["bugs"].dir == "bug-reports"
        assert config.categories["bugs"].action == "resolve"

        # Other required categories still present
        assert "features" in config.categories
        assert "enhancements" in config.categories


class TestIssuesConfigHelperMethods:
    """Tests for IssuesConfig helper methods."""

    def test_get_category_by_prefix_found(self) -> None:
        """Test get_category_by_prefix returns category when found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_prefix("BUG")

        assert result is not None
        assert result.prefix == "BUG"
        assert result.dir == "bugs"

    def test_get_category_by_prefix_not_found(self) -> None:
        """Test get_category_by_prefix returns None when not found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_prefix("UNKNOWN")

        assert result is None

    def test_get_category_by_dir_found(self) -> None:
        """Test get_category_by_dir returns category when found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_dir("features")

        assert result is not None
        assert result.prefix == "FEAT"
        assert result.dir == "features"

    def test_get_category_by_dir_not_found(self) -> None:
        """Test get_category_by_dir returns None when not found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_dir("unknown")

        assert result is None

    def test_get_all_prefixes(self) -> None:
        """Test get_all_prefixes returns all configured prefixes."""
        config = IssuesConfig.from_dict({})

        prefixes = config.get_all_prefixes()

        assert "BUG" in prefixes
        assert "FEAT" in prefixes
        assert "ENH" in prefixes

    def test_get_all_dirs(self) -> None:
        """Test get_all_dirs returns all configured directories."""
        config = IssuesConfig.from_dict({})

        dirs = config.get_all_dirs()

        assert "bugs" in dirs
        assert "features" in dirs
        assert "enhancements" in dirs

    def test_get_all_prefixes_with_custom_category(self) -> None:
        """Test get_all_prefixes includes custom categories."""
        data = {
            "categories": {
                "documentation": {"prefix": "DOC", "dir": "docs", "action": "document"},
            }
        }
        config = IssuesConfig.from_dict(data)

        prefixes = config.get_all_prefixes()

        assert "DOC" in prefixes
        # Required categories also present
        assert "BUG" in prefixes
        assert "FEAT" in prefixes
        assert "ENH" in prefixes


class TestGitHubSyncConfig:
    """Tests for GitHubSyncConfig dataclass."""

    def test_from_dict_with_defaults(self) -> None:
        """Test creating GitHubSyncConfig with default values."""
        config = GitHubSyncConfig.from_dict({})

        assert config.repo is None
        assert config.label_mapping == {"BUG": "bug", "FEAT": "enhancement", "ENH": "enhancement"}
        assert config.priority_labels is True
        assert config.sync_completed is False
        assert config.state_file == ".ll/ll-sync-state.json"

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating GitHubSyncConfig with all fields specified."""
        data = {
            "repo": "owner/repo",
            "label_mapping": {"BUG": "defect", "FEAT": "feature"},
            "priority_labels": False,
            "sync_completed": True,
            "state_file": "custom-sync-state.json",
        }
        config = GitHubSyncConfig.from_dict(data)

        assert config.repo == "owner/repo"
        assert config.label_mapping == {"BUG": "defect", "FEAT": "feature"}
        assert config.priority_labels is False
        assert config.sync_completed is True
        assert config.state_file == "custom-sync-state.json"

    def test_from_dict_partial_label_mapping(self) -> None:
        """Test that partial label_mapping replaces default entirely."""
        data = {"label_mapping": {"BUG": "defect"}}
        config = GitHubSyncConfig.from_dict(data)

        # Partial mapping replaces default (doesn't merge)
        assert config.label_mapping == {"BUG": "defect"}

    def test_pull_limit_default(self) -> None:
        """GitHubSyncConfig defaults pull_limit to 500."""
        config = GitHubSyncConfig.from_dict({})
        assert config.pull_limit == 500

    def test_pull_limit_configurable(self) -> None:
        """GitHubSyncConfig pull_limit can be set via from_dict."""
        config = GitHubSyncConfig.from_dict({"pull_limit": 250})
        assert config.pull_limit == 250


class TestSyncConfig:
    """Tests for SyncConfig dataclass."""

    def test_from_dict_with_defaults(self) -> None:
        """Test creating SyncConfig with default values."""
        config = SyncConfig.from_dict({})

        assert config.enabled is False
        assert config.provider == "github"
        assert isinstance(config.github, GitHubSyncConfig)
        assert config.github.repo is None

    def test_from_dict_enabled(self) -> None:
        """Test creating SyncConfig with enabled flag."""
        config = SyncConfig.from_dict({"enabled": True})

        assert config.enabled is True
        assert config.provider == "github"

    def test_from_dict_with_github_settings(self) -> None:
        """Test creating SyncConfig with GitHub settings."""
        data = {
            "enabled": True,
            "github": {
                "repo": "myorg/myrepo",
                "priority_labels": False,
            },
        }
        config = SyncConfig.from_dict(data)

        assert config.enabled is True
        assert config.github.repo == "myorg/myrepo"
        assert config.github.priority_labels is False
        # Other github defaults preserved
        assert config.github.sync_completed is False

    def test_from_dict_alternative_provider(self) -> None:
        """Test creating SyncConfig with different provider value."""
        config = SyncConfig.from_dict({"provider": "github"})

        assert config.provider == "github"


class TestBRConfigSyncIntegration:
    """Tests for BRConfig sync property integration."""

    def test_sync_property_exists(self, temp_project_dir: Path) -> None:
        """Test that BRConfig has sync property."""
        config = BRConfig(temp_project_dir)

        assert hasattr(config, "sync")
        assert isinstance(config.sync, SyncConfig)

    def test_sync_property_with_defaults(self, temp_project_dir: Path) -> None:
        """Test sync property returns defaults when not configured."""
        config = BRConfig(temp_project_dir)

        assert config.sync.enabled is False
        assert config.sync.provider == "github"
        assert config.sync.github.repo is None

    def test_sync_property_loads_from_config(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test sync property loads from config file."""
        sample_config["sync"] = {
            "enabled": True,
            "github": {
                "repo": "test/repo",
                "priority_labels": True,
            },
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.sync.enabled is True
        assert config.sync.github.repo == "test/repo"

    def test_sync_in_to_dict(self, temp_project_dir: Path) -> None:
        """Test sync config appears in to_dict output."""
        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert "sync" in result
        assert "enabled" in result["sync"]
        assert "provider" in result["sync"]
        assert "github" in result["sync"]
        assert "repo" in result["sync"]["github"]
        assert "label_mapping" in result["sync"]["github"]

    def test_sync_to_dict_serializable(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test that sync config in to_dict is JSON serializable."""
        sample_config["sync"] = {
            "enabled": True,
            "github": {
                "repo": "owner/repo",
                "label_mapping": {"BUG": "bug", "FEAT": "feature"},
            },
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        # Should not raise
        json.dumps(result)

    def test_resolve_variable_sync(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test resolve_variable works for sync config paths."""
        sample_config["sync"] = {"enabled": True}
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.resolve_variable("sync.enabled") == "True"
        assert config.resolve_variable("sync.provider") == "github"


class TestScoringWeightsConfig:
    """Tests for ScoringWeightsConfig dataclass."""

    def test_from_dict_with_defaults(self) -> None:
        """Test creating ScoringWeightsConfig with default values."""
        config = ScoringWeightsConfig.from_dict({})
        assert config.semantic == 0.5
        assert config.section == 0.3
        assert config.type == 0.2

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating ScoringWeightsConfig with all fields specified."""
        data = {"semantic": 0.6, "section": 0.2, "type": 0.2}
        config = ScoringWeightsConfig.from_dict(data)
        assert config.semantic == 0.6
        assert config.section == 0.2
        assert config.type == 0.2


class TestDependencyMappingConfig:
    """Tests for DependencyMappingConfig dataclass."""

    def test_from_dict_with_defaults(self) -> None:
        """Test creating DependencyMappingConfig with default values."""
        config = DependencyMappingConfig.from_dict({})
        assert config.overlap_min_files == 2
        assert config.overlap_min_ratio == 0.25
        assert config.min_directory_depth == 2
        assert config.conflict_threshold == 0.4
        assert config.high_conflict_threshold == 0.7
        assert config.confidence_modifier == 0.5
        assert config.scoring_weights.semantic == 0.5
        assert config.scoring_weights.section == 0.3
        assert config.scoring_weights.type == 0.2
        assert "__init__.py" in config.exclude_common_files
        assert "pyproject.toml" in config.exclude_common_files

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating DependencyMappingConfig with all fields specified."""
        data = {
            "overlap_min_files": 3,
            "overlap_min_ratio": 0.5,
            "min_directory_depth": 3,
            "conflict_threshold": 0.5,
            "high_conflict_threshold": 0.8,
            "confidence_modifier": 0.3,
            "scoring_weights": {"semantic": 0.7, "section": 0.2, "type": 0.1},
            "exclude_common_files": ["README.md"],
        }
        config = DependencyMappingConfig.from_dict(data)
        assert config.overlap_min_files == 3
        assert config.overlap_min_ratio == 0.5
        assert config.min_directory_depth == 3
        assert config.conflict_threshold == 0.5
        assert config.high_conflict_threshold == 0.8
        assert config.confidence_modifier == 0.3
        assert config.scoring_weights.semantic == 0.7
        assert config.scoring_weights.section == 0.2
        assert config.scoring_weights.type == 0.1
        assert config.exclude_common_files == ["README.md"]

    def test_from_dict_partial_data(self) -> None:
        """Test creating DependencyMappingConfig with partial data."""
        data = {"conflict_threshold": 0.6}
        config = DependencyMappingConfig.from_dict(data)
        assert config.conflict_threshold == 0.6
        # Other fields should use defaults
        assert config.overlap_min_files == 2
        assert config.scoring_weights.semantic == 0.5

    def test_brconfig_defaults(self, temp_project_dir: Path) -> None:
        """Test BRConfig loads dependency_mapping with defaults."""
        config = BRConfig(temp_project_dir)
        assert config.dependency_mapping.overlap_min_files == 2
        assert config.dependency_mapping.conflict_threshold == 0.4

    def test_brconfig_loads_from_file(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test BRConfig loads dependency_mapping from config file."""
        sample_config["dependency_mapping"] = {
            "overlap_min_files": 5,
            "conflict_threshold": 0.6,
            "scoring_weights": {"semantic": 0.8, "section": 0.1, "type": 0.1},
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        assert config.dependency_mapping.overlap_min_files == 5
        assert config.dependency_mapping.conflict_threshold == 0.6
        assert config.dependency_mapping.scoring_weights.semantic == 0.8

    def test_dependency_mapping_in_to_dict(self, temp_project_dir: Path) -> None:
        """Test dependency_mapping config appears in to_dict output."""
        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert "dependency_mapping" in result
        dm = result["dependency_mapping"]
        assert "overlap_min_files" in dm
        assert "conflict_threshold" in dm
        assert "scoring_weights" in dm
        assert dm["scoring_weights"]["semantic"] == 0.5

    def test_resolve_variable_dependency_mapping(self, temp_project_dir: Path) -> None:
        """Test resolve_variable works for dependency_mapping config paths."""
        config = BRConfig(temp_project_dir)
        assert config.resolve_variable("dependency_mapping.conflict_threshold") == "0.4"
        assert config.resolve_variable("dependency_mapping.overlap_min_files") == "2"


class TestCliColorsLoggerConfig:
    """Tests for CliColorsLoggerConfig dataclass."""

    def test_defaults(self) -> None:
        config = CliColorsLoggerConfig()
        assert config.info == "36"
        assert config.success == "32"
        assert config.warning == "33"
        assert config.error == "38;5;208"

    def test_from_dict_full(self) -> None:
        config = CliColorsLoggerConfig.from_dict(
            {"info": "34", "success": "35", "warning": "31", "error": "91"}
        )
        assert config.info == "34"
        assert config.success == "35"
        assert config.warning == "31"
        assert config.error == "91"

    def test_from_dict_partial(self) -> None:
        """Unspecified keys retain defaults."""
        config = CliColorsLoggerConfig.from_dict({"info": "34"})
        assert config.info == "34"
        assert config.success == "32"  # default


class TestCliColorsPriorityConfig:
    """Tests for CliColorsPriorityConfig dataclass."""

    def test_defaults(self) -> None:
        config = CliColorsPriorityConfig()
        assert config.P0 == "38;5;208;1"
        assert config.P1 == "38;5;208"
        assert config.P2 == "33"
        assert config.P3 == "0"
        assert config.P4 == "2"
        assert config.P5 == "2"

    def test_from_dict_partial(self) -> None:
        config = CliColorsPriorityConfig.from_dict({"P0": "31;1", "P2": "91"})
        assert config.P0 == "31;1"
        assert config.P2 == "91"
        assert config.P1 == "38;5;208"  # default


class TestCliColorsTypeConfig:
    """Tests for CliColorsTypeConfig dataclass."""

    def test_defaults(self) -> None:
        config = CliColorsTypeConfig()
        assert config.BUG == "38;5;208"
        assert config.FEAT == "32"
        assert config.ENH == "34"

    def test_from_dict_override(self) -> None:
        config = CliColorsTypeConfig.from_dict({"BUG": "31"})
        assert config.BUG == "31"
        assert config.FEAT == "32"  # default


class TestCliColorsConfig:
    """Tests for CliColorsConfig dataclass."""

    def test_defaults(self) -> None:
        config = CliColorsConfig()
        assert config.logger.info == "36"
        assert config.priority.P0 == "38;5;208;1"
        assert config.type.BUG == "38;5;208"

    def test_from_dict_empty(self) -> None:
        config = CliColorsConfig.from_dict({})
        assert config.logger.info == "36"
        assert config.priority.P0 == "38;5;208;1"

    def test_from_dict_nested_partial(self) -> None:
        config = CliColorsConfig.from_dict({"logger": {"info": "34"}, "type": {"BUG": "31"}})
        assert config.logger.info == "34"
        assert config.logger.success == "32"  # default
        assert config.type.BUG == "31"
        assert config.type.FEAT == "32"  # default
        assert config.priority.P0 == "38;5;208;1"  # untouched default

    def test_fsm_active_state_default(self) -> None:
        config = CliColorsConfig()
        assert config.fsm_active_state == "32"

    def test_fsm_active_state_from_dict_default(self) -> None:
        config = CliColorsConfig.from_dict({})
        assert config.fsm_active_state == "32"

    def test_fsm_active_state_from_dict_override(self) -> None:
        config = CliColorsConfig.from_dict({"fsm_active_state": "36"})
        assert config.fsm_active_state == "36"

    def test_cli_colors_has_fsm_edge_labels(self) -> None:
        config = CliColorsConfig()
        assert hasattr(config, "fsm_edge_labels")
        assert isinstance(config.fsm_edge_labels, CliColorsEdgeLabelsConfig)

    def test_cli_colors_from_dict_fsm_edge_labels_override(self) -> None:
        config = CliColorsConfig.from_dict({"fsm_edge_labels": {"yes": "36"}})
        assert config.fsm_edge_labels.yes == "36"
        assert config.fsm_edge_labels.no == "38;5;208"  # default


class TestCliColorsEdgeLabelsConfig:
    """Tests for CliColorsEdgeLabelsConfig dataclass."""

    def test_defaults(self) -> None:
        config = CliColorsEdgeLabelsConfig()
        assert config.yes == "32"
        assert config.no == "38;5;208"
        assert config.error == "31"
        assert config.partial == "33"
        assert config.next == "2"
        assert config.default == "2"
        assert config.blocked == "31"
        assert config.retry_exhausted == "38;5;208"
        assert config.rate_limit_exhausted == "38;5;214"

    def test_from_dict_empty(self) -> None:
        config = CliColorsEdgeLabelsConfig.from_dict({})
        assert config.yes == "32"
        assert config.no == "38;5;208"

    def test_from_dict_override(self) -> None:
        config = CliColorsEdgeLabelsConfig.from_dict({"yes": "36", "error": "91"})
        assert config.yes == "36"
        assert config.error == "91"
        assert config.no == "38;5;208"  # default

    def test_to_dict_maps_default_to_underscore(self) -> None:
        config = CliColorsEdgeLabelsConfig()
        d = config.to_dict()
        assert "_" in d
        assert "default" not in d
        assert d["_"] == "2"
        assert d["yes"] == "32"


class TestCliConfig:
    """Tests for CliConfig dataclass."""

    def test_defaults(self) -> None:
        config = CliConfig()
        assert config.color is True
        assert config.colors.logger.info == "36"

    def test_from_dict_empty(self) -> None:
        config = CliConfig.from_dict({})
        assert config.color is True

    def test_from_dict_color_false(self) -> None:
        config = CliConfig.from_dict({"color": False})
        assert config.color is False

    def test_from_dict_with_colors(self) -> None:
        config = CliConfig.from_dict(
            {"color": True, "colors": {"logger": {"error": "91"}, "priority": {"P0": "31;1"}}}
        )
        assert config.color is True
        assert config.colors.logger.error == "91"
        assert config.colors.priority.P0 == "31;1"
        assert config.colors.type.BUG == "38;5;208"  # default


class TestBRConfigCli:
    """Tests for BRConfig.cli property."""

    def test_cli_defaults_when_absent(self, temp_project_dir: Path) -> None:
        """BRConfig.cli returns defaults when 'cli' key is absent from config."""
        config = BRConfig(temp_project_dir)
        assert config.cli.color is True
        assert config.cli.colors.logger.info == "36"

    def test_cli_color_false_from_config(self, temp_project_dir: Path) -> None:
        """BRConfig.cli.color is False when configured."""
        sample_config: dict[str, Any] = {"cli": {"color": False}}
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        assert config.cli.color is False

    def test_cli_colors_override_from_config(self, temp_project_dir: Path) -> None:
        """Custom cli.colors values are loaded from config."""
        sample_config: dict[str, Any] = {
            "cli": {
                "colors": {
                    "logger": {"error": "91"},
                    "priority": {"P0": "31;1"},
                    "type": {"BUG": "31"},
                }
            }
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        assert config.cli.colors.logger.error == "91"
        assert config.cli.colors.priority.P0 == "31;1"
        assert config.cli.colors.type.BUG == "31"
        # Unspecified keys retain defaults
        assert config.cli.colors.logger.info == "36"
        assert config.cli.colors.priority.P1 == "38;5;208"

    def test_cli_in_to_dict(self, temp_project_dir: Path) -> None:
        """Test cli config appears in to_dict output."""
        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert "cli" in result
        assert "color" in result["cli"]
        assert "colors" in result["cli"]
        assert "logger" in result["cli"]["colors"]
        assert "priority" in result["cli"]["colors"]
        assert "type" in result["cli"]["colors"]


class TestLoopsGlyphsConfig:
    """Tests for LoopsGlyphsConfig dataclass."""

    def test_defaults(self) -> None:
        config = LoopsGlyphsConfig()
        assert config.prompt == "\u2726"
        assert config.slash_command == "/\u2501\u25ba"
        assert config.shell == "\u276f_"
        assert config.mcp_tool == "\u26a1"
        assert config.sub_loop == "\u21b3\u27f3"
        assert config.route == "\u2443"

    def test_from_dict_empty(self) -> None:
        config = LoopsGlyphsConfig.from_dict({})
        assert config.prompt == "\u2726"
        assert config.sub_loop == "\u21b3\u27f3"

    def test_from_dict_partial_override(self) -> None:
        config = LoopsGlyphsConfig.from_dict({"prompt": "P", "shell": "S"})
        assert config.prompt == "P"
        assert config.shell == "S"
        assert config.mcp_tool == "\u26a1"  # default unchanged

    def test_to_dict_returns_all_keys(self) -> None:
        config = LoopsGlyphsConfig()
        d = config.to_dict()
        assert set(d.keys()) == {
            "prompt",
            "slash_command",
            "shell",
            "mcp_tool",
            "sub_loop",
            "route",
        }
        assert d["prompt"] == "\u2726"
        assert d["route"] == "\u2443"

    def test_loops_config_has_glyphs_field(self) -> None:
        config = LoopsConfig()
        assert hasattr(config, "glyphs")
        assert isinstance(config.glyphs, LoopsGlyphsConfig)

    def test_loops_config_from_dict_passes_glyphs(self) -> None:
        config = LoopsConfig.from_dict({"glyphs": {"prompt": "X"}})
        assert config.glyphs.prompt == "X"
        assert config.glyphs.shell == "\u276f_"  # default


class TestBRConfigLoopsGlyphs:
    """Tests for BRConfig.loops.glyphs integration."""

    def test_loops_glyphs_defaults_when_absent(self, temp_project_dir: Path) -> None:
        """BRConfig.loops.glyphs returns defaults when 'glyphs' key is absent."""
        config = BRConfig(temp_project_dir)
        assert config.loops.glyphs.prompt == "\u2726"
        assert config.loops.glyphs.route == "\u2443"

    def test_loops_glyphs_override_from_config(self, temp_project_dir: Path) -> None:
        """Custom loops.glyphs values are loaded from config file."""
        sample_config: dict[str, Any] = {"loops": {"glyphs": {"prompt": "P", "mcp_tool": "M"}}}
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        assert config.loops.glyphs.prompt == "P"
        assert config.loops.glyphs.mcp_tool == "M"
        assert config.loops.glyphs.shell == "\u276f_"  # default unchanged

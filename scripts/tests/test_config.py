"""Tests for little_loops.config module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.config import (
    DEFAULT_CATEGORIES,
    REQUIRED_CATEGORIES,
    AutomationConfig,
    BRConfig,
    CaptureIssueConfig,
    CategoryConfig,
    CliColorsConfig,
    CliColorsEdgeLabelsConfig,
    CliColorsLoggerConfig,
    CliColorsPriorityConfig,
    CliColorsTypeConfig,
    CliConfig,
    ClusterConfig,
    CodeQueryCodegraphConfig,
    CodeQueryConfig,
    CommandsConfig,
    CompactionConfig,
    ComposerAdaptiveConfig,
    ComposerConfig,
    ConfidenceGateConfig,
    DecisionsConfig,
    DependencyMappingConfig,
    DesignTokensConfig,
    DuplicateDetectionConfig,
    EpicBranchesConfig,
    EventsConfig,
    EvolutionConfig,
    GitHubSyncConfig,
    GoNoGoConfig,
    HistoryConfig,
    IssuesConfig,
    LearningTestsConfig,
    LoopsConfig,
    LoopsGlyphsConfig,
    NextIssueConfig,
    OrchestrationConfig,
    OTelEventsConfig,
    ParallelAutomationConfig,
    PreCompactRubricConfig,
    ProjectConfig,
    RateLimitsConfig,
    RecursiveRefineConfig,
    ScanConfig,
    ScoringWeightsConfig,
    SessionDigestConfig,
    SocketEventsConfig,
    SprintsConfig,
    SyncConfig,
    WebhookEventsConfig,
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
            "health_url": "http://localhost:8080/health",
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
        assert config.health_url == "http://localhost:8080/health"

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
        assert config.health_url is None


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
        # User specified bugs, required categories (features, enhancements, epics) are auto-added
        assert len(config.categories) == 4
        assert config.categories["bugs"].prefix == "BUG"
        assert "features" in config.categories
        assert "enhancements" in config.categories
        assert "epics" in config.categories
        assert config.completed_dir == "done"
        assert config.deferred_dir == "deferred"  # default when not specified
        assert config.priorities == ["P0", "P1"]
        assert config.templates_dir == "templates/"
        assert config.capture_template == "minimal"
        assert config.auto_commit is False
        assert config.auto_commit_prefix == "chore(issues)"

    def test_from_dict_with_auto_commit(self) -> None:
        """Test creating IssuesConfig with explicit auto_commit values."""
        config = IssuesConfig.from_dict({"auto_commit": True, "auto_commit_prefix": "fix(issues)"})
        assert config.auto_commit is True
        assert config.auto_commit_prefix == "fix(issues)"

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
        assert len(config.categories) == 4  # bugs, features, enhancements, epics
        assert "bugs" in config.categories
        assert "features" in config.categories
        assert "enhancements" in config.categories
        assert "epics" in config.categories
        assert config.completed_dir == "completed"
        assert config.deferred_dir == "deferred"
        assert config.priorities == ["P0", "P1", "P2", "P3", "P4", "P5"]
        assert config.templates_dir is None
        assert config.capture_template == "full"
        assert config.duplicate_detection.exact_threshold == 0.8
        assert config.duplicate_detection.similar_threshold == 0.5
        assert config.next_issue.strategy == "confidence_first"
        assert config.next_issue.sort_keys is None
        assert config.auto_commit is False
        assert config.auto_commit_prefix == "chore(issues)"


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


class TestNextIssueConfig:
    """Tests for NextIssueConfig dataclass (selection strategy for ll-issues next-issue)."""

    def test_defaults(self) -> None:
        """Default strategy is confidence_first; sort_keys is None."""
        config = NextIssueConfig()
        assert config.strategy == "confidence_first"
        assert config.sort_keys is None

    def test_from_dict_with_strategy(self) -> None:
        """from_dict accepts a named strategy and leaves sort_keys as None."""
        config = NextIssueConfig.from_dict({"strategy": "priority_first"})
        assert config.strategy == "priority_first"
        assert config.sort_keys is None

    def test_from_dict_with_empty_dict(self) -> None:
        """Empty dict yields defaults."""
        config = NextIssueConfig.from_dict({})
        assert config.strategy == "confidence_first"
        assert config.sort_keys is None

    def test_unknown_strategy_raises(self) -> None:
        """Unknown strategy raises ValueError (locks in validating-from_dict convention)."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            NextIssueConfig.from_dict({"strategy": "bogus"})

    def test_unknown_sort_key_raises(self) -> None:
        """Unknown sort key raises ValueError."""
        with pytest.raises(ValueError, match="Unknown sort key"):
            NextIssueConfig.from_dict({"sort_keys": [{"key": "nonexistent", "direction": "asc"}]})

    def test_issues_config_parses_next_issue(self) -> None:
        """IssuesConfig.from_dict reads the next_issue block."""
        config = IssuesConfig.from_dict({"next_issue": {"strategy": "priority_first"}})
        assert config.next_issue.strategy == "priority_first"
        assert config.next_issue.sort_keys is None


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

    # EpicBranchesConfig integration (FEAT-2447)
    def test_epic_branches_defaults(self) -> None:
        """EpicBranchesConfig defaults to all-False / epic/ prefix."""
        config = ParallelAutomationConfig.from_dict({})
        assert config.epic_branches.enabled is False
        assert config.epic_branches.prefix == "epic/"
        assert config.epic_branches.merge_to_base_on_complete is True
        assert config.epic_branches.open_pr is False
        assert config.epic_branches.verify_before_merge is False

    def test_epic_branches_from_dict(self) -> None:
        """EpicBranchesConfig parses all 5 sub-keys from data."""
        data = {
            "epic_branches": {
                "enabled": True,
                "prefix": "epic-/",
                "merge_to_base_on_complete": False,
                "open_pr": True,
                "verify_before_merge": True,
            }
        }
        config = ParallelAutomationConfig.from_dict(data)
        assert config.epic_branches.enabled is True
        assert config.epic_branches.prefix == "epic-/"
        assert config.epic_branches.merge_to_base_on_complete is False
        assert config.epic_branches.open_pr is True
        assert config.epic_branches.verify_before_merge is True

    def test_epic_branches_partial_dict_uses_defaults(self) -> None:
        """Partial EpicBranchesConfig dict fills missing keys with defaults."""
        config = ParallelAutomationConfig.from_dict({"epic_branches": {"enabled": True}})
        assert config.epic_branches.enabled is True
        assert config.epic_branches.prefix == "epic/"
        assert config.epic_branches.merge_to_base_on_complete is True
        assert config.epic_branches.open_pr is False
        assert config.epic_branches.verify_before_merge is False


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


class TestRecursiveRefineConfig:
    """Tests for RecursiveRefineConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating RecursiveRefineConfig with all schema-aligned fields."""
        config = RecursiveRefineConfig.from_dict({"max_depth": 5})
        assert config.max_depth == 5

    def test_from_dict_with_defaults(self) -> None:
        """Test creating RecursiveRefineConfig with default values."""
        config = RecursiveRefineConfig.from_dict({})
        assert config.max_depth == 3


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
            "recursive_refine": {"max_depth": 5},
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
        assert config.recursive_refine.max_depth == 5

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
        assert config.recursive_refine.max_depth == 3


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
            "max_issue_wall_clock_time": 1800,
        }
        config = SprintsConfig.from_dict(data)

        assert config.sprints_dir == "custom-sprints/"
        assert config.default_timeout == 7200
        assert config.default_max_workers == 8
        assert config.max_issue_wall_clock_time == 1800

    def test_from_dict_with_defaults(self) -> None:
        """Test creating SprintsConfig with default values."""
        config = SprintsConfig.from_dict({})

        assert config.sprints_dir == ".sprints"
        assert config.default_timeout == 3600
        assert config.default_max_workers == 2
        assert config.max_issue_wall_clock_time == 2700


class TestLoopsConfig:
    """Tests for LoopsConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating LoopsConfig with all fields."""
        data = {
            "loops_dir": "custom-loops/",
            "queue_wait_timeout_seconds": 7200,
        }
        config = LoopsConfig.from_dict(data)

        assert config.loops_dir == "custom-loops/"
        assert config.queue_wait_timeout_seconds == 7200

    def test_from_dict_with_defaults(self) -> None:
        """Test creating LoopsConfig with default values."""
        config = LoopsConfig.from_dict({})

        assert config.loops_dir == ".loops"
        assert config.queue_wait_timeout_seconds == 86400


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
        assert len(config.issues.categories) == 4

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
        assert "queue_wait_timeout_seconds" in result["loops"]
        assert "events" in result
        assert "decisions" in result

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

        # EpicBranchesConfig sub-block (FEAT-2447)
        assert "epic_branches" in parallel
        assert parallel["epic_branches"]["enabled"] is False
        assert parallel["epic_branches"]["prefix"] == "epic/"
        assert parallel["epic_branches"]["merge_to_base_on_complete"] is True
        assert parallel["epic_branches"]["open_pr"] is False
        assert parallel["epic_branches"]["verify_before_merge"] is False

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

    def test_commands_recursive_refine_in_to_dict(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test to_dict exports commands.recursive_refine.max_depth."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert "recursive_refine" in result["commands"]
        assert result["commands"]["recursive_refine"]["max_depth"] == 3

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

    def test_create_parallel_config_feature_branches_explicit_true(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """--feature-branches forces True regardless of config value."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        # Config has use_feature_branches=True; explicit True should still be True
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)
        result = config.create_parallel_config(use_feature_branches=True)
        assert result.use_feature_branches is True

    def test_create_parallel_config_feature_branches_explicit_false(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """--no-feature-branches forces False even when config has True."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        # Config has use_feature_branches=True; explicit False must override it
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)
        result = config.create_parallel_config(use_feature_branches=False)
        assert result.use_feature_branches is False

    def test_create_parallel_config_feature_branches_none_falls_back_to_config_true(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Omitting the flag falls back to config value (True case)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)
        result = config.create_parallel_config()
        assert result.use_feature_branches is True

    def test_create_parallel_config_feature_branches_none_falls_back_to_config_false(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Omitting the flag falls back to config value (False case)."""
        cfg = dict(sample_config)
        cfg["parallel"] = dict(sample_config["parallel"], use_feature_branches=False)
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(cfg))
        config = BRConfig(temp_project_dir)
        result = config.create_parallel_config()
        assert result.use_feature_branches is False

    # EpicBranchesConfig passthrough (FEAT-2447)
    def test_create_parallel_config_epic_branches_explicit_true(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Explicit epic_branches kwarg overrides config value."""
        cfg = dict(sample_config)
        cfg["parallel"] = dict(
            sample_config["parallel"],
            epic_branches={"enabled": False, "prefix": "epic/"},
        )
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(cfg))
        config = BRConfig(temp_project_dir)
        result = config.create_parallel_config(epic_branches=EpicBranchesConfig(enabled=True))
        assert result.epic_branches.enabled is True

    def test_create_parallel_config_epic_branches_explicit_false(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Explicit epic_branches=False overrides config's True."""
        cfg = dict(sample_config)
        cfg["parallel"] = dict(
            sample_config["parallel"],
            epic_branches={"enabled": True, "prefix": "epic/"},
        )
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(cfg))
        config = BRConfig(temp_project_dir)
        result = config.create_parallel_config(epic_branches=EpicBranchesConfig(enabled=False))
        assert result.epic_branches.enabled is False

    def test_create_parallel_config_epic_branches_none_falls_back_to_config(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Omitting epic_branches kwarg falls back to config value."""
        cfg = dict(sample_config)
        cfg["parallel"] = dict(
            sample_config["parallel"],
            epic_branches={
                "enabled": True,
                "prefix": "fe/",
                "merge_to_base_on_complete": False,
                "open_pr": True,
                "verify_before_merge": True,
            },
        )
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(cfg))
        config = BRConfig(temp_project_dir)
        result = config.create_parallel_config()
        assert result.epic_branches.enabled is True
        assert result.epic_branches.prefix == "fe/"
        assert result.epic_branches.merge_to_base_on_complete is False
        assert result.epic_branches.open_pr is True
        assert result.epic_branches.verify_before_merge is True

    def test_to_dict_excludes_deprecated_dirs(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """BRConfig.to_dict() issues section must not contain completed_dir or deferred_dir."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        config_dict = config.to_dict()

        issues_section = config_dict.get("issues", {})
        assert "completed_dir" not in issues_section
        assert "deferred_dir" not in issues_section

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


class TestResolveConfigPath:
    """Tests for resolve_config_path (Python port of bash ll_resolve_config — FEAT-1454)."""

    def test_prefers_ll_dir_config(self, tmp_path: Path) -> None:
        """``.ll/ll-config.json`` is returned when present (preferred over root-level)."""
        from little_loops.config.core import resolve_config_path

        (tmp_path / ".ll").mkdir(exist_ok=True)
        ll_dir_cfg = tmp_path / ".ll" / "ll-config.json"
        ll_dir_cfg.write_text('{"a": 1}')
        # Also write a root-level one to confirm the .ll/ dir wins.
        (tmp_path / "ll-config.json").write_text('{"b": 2}')

        assert resolve_config_path(tmp_path) == ll_dir_cfg

    def test_falls_back_to_root_level(self, tmp_path: Path) -> None:
        """When ``.ll/ll-config.json`` is absent, root-level ``ll-config.json`` is returned."""
        from little_loops.config.core import resolve_config_path

        root_cfg = tmp_path / "ll-config.json"
        root_cfg.write_text('{"b": 2}')

        assert resolve_config_path(tmp_path) == root_cfg

    def test_returns_none_when_both_absent(self, tmp_path: Path) -> None:
        """Neither candidate present → ``None``."""
        from little_loops.config.core import resolve_config_path

        assert resolve_config_path(tmp_path) is None

    def test_pure_lookup_no_mkdir(self, tmp_path: Path) -> None:
        """Lookup does NOT create ``.ll/`` (vs. bash version's ``mkdir -p .ll`` side effect)."""
        from little_loops.config.core import resolve_config_path

        # Use a fresh sub-directory isolated from the test fixture's tmp_path/.ll/
        probe = tmp_path / "probe"
        probe.mkdir()
        resolve_config_path(probe)
        assert not (probe / ".ll").exists()

    def test_brconfig_picks_up_root_level_fallback(self, tmp_path: Path) -> None:
        """``BRConfig._load_config`` now reads root-level ``ll-config.json`` via resolve_config_path."""
        (tmp_path / "ll-config.json").write_text(
            json.dumps({"project": {"name": "from-root", "src_dir": "lib/"}})
        )
        config = BRConfig(tmp_path)
        assert config.project.name == "from-root"
        assert config.project.src_dir == "lib/"

    def test_codex_path_ignored_without_host_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``.codex/ll-config.json`` is NOT probed when no host env var is set (default order preserved)."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.delenv("LL_HOOK_HOST", raising=False)
        monkeypatch.delenv("LL_STATE_DIR", raising=False)
        (tmp_path / ".codex").mkdir()
        codex_cfg = tmp_path / ".codex" / "ll-config.json"
        codex_cfg.write_text('{"codex": true}')
        (tmp_path / ".ll").mkdir(exist_ok=True)
        ll_cfg = tmp_path / ".ll" / "ll-config.json"
        ll_cfg.write_text('{"ll": true}')

        # `.ll/` wins because no LL_HOOK_HOST/LL_STATE_DIR is set.
        assert resolve_config_path(tmp_path) == ll_cfg

    def test_codex_path_takes_precedence_when_host_codex(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``LL_HOOK_HOST=codex`` puts ``.codex/ll-config.json`` ahead of ``.ll/`` and root-level (FEAT-957)."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.setenv("LL_HOOK_HOST", "codex")
        monkeypatch.delenv("LL_STATE_DIR", raising=False)
        (tmp_path / ".codex").mkdir()
        codex_cfg = tmp_path / ".codex" / "ll-config.json"
        codex_cfg.write_text('{"codex": true}')
        (tmp_path / ".ll").mkdir(exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text('{"ll": true}')
        (tmp_path / "ll-config.json").write_text('{"root": true}')

        assert resolve_config_path(tmp_path) == codex_cfg

    def test_codex_path_takes_precedence_when_state_dir_codex(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``LL_STATE_DIR=.codex`` is an alternate trigger for the codex probe order (FEAT-957)."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.delenv("LL_HOOK_HOST", raising=False)
        monkeypatch.setenv("LL_STATE_DIR", ".codex")
        (tmp_path / ".codex").mkdir()
        codex_cfg = tmp_path / ".codex" / "ll-config.json"
        codex_cfg.write_text('{"codex": true}')
        (tmp_path / ".ll").mkdir(exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text('{"ll": true}')

        assert resolve_config_path(tmp_path) == codex_cfg

    def test_codex_host_falls_through_to_ll_dir_when_codex_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex host with no ``.codex/ll-config.json`` falls back to ``.ll/`` then root-level."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.setenv("LL_HOOK_HOST", "codex")
        # No .codex/ll-config.json exists.
        (tmp_path / ".ll").mkdir(exist_ok=True)
        ll_cfg = tmp_path / ".ll" / "ll-config.json"
        ll_cfg.write_text('{"ll": true}')

        assert resolve_config_path(tmp_path) == ll_cfg

    def test_opencode_host_uses_default_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``LL_HOOK_HOST=opencode`` does not change probe order — only ``codex`` does (FEAT-957)."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.setenv("LL_HOOK_HOST", "opencode")
        (tmp_path / ".codex").mkdir()
        (tmp_path / ".codex" / "ll-config.json").write_text('{"codex": true}')
        (tmp_path / ".ll").mkdir(exist_ok=True)
        ll_cfg = tmp_path / ".ll" / "ll-config.json"
        ll_cfg.write_text('{"ll": true}')

        # `.ll/` still wins under opencode host — codex probe only triggers for codex.
        assert resolve_config_path(tmp_path) == ll_cfg

    def test_gemini_path_takes_precedence_when_host_gemini(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``LL_HOOK_HOST=gemini`` puts ``.gemini/ll-config.json`` ahead of ``.ll/`` (ENH-2187)."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.setenv("LL_HOOK_HOST", "gemini")
        monkeypatch.delenv("LL_STATE_DIR", raising=False)
        (tmp_path / ".gemini").mkdir()
        gemini_cfg = tmp_path / ".gemini" / "ll-config.json"
        gemini_cfg.write_text('{"gemini": true}')
        (tmp_path / ".ll").mkdir(exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text('{"ll": true}')
        (tmp_path / "ll-config.json").write_text('{"root": true}')

        assert resolve_config_path(tmp_path) == gemini_cfg

    def test_gemini_path_takes_precedence_when_state_dir_gemini(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``LL_STATE_DIR=.gemini`` is an alternate trigger for the gemini probe (ENH-2187)."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.delenv("LL_HOOK_HOST", raising=False)
        monkeypatch.setenv("LL_STATE_DIR", ".gemini")
        (tmp_path / ".gemini").mkdir()
        gemini_cfg = tmp_path / ".gemini" / "ll-config.json"
        gemini_cfg.write_text('{"gemini": true}')
        (tmp_path / ".ll").mkdir(exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text('{"ll": true}')

        assert resolve_config_path(tmp_path) == gemini_cfg

    def test_gemini_path_ignored_without_host_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``.gemini/ll-config.json`` is NOT probed when no gemini env trigger is set."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.delenv("LL_HOOK_HOST", raising=False)
        monkeypatch.delenv("LL_STATE_DIR", raising=False)
        (tmp_path / ".gemini").mkdir()
        (tmp_path / ".gemini" / "ll-config.json").write_text('{"gemini": true}')
        (tmp_path / ".ll").mkdir(exist_ok=True)
        ll_cfg = tmp_path / ".ll" / "ll-config.json"
        ll_cfg.write_text('{"ll": true}')

        assert resolve_config_path(tmp_path) == ll_cfg

    def test_gemini_host_falls_through_to_ll_dir_when_gemini_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gemini host with no ``.gemini/ll-config.json`` falls back to ``.ll/``."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.setenv("LL_HOOK_HOST", "gemini")
        (tmp_path / ".ll").mkdir(exist_ok=True)
        ll_cfg = tmp_path / ".ll" / "ll-config.json"
        ll_cfg.write_text('{"ll": true}')

        assert resolve_config_path(tmp_path) == ll_cfg

    def test_omp_path_takes_precedence_when_host_omp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``LL_HOOK_HOST=omp`` puts ``.omp/ll-config.json`` ahead of ``.ll/`` (FEAT-2262)."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.setenv("LL_HOOK_HOST", "omp")
        monkeypatch.delenv("LL_STATE_DIR", raising=False)
        (tmp_path / ".omp").mkdir()
        omp_cfg = tmp_path / ".omp" / "ll-config.json"
        omp_cfg.write_text('{"omp": true}')
        (tmp_path / ".ll").mkdir(exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text('{"ll": true}')
        (tmp_path / "ll-config.json").write_text('{"root": true}')

        assert resolve_config_path(tmp_path) == omp_cfg

    def test_omp_path_takes_precedence_when_state_dir_omp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``LL_STATE_DIR=.omp`` is an alternate trigger for the omp probe (FEAT-2262)."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.delenv("LL_HOOK_HOST", raising=False)
        monkeypatch.setenv("LL_STATE_DIR", ".omp")
        (tmp_path / ".omp").mkdir()
        omp_cfg = tmp_path / ".omp" / "ll-config.json"
        omp_cfg.write_text('{"omp": true}')
        (tmp_path / ".ll").mkdir(exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text('{"ll": true}')

        assert resolve_config_path(tmp_path) == omp_cfg

    def test_omp_path_ignored_without_host_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``.omp/ll-config.json`` is NOT probed when no omp env trigger is set."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.delenv("LL_HOOK_HOST", raising=False)
        monkeypatch.delenv("LL_STATE_DIR", raising=False)
        (tmp_path / ".omp").mkdir()
        (tmp_path / ".omp" / "ll-config.json").write_text('{"omp": true}')
        (tmp_path / ".ll").mkdir(exist_ok=True)
        ll_cfg = tmp_path / ".ll" / "ll-config.json"
        ll_cfg.write_text('{"ll": true}')

        assert resolve_config_path(tmp_path) == ll_cfg

    def test_omp_host_falls_through_to_ll_dir_when_omp_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """omp host with no ``.omp/ll-config.json`` falls back to ``.ll/``."""
        from little_loops.config.core import resolve_config_path

        monkeypatch.setenv("LL_HOOK_HOST", "omp")
        (tmp_path / ".ll").mkdir(exist_ok=True)
        ll_cfg = tmp_path / ".ll" / "ll-config.json"
        ll_cfg.write_text('{"ll": true}')

        assert resolve_config_path(tmp_path) == ll_cfg


class TestFeatureEnabledHelper:
    """Tests for feature_enabled (Python port of bash ll_feature_enabled — FEAT-1454)."""

    def test_truthy_dot_path_returns_true(self) -> None:
        from little_loops.config.features import feature_enabled

        assert feature_enabled({"context_monitor": {"enabled": True}}, "context_monitor.enabled")

    def test_falsy_dot_path_returns_false(self) -> None:
        from little_loops.config.features import feature_enabled

        assert not feature_enabled(
            {"context_monitor": {"enabled": False}}, "context_monitor.enabled"
        )

    def test_missing_top_level_key_returns_false(self) -> None:
        from little_loops.config.features import feature_enabled

        assert not feature_enabled({}, "sync.enabled")

    def test_missing_nested_key_returns_false(self) -> None:
        from little_loops.config.features import feature_enabled

        assert not feature_enabled({"sync": {}}, "sync.enabled")

    def test_non_dict_intermediate_returns_false(self) -> None:
        """``feature_enabled`` doesn't traverse into non-dict values (jq returns null/false)."""
        from little_loops.config.features import feature_enabled

        assert not feature_enabled({"sync": "not a dict"}, "sync.enabled")

    def test_truthy_non_bool_value(self) -> None:
        """Non-empty strings / non-zero numbers coerce to True (parity with jq's // false)."""
        from little_loops.config.features import feature_enabled

        assert feature_enabled({"a": {"b": "yes"}}, "a.b")
        assert feature_enabled({"a": {"b": 1}}, "a.b")

    def test_falsy_non_bool_value(self) -> None:
        from little_loops.config.features import feature_enabled

        assert not feature_enabled({"a": {"b": 0}}, "a.b")
        assert not feature_enabled({"a": {"b": ""}}, "a.b")
        assert not feature_enabled({"a": {"b": None}}, "a.b")


class TestFeatureEnabledForHelper:
    """Tests for feature_enabled_for (ENH-1840 — glob-matching variant of feature_enabled)."""

    def test_wildcard_matches_any_subject(self) -> None:
        from little_loops.config.features import feature_enabled_for

        cfg = {"analytics": {"capture": {"skills": ["*"]}}}
        assert feature_enabled_for(cfg, "analytics.capture.skills", "my-skill")
        assert feature_enabled_for(cfg, "analytics.capture.skills", "other-skill")

    def test_exact_pattern_matches_only_exact_subject(self) -> None:
        from little_loops.config.features import feature_enabled_for

        cfg = {"analytics": {"capture": {"skills": ["Read"]}}}
        assert feature_enabled_for(cfg, "analytics.capture.skills", "Read")
        assert not feature_enabled_for(cfg, "analytics.capture.skills", "Write")

    def test_list_of_patterns_matches_any(self) -> None:
        from little_loops.config.features import feature_enabled_for

        cfg = {"analytics": {"capture": {"skills": ["Read", "Write"]}}}
        assert feature_enabled_for(cfg, "analytics.capture.skills", "Read")
        assert feature_enabled_for(cfg, "analytics.capture.skills", "Write")
        assert not feature_enabled_for(cfg, "analytics.capture.skills", "Edit")

    def test_empty_list_returns_default(self) -> None:
        from little_loops.config.features import feature_enabled_for

        cfg = {"analytics": {"capture": {"skills": []}}}
        assert feature_enabled_for(cfg, "analytics.capture.skills", "any") is True
        assert feature_enabled_for(cfg, "analytics.capture.skills", "any", default=False) is False

    def test_absent_key_returns_default(self) -> None:
        from little_loops.config.features import feature_enabled_for

        assert feature_enabled_for({}, "analytics.capture.skills", "any") is True
        assert feature_enabled_for({}, "analytics.capture.skills", "any", default=False) is False

    def test_none_value_treated_as_match_all(self) -> None:
        from little_loops.config.features import feature_enabled_for

        cfg = {"analytics": {"capture": {"skills": None}}}
        assert feature_enabled_for(cfg, "analytics.capture.skills", "anything")

    def test_bare_string_value_normalised_to_list(self) -> None:
        from little_loops.config.features import feature_enabled_for

        cfg = {"analytics": {"capture": {"skills": "Read"}}}
        assert feature_enabled_for(cfg, "analytics.capture.skills", "Read")
        assert not feature_enabled_for(cfg, "analytics.capture.skills", "Write")

    def test_glob_pattern_matching(self) -> None:
        from little_loops.config.features import feature_enabled_for

        cfg = {"analytics": {"capture": {"skills": ["ll:*"]}}}
        assert feature_enabled_for(cfg, "analytics.capture.skills", "ll:commit")
        assert not feature_enabled_for(cfg, "analytics.capture.skills", "commit")


class TestAnalyticsCaptureConfig:
    """Tests for AnalyticsCaptureConfig dataclass (ENH-1840)."""

    def test_defaults_when_empty_dict(self) -> None:
        from little_loops.config.features import AnalyticsCaptureConfig

        cfg = AnalyticsCaptureConfig.from_dict({})
        assert cfg.skills == ["*"]
        assert cfg.cli_commands == ["*"]
        assert cfg.corrections is True
        assert cfg.file_events is True
        assert cfg.correction_patterns == []

    def test_skills_override(self) -> None:
        from little_loops.config.features import AnalyticsCaptureConfig

        cfg = AnalyticsCaptureConfig.from_dict({"skills": ["ll:commit", "ll:open-pr"]})
        assert cfg.skills == ["ll:commit", "ll:open-pr"]
        assert cfg.cli_commands == ["*"]

    def test_cli_commands_override(self) -> None:
        from little_loops.config.features import AnalyticsCaptureConfig

        cfg = AnalyticsCaptureConfig.from_dict({"cli_commands": ["ll-auto"]})
        assert cfg.cli_commands == ["ll-auto"]
        assert cfg.skills == ["*"]

    def test_corrections_false(self) -> None:
        from little_loops.config.features import AnalyticsCaptureConfig

        cfg = AnalyticsCaptureConfig.from_dict({"corrections": False})
        assert cfg.corrections is False

    def test_file_events_false(self) -> None:
        from little_loops.config.features import AnalyticsCaptureConfig

        cfg = AnalyticsCaptureConfig.from_dict({"file_events": False})
        assert cfg.file_events is False

    def test_correction_patterns_default(self) -> None:
        from little_loops.config.features import AnalyticsCaptureConfig

        cfg = AnalyticsCaptureConfig.from_dict({})
        assert cfg.correction_patterns == []

    def test_correction_patterns_set(self) -> None:
        from little_loops.config.features import AnalyticsCaptureConfig

        cfg = AnalyticsCaptureConfig.from_dict({"correction_patterns": ["not quite", "try again"]})
        assert cfg.correction_patterns == ["not quite", "try again"]

    def test_correction_patterns_malformed_non_list(self) -> None:
        from little_loops.config.features import AnalyticsCaptureConfig

        cfg = AnalyticsCaptureConfig.from_dict({"correction_patterns": "not quite"})
        assert cfg.correction_patterns == []

    def test_correction_patterns_malformed_mixed(self) -> None:
        from little_loops.config.features import AnalyticsCaptureConfig

        cfg = AnalyticsCaptureConfig.from_dict(
            {"correction_patterns": ["valid", 42, None, "also valid"]}
        )
        assert cfg.correction_patterns == ["valid", "also valid"]


class TestBRConfigAliases:
    """Tests for backwards compatibility aliases."""

    def test_clconfig_alias(self) -> None:
        """Test CLConfig is an alias for BRConfig."""
        from little_loops.config import CLConfig

        assert CLConfig is BRConfig


class TestCategoryConstants:
    """Tests for REQUIRED_CATEGORIES and DEFAULT_CATEGORIES constants."""

    def test_required_categories_contains_core_types(self) -> None:
        """Test that REQUIRED_CATEGORIES has bugs, features, enhancements, and epics."""
        assert "bugs" in REQUIRED_CATEGORIES
        assert "features" in REQUIRED_CATEGORIES
        assert "enhancements" in REQUIRED_CATEGORIES
        assert "epics" in REQUIRED_CATEGORIES
        assert REQUIRED_CATEGORIES["bugs"]["prefix"] == "BUG"
        assert REQUIRED_CATEGORIES["features"]["prefix"] == "FEAT"
        assert REQUIRED_CATEGORIES["enhancements"]["prefix"] == "ENH"
        assert REQUIRED_CATEGORIES["epics"]["prefix"] == "EPIC"
        assert REQUIRED_CATEGORIES["epics"]["action"] == "coordinate"

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
        assert "epics" in config.categories

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
        assert "epics" in config.categories
        assert config.categories["epics"].prefix == "EPIC"

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
        assert config.label_mapping == {
            "BUG": "bug",
            "FEAT": "enhancement",
            "ENH": "enhancement",
            "EPIC": "epic",
        }
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


class TestEventsConfig:
    """Tests for EventsConfig dataclass."""

    def test_from_dict_with_defaults(self) -> None:
        """Test creating EventsConfig with default values."""
        config = EventsConfig.from_dict({})

        assert config.transports == []
        assert isinstance(config.socket, SocketEventsConfig)
        assert config.socket.path == ".ll/events.sock"
        assert config.socket.max_clients == 32
        assert isinstance(config.otel, OTelEventsConfig)
        assert config.otel.endpoint == "http://localhost:4317"
        assert config.otel.service_name == "little-loops"
        assert isinstance(config.webhook, WebhookEventsConfig)
        assert config.webhook.url is None
        assert config.webhook.batch_ms == 1000
        assert config.webhook.headers == {}

    def test_from_dict_with_transports(self) -> None:
        """Test creating EventsConfig with explicit transports list."""
        config = EventsConfig.from_dict({"transports": ["jsonl"]})

        assert config.transports == ["jsonl"]

    def test_from_dict_with_socket_overrides(self) -> None:
        """events.socket sub-object overrides defaults."""
        config = EventsConfig.from_dict(
            {
                "transports": ["jsonl", "socket"],
                "socket": {"path": "/tmp/x.sock", "max_clients": 32},
            }
        )

        assert config.transports == ["jsonl", "socket"]
        assert config.socket.path == "/tmp/x.sock"
        assert config.socket.max_clients == 32

    def test_from_dict_with_otel_overrides(self) -> None:
        """events.otel sub-object overrides defaults."""
        config = EventsConfig.from_dict(
            {
                "transports": ["otel"],
                "otel": {
                    "endpoint": "http://collector:4317",
                    "service_name": "my-service",
                },
            }
        )

        assert config.transports == ["otel"]
        assert config.otel.endpoint == "http://collector:4317"
        assert config.otel.service_name == "my-service"

    def test_from_dict_with_webhook_overrides(self) -> None:
        """events.webhook sub-object overrides defaults."""
        config = EventsConfig.from_dict(
            {
                "transports": ["webhook"],
                "webhook": {
                    "url": "https://hooks.example.com/ll",
                    "batch_ms": 500,
                    "headers": {"Authorization": "Bearer tok"},
                },
            }
        )

        assert config.transports == ["webhook"]
        assert config.webhook.url == "https://hooks.example.com/ll"
        assert config.webhook.batch_ms == 500
        assert config.webhook.headers == {"Authorization": "Bearer tok"}


class TestSocketEventsConfig:
    """Tests for SocketEventsConfig dataclass."""

    def test_defaults(self) -> None:
        """SocketEventsConfig defaults match the documented values."""
        config = SocketEventsConfig.from_dict({})

        assert config.path == ".ll/events.sock"
        assert config.max_clients == 32

    def test_from_dict_with_overrides(self) -> None:
        """Explicit values override defaults."""
        config = SocketEventsConfig.from_dict({"path": "/var/run/ll.sock", "max_clients": 16})

        assert config.path == "/var/run/ll.sock"
        assert config.max_clients == 16


class TestOTelEventsConfig:
    """Tests for OTelEventsConfig dataclass."""

    def test_defaults(self) -> None:
        """OTelEventsConfig defaults match the documented values."""
        config = OTelEventsConfig.from_dict({})

        assert config.endpoint == "http://localhost:4317"
        assert config.service_name == "little-loops"

    def test_from_dict_with_overrides(self) -> None:
        """Explicit values override defaults."""
        config = OTelEventsConfig.from_dict(
            {"endpoint": "http://collector:4317", "service_name": "my-svc"}
        )

        assert config.endpoint == "http://collector:4317"
        assert config.service_name == "my-svc"


class TestWebhookEventsConfig:
    """Tests for WebhookEventsConfig dataclass."""

    def test_defaults(self) -> None:
        """WebhookEventsConfig defaults match the documented values."""
        config = WebhookEventsConfig.from_dict({})

        assert config.url is None
        assert config.batch_ms == 1000
        assert config.headers == {}

    def test_from_dict_with_overrides(self) -> None:
        """Explicit values override defaults."""
        config = WebhookEventsConfig.from_dict(
            {
                "url": "https://hooks.example.com/ll",
                "batch_ms": 250,
                "headers": {"X-Api-Key": "secret"},
            }
        )

        assert config.url == "https://hooks.example.com/ll"
        assert config.batch_ms == 250
        assert config.headers == {"X-Api-Key": "secret"}

    def test_from_dict_url_null(self) -> None:
        """Explicit null url is preserved."""
        config = WebhookEventsConfig.from_dict({"url": None})

        assert config.url is None


class TestBRConfigEventsIntegration:
    """Tests for BRConfig events property integration."""

    def test_events_property_exists(self, temp_project_dir: Path) -> None:
        """Test that BRConfig has events property."""
        config = BRConfig(temp_project_dir)

        assert hasattr(config, "events")
        assert isinstance(config.events, EventsConfig)

    def test_events_property_with_defaults(self, temp_project_dir: Path) -> None:
        """Test events property returns defaults when not configured."""
        config = BRConfig(temp_project_dir)

        assert config.events.transports == []

    def test_events_property_loads_from_config(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test events property loads from config file."""
        sample_config["events"] = {"transports": ["jsonl"]}
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)

        assert config.events.transports == ["jsonl"]

    def test_events_in_to_dict(self, temp_project_dir: Path) -> None:
        """Test events config appears in to_dict output."""
        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert "events" in result
        assert "transports" in result["events"]

    @pytest.mark.parametrize(
        "transport,sub_cfg,expected",
        [
            (
                "socket",
                {"path": "/tmp/test.sock", "max_clients": 4},
                {"path": "/tmp/test.sock", "max_clients": 4},
            ),
            (
                "otel",
                {"endpoint": "http://collector:4317", "service_name": "my-svc"},
                {"endpoint": "http://collector:4317", "service_name": "my-svc"},
            ),
            (
                "webhook",
                {
                    "url": "https://hooks.example.com/ll",
                    "batch_ms": 500,
                    "headers": {"Authorization": "Bearer tok"},
                },
                {
                    "url": "https://hooks.example.com/ll",
                    "batch_ms": 500,
                    "headers": {"Authorization": "Bearer tok"},
                },
            ),
        ],
        ids=["socket", "otel", "webhook"],
    )
    def test_events_transport_sub_config_round_trips_through_to_dict(
        self,
        transport: str,
        sub_cfg: dict[str, Any],
        expected: dict[str, Any],
        temp_project_dir: Path,
        sample_config: dict[str, Any],
    ) -> None:
        """events.<transport> sub-config round-trips through BRConfig.to_dict()."""
        sample_config["events"] = {"transports": [transport], transport: sub_cfg}
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert result["events"]["transports"] == [transport]
        assert result["events"][transport] == expected


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


class TestCodeQueryConfig:
    """Tests for CodeQueryConfig dataclass."""

    def test_from_dict_with_defaults(self) -> None:
        """Test creating CodeQueryConfig with default values."""
        config = CodeQueryConfig.from_dict({})
        assert config.provider == "auto"
        assert config.codegraph.db_path == ".codegraph/codegraph.db"
        assert config.staleness == "warn"

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating CodeQueryConfig with all fields specified."""
        data = {
            "provider": "codegraph",
            "codegraph": {"db_path": "custom/path.db"},
            "staleness": "strict",
        }
        config = CodeQueryConfig.from_dict(data)
        assert config.provider == "codegraph"
        assert config.codegraph.db_path == "custom/path.db"
        assert config.staleness == "strict"

    def test_from_dict_partial_data(self) -> None:
        """Test creating CodeQueryConfig with partial data."""
        data = {"staleness": "off"}
        config = CodeQueryConfig.from_dict(data)
        assert config.staleness == "off"
        # Other fields should use defaults
        assert config.provider == "auto"
        assert config.codegraph.db_path == ".codegraph/codegraph.db"

    def test_codegraph_from_dict_with_defaults(self) -> None:
        """Test creating CodeQueryCodegraphConfig with default values."""
        config = CodeQueryCodegraphConfig.from_dict({})
        assert config.db_path == ".codegraph/codegraph.db"

    def test_brconfig_defaults(self, temp_project_dir: Path) -> None:
        """Test BRConfig loads code_query with defaults."""
        config = BRConfig(temp_project_dir)
        assert config.code_query.provider == "auto"
        assert config.code_query.staleness == "warn"

    def test_brconfig_loads_from_file(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """Test BRConfig loads code_query from config file."""
        sample_config["code_query"] = {
            "provider": "codegraph",
            "codegraph": {"db_path": ".codegraph/custom.db"},
            "staleness": "strict",
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        assert config.code_query.provider == "codegraph"
        assert config.code_query.codegraph.db_path == ".codegraph/custom.db"
        assert config.code_query.staleness == "strict"

    def test_code_query_in_to_dict(self, temp_project_dir: Path) -> None:
        """Test code_query config appears in to_dict output."""
        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert "code_query" in result
        cq = result["code_query"]
        assert cq["provider"] == "auto"
        assert cq["codegraph"]["db_path"] == ".codegraph/codegraph.db"
        assert cq["staleness"] == "warn"

    def test_resolve_variable_code_query(self, temp_project_dir: Path) -> None:
        """Test resolve_variable works for code_query config paths."""
        config = BRConfig(temp_project_dir)
        assert config.resolve_variable("code_query.provider") == "auto"
        assert config.resolve_variable("code_query.staleness") == "warn"


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
        assert config.parallel == "\u2225"

    def test_from_dict_empty(self) -> None:
        config = LoopsGlyphsConfig.from_dict({})
        assert config.prompt == "\u2726"
        assert config.sub_loop == "\u21b3\u27f3"
        assert config.parallel == "\u2225"

    def test_from_dict_partial_override(self) -> None:
        config = LoopsGlyphsConfig.from_dict({"prompt": "P", "shell": "S"})
        assert config.prompt == "P"
        assert config.shell == "S"
        assert config.mcp_tool == "\u26a1"  # default unchanged

    def test_from_dict_parallel_override(self) -> None:
        config = LoopsGlyphsConfig.from_dict({"parallel": "P"})
        assert config.parallel == "P"
        assert config.route == "\u2443"  # default unchanged

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
            "parallel",
        }
        assert d["prompt"] == "\u2726"
        assert d["route"] == "\u2443"
        assert d["parallel"] == "\u2225"

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
        assert config.loops.glyphs.parallel == "\u2225"

    def test_loops_glyphs_override_from_config(self, temp_project_dir: Path) -> None:
        """Custom loops.glyphs values are loaded from config file."""
        sample_config: dict[str, Any] = {
            "loops": {"glyphs": {"prompt": "P", "mcp_tool": "M", "parallel": "Q"}}
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        assert config.loops.glyphs.prompt == "P"
        assert config.loops.glyphs.mcp_tool == "M"
        assert config.loops.glyphs.parallel == "Q"
        assert config.loops.glyphs.shell == "\u276f_"  # default unchanged
        assert config.loops.glyphs.route == "\u2443"  # default unchanged


class TestLearningTestsConfig:
    """Tests for LearningTestsConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating LearningTestsConfig with all fields."""
        data = {"stale_after_days": 14}
        config = LearningTestsConfig.from_dict(data)
        assert config.stale_after_days == 14

    def test_from_dict_with_defaults(self) -> None:
        """Test creating LearningTestsConfig with default values."""
        config = LearningTestsConfig.from_dict({})
        assert config.stale_after_days == 30

    def test_enabled_defaults_to_false(self) -> None:
        """enabled defaults to False when absent (FEAT-1743)."""
        config = LearningTestsConfig.from_dict({})
        assert config.enabled is False

    def test_enabled_from_dict(self) -> None:
        """enabled is read from config dict (FEAT-1743)."""
        config = LearningTestsConfig.from_dict({"enabled": True})
        assert config.enabled is True

    def test_auto_prove_defaults_to_true(self) -> None:
        """auto_prove defaults to True when absent (ENH-2487)."""
        config = LearningTestsConfig.from_dict({})
        assert config.auto_prove is True

    def test_auto_prove_from_dict(self) -> None:
        """auto_prove is read from config dict (ENH-2487)."""
        config = LearningTestsConfig.from_dict({"auto_prove": False})
        assert config.auto_prove is False

    def test_discoverability_defaults(self) -> None:
        """discoverability sub-config defaults when absent (FEAT-1743)."""
        config = LearningTestsConfig.from_dict({})
        assert config.discoverability.mode == "warn"
        assert config.discoverability.skip_packages == ["std", "typing", "os", "sys"]

    def test_discoverability_from_dict(self) -> None:
        """discoverability sub-config is read from config dict (FEAT-1743)."""
        config = LearningTestsConfig.from_dict(
            {
                "discoverability": {
                    "mode": "block",
                    "skip_packages": ["std", "os"],
                },
            }
        )
        assert config.discoverability.mode == "block"
        assert config.discoverability.skip_packages == ["std", "os"]

    def test_release_gate_defaults_to_warn(self) -> None:
        """release_gate defaults to 'warn' when absent (ENH-2214)."""
        config = LearningTestsConfig.from_dict({})
        assert config.release_gate == "warn"

    def test_release_gate_block_from_dict(self) -> None:
        """release_gate is read from config dict (ENH-2214)."""
        config = LearningTestsConfig.from_dict({"release_gate": "block"})
        assert config.release_gate == "block"

    def test_scan_dirs_defaults(self) -> None:
        """scan_dirs defaults to ['scripts/'] when absent (ENH-2214)."""
        config = LearningTestsConfig.from_dict({})
        assert config.scan_dirs == ["scripts/"]

    def test_scan_dirs_from_dict(self) -> None:
        """scan_dirs is read from config dict (ENH-2214)."""
        config = LearningTestsConfig.from_dict({"scan_dirs": ["src/", "lib/"]})
        assert config.scan_dirs == ["src/", "lib/"]


class TestBRConfigLearningTestsIntegration:
    """Tests for BRConfig.learning_tests integration."""

    def test_learning_tests_defaults_when_absent(self, temp_project_dir: Path) -> None:
        """BRConfig.learning_tests returns defaults when key is absent."""
        config = BRConfig(temp_project_dir)
        assert config.learning_tests.stale_after_days == 30

    def test_learning_tests_override_from_config(self, temp_project_dir: Path) -> None:
        """Custom learning_tests values are loaded from config file."""
        sample_config: dict[str, Any] = {"learning_tests": {"stale_after_days": 7}}
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        assert config.learning_tests.stale_after_days == 7

    def test_learning_tests_enabled_defaults_false(self, temp_project_dir: Path) -> None:
        """BRConfig.learning_tests.enabled defaults to False (FEAT-1743)."""
        config = BRConfig(temp_project_dir)
        assert config.learning_tests.enabled is False

    def test_learning_tests_round_trip_to_dict(self, temp_project_dir: Path) -> None:
        """learning_tests key appears in to_dict() with correct structure (FEAT-1743)."""
        config = BRConfig(temp_project_dir)
        d = config.to_dict()
        assert "learning_tests" in d
        lt = d["learning_tests"]
        assert lt["enabled"] is False
        assert lt["auto_prove"] is True  # ENH-2487
        assert lt["stale_after_days"] == 30
        assert "discoverability" in lt
        assert lt["discoverability"]["mode"] == "warn"

    def test_issues_auto_commit_round_trip_to_dict(self, temp_project_dir: Path) -> None:
        """auto_commit fields appear in to_dict() issues sub-dict with correct defaults (ENH-1843)."""
        config = BRConfig(temp_project_dir)
        d = config.to_dict()
        assert "issues" in d
        issues = d["issues"]
        assert issues["auto_commit"] is False
        assert issues["auto_commit_prefix"] == "chore(issues)"

    def test_issues_auto_commit_round_trip_override(self, temp_project_dir: Path) -> None:
        """auto_commit overrides from config file are preserved through to_dict() (ENH-1843)."""
        config_file = temp_project_dir / ".ll" / "ll-config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            '{"issues": {"auto_commit": true, "auto_commit_prefix": "ci(issues)"}}'
        )
        config = BRConfig(temp_project_dir)
        d = config.to_dict()
        issues = d["issues"]
        assert issues["auto_commit"] is True
        assert issues["auto_commit_prefix"] == "ci(issues)"


class TestDecisionsConfig:
    """Tests for DecisionsConfig dataclass."""

    def test_from_dict_defaults(self) -> None:
        config = DecisionsConfig.from_dict({})
        assert config.enabled is False
        assert config.log_path == ".ll/decisions.yaml"
        assert config.auto_generate == []

    def test_from_dict_with_values(self) -> None:
        data = {
            "enabled": True,
            "log_path": ".ll/my-decisions.yaml",
            "auto_generate": ["NAMING-001"],
        }
        config = DecisionsConfig.from_dict(data)
        assert config.enabled is True
        assert config.log_path == ".ll/my-decisions.yaml"
        assert config.auto_generate == ["NAMING-001"]

    def test_from_dict_partial(self) -> None:
        config = DecisionsConfig.from_dict({"enabled": True})
        assert config.enabled is True
        assert config.log_path == ".ll/decisions.yaml"


class TestBRConfigDecisionsIntegration:
    """Tests for BRConfig.decisions integration."""

    def test_decisions_defaults_when_absent(self, temp_project_dir: Path) -> None:
        config = BRConfig(temp_project_dir)
        assert config.decisions.enabled is False
        assert config.decisions.log_path == ".ll/decisions.yaml"
        assert config.decisions.auto_generate == []

    def test_decisions_override_from_config(self, temp_project_dir: Path) -> None:
        sample_config: dict[str, Any] = {
            "decisions": {"enabled": True, "log_path": ".ll/custom.yaml"}
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        assert config.decisions.enabled is True
        assert config.decisions.log_path == ".ll/custom.yaml"

    def test_decisions_round_trip_to_dict(self, temp_project_dir: Path) -> None:
        config = BRConfig(temp_project_dir)
        d = config.to_dict()
        assert "decisions" in d
        dec = d["decisions"]
        assert dec["enabled"] is False
        assert dec["log_path"] == ".ll/decisions.yaml"
        assert dec["auto_generate"] == []


class TestDesignTokensConfig:
    """Tests for DesignTokensConfig dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating DesignTokensConfig with all fields specified."""
        data = {
            "enabled": False,
            "path": ".ll/my-tokens",
            "primitives_file": "prim.json",
            "semantic_file": "sem.json",
            "themes_dir": "t",
            "active_theme": "dark",
        }
        config = DesignTokensConfig.from_dict(data)
        assert config.enabled is False
        assert config.path == ".ll/my-tokens"
        assert config.primitives_file == "prim.json"
        assert config.semantic_file == "sem.json"
        assert config.themes_dir == "t"
        assert config.active_theme == "dark"

    def test_from_dict_with_defaults(self) -> None:
        """Test creating DesignTokensConfig with default values."""
        config = DesignTokensConfig.from_dict({})
        assert config.enabled is True
        assert config.path == ".ll/design-tokens"
        assert config.primitives_file == "primitives.json"
        assert config.semantic_file == "semantic.json"
        assert config.themes_dir == "themes"
        assert config.active_theme == "dark"


class TestBRConfigDesignTokensIntegration:
    """Tests for BRConfig.design_tokens integration."""

    def test_design_tokens_defaults_when_absent(self, temp_project_dir: Path) -> None:
        """BRConfig.design_tokens returns defaults when key is absent."""
        config = BRConfig(temp_project_dir)
        assert config.design_tokens.enabled is True
        assert config.design_tokens.path == ".ll/design-tokens"
        assert config.design_tokens.active_theme == "dark"

    def test_design_tokens_override_from_config(self, temp_project_dir: Path) -> None:
        """Custom design_tokens values are loaded from config file."""
        sample_config: dict[str, Any] = {
            "design_tokens": {
                "enabled": False,
                "path": ".ll/brand-tokens",
                "active_theme": "dark",
            }
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        assert config.design_tokens.enabled is False
        assert config.design_tokens.path == ".ll/brand-tokens"
        assert config.design_tokens.active_theme == "dark"

    def test_design_tokens_round_trip_to_dict(self, temp_project_dir: Path) -> None:
        """design_tokens key appears in to_dict() with correct structure."""
        config = BRConfig(temp_project_dir)
        d = config.to_dict()
        assert "design_tokens" in d
        dt = d["design_tokens"]
        assert dt["enabled"] is True
        assert dt["path"] == ".ll/design-tokens"
        assert dt["primitives_file"] == "primitives.json"
        assert dt["semantic_file"] == "semantic.json"
        assert dt["themes_dir"] == "themes"
        assert dt["active_theme"] == "dark"


class TestDeepMerge:
    """Tests for `little_loops.config.core.deep_merge` (config-overlay semantics)."""

    def test_replaces_scalar(self) -> None:
        """Override scalar replaces base scalar."""
        from little_loops.config.core import deep_merge

        result = deep_merge({"a": 1}, {"a": 2})
        assert result == {"a": 2}

    def test_adds_new_key(self) -> None:
        """Override adds keys not in base."""
        from little_loops.config.core import deep_merge

        result = deep_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_recurses_into_nested_dicts(self) -> None:
        """Nested dicts merge recursively at every level."""
        from little_loops.config.core import deep_merge

        result = deep_merge(
            {"outer": {"inner": {"x": 1, "y": 2}}},
            {"outer": {"inner": {"y": 99, "z": 3}}},
        )
        assert result == {"outer": {"inner": {"x": 1, "y": 99, "z": 3}}}

    def test_arrays_replace_not_append(self) -> None:
        """Arrays in override replace base arrays — they do not append."""
        from little_loops.config.core import deep_merge

        result = deep_merge({"items": [1, 2, 3]}, {"items": [4]})
        assert result == {"items": [4]}

    def test_null_removes_key(self) -> None:
        """Explicit `None` in override removes the key from the result."""
        from little_loops.config.core import deep_merge

        result = deep_merge({"a": 1, "b": 2}, {"a": None})
        assert result == {"b": 2}

    def test_null_on_missing_key_is_noop(self) -> None:
        """`None` for a key not in base is a no-op (no KeyError)."""
        from little_loops.config.core import deep_merge

        result = deep_merge({"a": 1}, {"b": None})
        assert result == {"a": 1}

    def test_dict_replaces_scalar(self) -> None:
        """Override dict replaces base scalar (no recursion when base is not a dict)."""
        from little_loops.config.core import deep_merge

        result = deep_merge({"a": 1}, {"a": {"x": 2}})
        assert result == {"a": {"x": 2}}

    def test_does_not_mutate_inputs(self) -> None:
        """Merge returns a new dict; neither input is mutated."""
        from little_loops.config.core import deep_merge

        base = {"a": {"b": 1}}
        override = {"a": {"c": 2}}
        deep_merge(base, override)
        assert base == {"a": {"b": 1}}
        assert override == {"a": {"c": 2}}


class TestClusterConfig:
    """Tests for ClusterConfig dataclass."""

    def test_from_dict_with_defaults(self) -> None:
        config = ClusterConfig.from_dict({})
        assert config.max_batch_size == 5
        assert config.enable_dedup is True
        assert config.propagate_context is True

    def test_from_dict_with_all_fields(self) -> None:
        config = ClusterConfig.from_dict(
            {"max_batch_size": 3, "enable_dedup": False, "propagate_context": False}
        )
        assert config.max_batch_size == 3
        assert config.enable_dedup is False
        assert config.propagate_context is False

    def test_from_dict_partial_override(self) -> None:
        config = ClusterConfig.from_dict({"max_batch_size": 10})
        assert config.max_batch_size == 10
        assert config.enable_dedup is True
        assert config.propagate_context is True


class TestOrchestrationConfig:
    """Tests for OrchestrationConfig dataclass."""

    def test_from_dict_with_defaults(self) -> None:
        config = OrchestrationConfig.from_dict({})
        assert config.host_cli is None

    def test_from_dict_with_host_cli(self) -> None:
        config = OrchestrationConfig.from_dict({"host_cli": "codex"})
        assert config.host_cli == "codex"

    def test_from_dict_with_claude_code(self) -> None:
        config = OrchestrationConfig.from_dict({"host_cli": "claude-code"})
        assert config.host_cli == "claude-code"

    def test_from_dict_defaults_composer_adaptive(self) -> None:
        config = OrchestrationConfig.from_dict({})
        assert config.composer.adaptive.enabled is False
        assert config.composer.adaptive.max_replans == 2
        assert config.composer.adaptive.reassess_min_confidence == 0.6

    def test_from_dict_composer_adaptive_with_values(self) -> None:
        data = {
            "composer": {
                "adaptive": {"enabled": True, "max_replans": 5, "reassess_min_confidence": 0.8}
            }
        }
        config = OrchestrationConfig.from_dict(data)
        assert config.composer.adaptive.enabled is True
        assert config.composer.adaptive.max_replans == 5
        assert config.composer.adaptive.reassess_min_confidence == 0.8

    def test_composer_adaptive_config_defaults(self) -> None:
        config = ComposerAdaptiveConfig.from_dict({})
        assert config.enabled is False
        assert config.max_replans == 2
        assert config.reassess_min_confidence == 0.6

    def test_composer_config_defaults(self) -> None:
        config = ComposerConfig.from_dict({})
        assert isinstance(config.adaptive, ComposerAdaptiveConfig)
        assert config.adaptive.enabled is False

    def test_from_dict_defaults_cluster(self) -> None:
        config = OrchestrationConfig.from_dict({})
        assert config.cluster.max_batch_size == 5
        assert config.cluster.enable_dedup is True
        assert config.cluster.propagate_context is True

    def test_from_dict_cluster_with_values(self) -> None:
        data = {"cluster": {"max_batch_size": 3, "enable_dedup": False, "propagate_context": False}}
        config = OrchestrationConfig.from_dict(data)
        assert config.cluster.max_batch_size == 3
        assert config.cluster.enable_dedup is False
        assert config.cluster.propagate_context is False

    def test_cluster_config_defaults(self) -> None:
        config = ClusterConfig.from_dict({})
        assert isinstance(config, ClusterConfig)
        assert config.max_batch_size == 5


class TestBRConfigOrchestration:
    """Extend TestBRConfig with orchestration property coverage."""

    def test_orchestration_property_from_file(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """BRConfig.orchestration returns OrchestrationConfig from file."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        assert isinstance(config.orchestration, OrchestrationConfig)
        assert config.orchestration.host_cli is None

    def test_orchestration_host_cli_from_file(self, temp_project_dir: Path) -> None:
        """BRConfig.orchestration.host_cli is read from ll-config.json."""
        cfg = {"orchestration": {"host_cli": "codex"}}
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(cfg))

        config = BRConfig(temp_project_dir)
        assert config.orchestration.host_cli == "codex"

    def test_orchestration_defaults_when_key_absent(self, temp_project_dir: Path) -> None:
        """BRConfig.orchestration returns defaults when orchestration key is absent."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text("{}")

        config = BRConfig(temp_project_dir)
        assert config.orchestration.host_cli is None

    def test_orchestration_composer_adaptive_from_file(self, temp_project_dir: Path) -> None:
        """BRConfig.orchestration.composer.adaptive is read from ll-config.json."""
        cfg = {"orchestration": {"composer": {"adaptive": {"enabled": True, "max_replans": 3}}}}
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(cfg))

        config = BRConfig(temp_project_dir)
        assert config.orchestration.composer.adaptive.enabled is True
        assert config.orchestration.composer.adaptive.max_replans == 3
        assert config.orchestration.composer.adaptive.reassess_min_confidence == 0.6

    def test_orchestration_cluster_from_file(self, temp_project_dir: Path) -> None:
        """BRConfig.orchestration.cluster is read from ll-config.json."""
        cfg = {"orchestration": {"cluster": {"max_batch_size": 2, "enable_dedup": False}}}
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(cfg))

        config = BRConfig(temp_project_dir)
        assert config.orchestration.cluster.max_batch_size == 2
        assert config.orchestration.cluster.enable_dedup is False
        assert config.orchestration.cluster.propagate_context is True


class TestBRConfigAnalyticsCaptureIntegration:
    """Tests for BRConfig.analytics_capture property (ENH-1840)."""

    def test_analytics_capture_property_exists(self, temp_project_dir: Path) -> None:
        from little_loops.config.features import AnalyticsCaptureConfig

        config = BRConfig(temp_project_dir)
        assert hasattr(config, "analytics_capture")
        assert isinstance(config.analytics_capture, AnalyticsCaptureConfig)

    def test_analytics_capture_defaults_when_absent(self, temp_project_dir: Path) -> None:
        """analytics_capture returns safe defaults when key is absent."""
        config = BRConfig(temp_project_dir)
        assert config.analytics_capture.skills == ["*"]
        assert config.analytics_capture.cli_commands == ["*"]
        assert config.analytics_capture.corrections is True
        assert config.analytics_capture.file_events is True

    def test_analytics_capture_loads_from_config(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """analytics.capture values are read from ll-config.json."""
        sample_config["analytics"] = {
            "enabled": True,
            "capture": {
                "skills": ["ll:commit"],
                "cli_commands": ["ll-auto"],
                "corrections": False,
                "file_events": False,
            },
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        assert config.analytics_capture.skills == ["ll:commit"]
        assert config.analytics_capture.cli_commands == ["ll-auto"]
        assert config.analytics_capture.corrections is False
        assert config.analytics_capture.file_events is False

    def test_analytics_capture_in_to_dict(self, temp_project_dir: Path) -> None:
        """analytics.capture appears in BRConfig.to_dict() output."""
        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert "analytics" in result
        assert "capture" in result["analytics"]
        assert result["analytics"]["capture"]["skills"] == ["*"]
        assert result["analytics"]["capture"]["corrections"] is True

    def test_analytics_capture_round_trips_through_to_dict(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        """analytics.capture round-trips through BRConfig.to_dict()."""
        sample_config["analytics"] = {
            "capture": {"skills": ["ll:commit", "ll:open-pr"], "corrections": False}
        }
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        config = BRConfig(temp_project_dir)
        result = config.to_dict()

        assert result["analytics"]["capture"]["skills"] == ["ll:commit", "ll:open-pr"]
        assert result["analytics"]["capture"]["corrections"] is False
        assert result["analytics"]["capture"]["cli_commands"] == ["*"]
        assert result["analytics"]["capture"]["file_events"] is True


class TestSessionDigestConfig:
    """Unit tests for SessionDigestConfig.from_dict (ENH-1913)."""

    def test_defaults(self) -> None:
        cfg = SessionDigestConfig.from_dict({})
        assert cfg.enabled is True
        assert cfg.days == 7
        assert cfg.char_cap == 1200
        assert cfg.sections == []

    def test_per_key_override(self) -> None:
        cfg = SessionDigestConfig.from_dict(
            {"enabled": True, "days": 14, "char_cap": 800, "sections": ["corrections"]}
        )
        assert cfg.enabled is True
        assert cfg.days == 14
        assert cfg.char_cap == 800
        assert cfg.sections == ["corrections"]

    def test_unknown_key_ignored(self) -> None:
        cfg = SessionDigestConfig.from_dict({"unknown_key": "value"})
        assert cfg.enabled is True


class TestEvolutionConfig:
    """Unit tests for EvolutionConfig.from_dict (ENH-1913)."""

    def test_defaults(self) -> None:
        cfg = EvolutionConfig.from_dict({})
        assert cfg.feedback_min_recurrence == 2
        assert cfg.bypass_min_count == 2

    def test_per_key_override(self) -> None:
        cfg = EvolutionConfig.from_dict({"feedback_min_recurrence": 5, "bypass_min_count": 3})
        assert cfg.feedback_min_recurrence == 5
        assert cfg.bypass_min_count == 3

    def test_unknown_key_ignored(self) -> None:
        cfg = EvolutionConfig.from_dict({"unknown_key": "value"})
        assert cfg.feedback_min_recurrence == 2


class TestGoNoGoConfig:
    """Unit tests for GoNoGoConfig.from_dict (ENH-1913)."""

    def test_defaults(self) -> None:
        cfg = GoNoGoConfig.from_dict({})
        assert cfg.correction_penalty == -0.2

    def test_per_key_override(self) -> None:
        cfg = GoNoGoConfig.from_dict({"correction_penalty": -0.5})
        assert cfg.correction_penalty == -0.5

    def test_unknown_key_ignored(self) -> None:
        cfg = GoNoGoConfig.from_dict({"unknown_key": "value"})
        assert cfg.correction_penalty == -0.2


class TestCaptureIssueConfig:
    """Unit tests for CaptureIssueConfig.from_dict (ENH-1913)."""

    def test_defaults(self) -> None:
        cfg = CaptureIssueConfig.from_dict({})
        assert cfg.dup_overlap_threshold == 0.7

    def test_per_key_override(self) -> None:
        cfg = CaptureIssueConfig.from_dict({"dup_overlap_threshold": 0.9})
        assert cfg.dup_overlap_threshold == 0.9

    def test_unknown_key_ignored(self) -> None:
        cfg = CaptureIssueConfig.from_dict({"unknown_key": "value"})
        assert cfg.dup_overlap_threshold == 0.7


class TestHistoryConfig:
    """Unit tests for HistoryConfig.from_dict (ENH-1913)."""

    def test_defaults(self) -> None:
        cfg = HistoryConfig.from_dict({})
        assert cfg.velocity_window == 10
        assert cfg.effort_fields == ["session_count", "cycle_time_days"]
        assert cfg.max_age_days is None
        assert cfg.planning_skills == ["create-sprint", "scope-epic", "manage-issue", "review-epic"]
        assert isinstance(cfg.session_digest, SessionDigestConfig)
        assert isinstance(cfg.evolution, EvolutionConfig)
        assert isinstance(cfg.go_no_go, GoNoGoConfig)
        assert isinstance(cfg.capture_issue, CaptureIssueConfig)

    def test_flat_key_override(self) -> None:
        cfg = HistoryConfig.from_dict({"velocity_window": 20, "max_age_days": 30})
        assert cfg.velocity_window == 20
        assert cfg.max_age_days == 30
        assert cfg.effort_fields == ["session_count", "cycle_time_days"]

    def test_nested_sub_object_defaults(self) -> None:
        cfg = HistoryConfig.from_dict({"session_digest": {}})
        assert cfg.session_digest.enabled is True
        assert cfg.session_digest.days == 7

    def test_nested_sub_object_override(self) -> None:
        cfg = HistoryConfig.from_dict({"session_digest": {"enabled": True, "days": 14}})
        assert cfg.session_digest.enabled is True
        assert cfg.session_digest.days == 14

    def test_evolution_defaults(self) -> None:
        cfg = HistoryConfig.from_dict({})
        assert cfg.evolution.feedback_min_recurrence == 2
        assert cfg.evolution.bypass_min_count == 2

    def test_go_no_go_defaults(self) -> None:
        cfg = HistoryConfig.from_dict({})
        assert cfg.go_no_go.correction_penalty == -0.2

    def test_capture_issue_defaults(self) -> None:
        cfg = HistoryConfig.from_dict({})
        assert cfg.capture_issue.dup_overlap_threshold == 0.7

    def test_compaction_defaults(self) -> None:
        cfg = HistoryConfig.from_dict({})
        assert isinstance(cfg.compaction, CompactionConfig)
        assert cfg.compaction.enabled is False
        assert cfg.compaction.budget_tokens == 4096
        assert cfg.compaction.model is None
        assert cfg.compaction.timeout == 60
        assert cfg.compaction.cross_session_enabled is True
        assert cfg.compaction.max_level is None

    def test_compaction_override(self) -> None:
        cfg = HistoryConfig.from_dict(
            {
                "compaction": {
                    "enabled": True,
                    "budget_tokens": 2048,
                    "timeout": 30,
                    "cross_session_enabled": False,
                    "max_level": 3,
                }
            }
        )
        assert cfg.compaction.enabled is True
        assert cfg.compaction.budget_tokens == 2048
        assert cfg.compaction.timeout == 30
        assert cfg.compaction.cross_session_enabled is False
        assert cfg.compaction.max_level == 3

    def test_unknown_key_ignored(self) -> None:
        cfg = HistoryConfig.from_dict({"unknown_key": "value"})
        assert cfg.velocity_window == 10

    def test_db_path_default_none(self) -> None:
        cfg = HistoryConfig.from_dict({})
        assert cfg.db_path is None

    def test_db_path_override(self) -> None:
        cfg = HistoryConfig.from_dict({"db_path": "/data/history.db"})
        assert cfg.db_path == "/data/history.db"


class TestBRConfigHistoryIntegration:
    """Integration tests for BRConfig.history property (ENH-1913)."""

    def test_history_property_exists(self, temp_project_dir: Path) -> None:
        config = BRConfig(temp_project_dir)
        assert hasattr(config, "history")

    def test_history_returns_history_config(self, temp_project_dir: Path) -> None:
        config = BRConfig(temp_project_dir)
        assert isinstance(config.history, HistoryConfig)

    def test_history_defaults_on_absent(self, temp_project_dir: Path) -> None:
        config = BRConfig(temp_project_dir)
        assert config.history.velocity_window == 10
        assert config.history.max_age_days is None
        assert config.history.session_digest.enabled is True
        assert config.history.evolution.feedback_min_recurrence == 2
        assert config.history.go_no_go.correction_penalty == -0.2
        assert config.history.capture_issue.dup_overlap_threshold == 0.7

    def test_history_loads_from_config(
        self, temp_project_dir: Path, sample_config: dict[str, Any]
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        sample_config["history"] = {
            "velocity_window": 15,
            "max_age_days": 60,
            "session_digest": {"enabled": True, "days": 14},
            "go_no_go": {"correction_penalty": -0.5},
            "capture_issue": {"dup_overlap_threshold": 0.9},
        }
        config_path.write_text(json.dumps(sample_config))
        config = BRConfig(temp_project_dir)
        assert config.history.velocity_window == 15
        assert config.history.max_age_days == 60
        assert config.history.session_digest.enabled is True
        assert config.history.session_digest.days == 14
        assert config.history.go_no_go.correction_penalty == -0.5
        assert config.history.capture_issue.dup_overlap_threshold == 0.9

    def test_history_to_dict_round_trip(self, temp_project_dir: Path) -> None:
        config = BRConfig(temp_project_dir)
        d = config.to_dict()
        assert "history" in d
        h = d["history"]
        assert h["velocity_window"] == 10
        assert h["max_age_days"] is None
        assert h["effort_fields"] == ["session_count", "cycle_time_days"]
        assert h["planning_skills"] == [
            "create-sprint",
            "scope-epic",
            "manage-issue",
            "review-epic",
        ]
        assert h["session_digest"]["enabled"] is True
        assert h["session_digest"]["days"] == 7
        assert h["session_digest"]["char_cap"] == 1200
        assert h["session_digest"]["sections"] == []
        assert h["evolution"]["feedback_min_recurrence"] == 2
        assert h["evolution"]["bypass_min_count"] == 2
        assert h["go_no_go"]["correction_penalty"] == -0.2
        assert h["capture_issue"]["dup_overlap_threshold"] == 0.7
        assert h["compaction"]["enabled"] is False
        assert h["compaction"]["budget_tokens"] == 4096
        assert h["compaction"]["model"] is None
        assert h["compaction"]["timeout"] == 60
        assert h["compaction"]["cross_session_enabled"] is True
        assert h["compaction"]["max_level"] is None

    def test_history_round_trip_from_dict(self, temp_project_dir: Path) -> None:
        config = BRConfig(temp_project_dir)
        d = config.to_dict()
        h2 = HistoryConfig.from_dict(d["history"])
        assert h2.velocity_window == config.history.velocity_window
        assert h2.max_age_days == config.history.max_age_days
        assert h2.session_digest.enabled == config.history.session_digest.enabled
        assert (
            h2.evolution.feedback_min_recurrence == config.history.evolution.feedback_min_recurrence
        )
        assert h2.compaction.enabled == config.history.compaction.enabled
        assert (
            h2.compaction.cross_session_enabled == config.history.compaction.cross_session_enabled
        )
        assert h2.compaction.max_level == config.history.compaction.max_level


class TestPreCompactRubricConfig:
    """Tests for PreCompactRubricConfig dataclass (ENH-2341)."""

    def test_enabled_defaults_to_false(self) -> None:
        """enabled defaults to False (opt-in; preserves existing behaviour)."""
        config = PreCompactRubricConfig.from_dict({})
        assert config.enabled is False

    def test_enabled_from_dict(self) -> None:
        """enabled is read from config dict."""
        config = PreCompactRubricConfig.from_dict({"enabled": True})
        assert config.enabled is True

    def test_hard_ceiling_pct_defaults(self) -> None:
        """hard_ceiling_pct defaults to 0.95."""
        config = PreCompactRubricConfig.from_dict({})
        assert config.hard_ceiling_pct == 0.95

    def test_hard_ceiling_pct_from_dict(self) -> None:
        """hard_ceiling_pct is read from config dict."""
        config = PreCompactRubricConfig.from_dict({"hard_ceiling_pct": 0.80})
        assert config.hard_ceiling_pct == 0.80

    def test_signals_defaults_non_empty(self) -> None:
        """All four signal lists default to non-empty lists."""
        config = PreCompactRubricConfig.from_dict({})
        assert len(config.signals.closed_unit_signals) > 0
        assert len(config.signals.reducible_signals) > 0
        assert len(config.signals.progress_signals) > 0
        assert len(config.signals.stuck_signals) > 0

    def test_signals_closed_unit_from_dict(self) -> None:
        """closed_unit_signals is read from nested signals dict."""
        config = PreCompactRubricConfig.from_dict(
            {"signals": {"closed_unit_signals": [r"\bmission accomplished\b"]}}
        )
        assert r"\bmission accomplished\b" in config.signals.closed_unit_signals

    def test_signals_reducible_from_dict(self) -> None:
        """reducible_signals is read from nested signals dict."""
        config = PreCompactRubricConfig.from_dict(
            {"signals": {"reducible_signals": [r"\bin short\b"]}}
        )
        assert r"\bin short\b" in config.signals.reducible_signals

    def test_signals_progress_from_dict(self) -> None:
        """progress_signals is read from nested signals dict."""
        config = PreCompactRubricConfig.from_dict(
            {"signals": {"progress_signals": [r"\badvanced\b"]}}
        )
        assert r"\badvanced\b" in config.signals.progress_signals

    def test_signals_stuck_from_dict(self) -> None:
        """stuck_signals is read from nested signals dict."""
        config = PreCompactRubricConfig.from_dict({"signals": {"stuck_signals": [r"\bdeadloop\b"]}})
        assert r"\bdeadloop\b" in config.signals.stuck_signals

    def test_from_dict_empty_does_not_raise(self) -> None:
        """from_dict({}) returns a valid default instance without raising."""
        config = PreCompactRubricConfig.from_dict({})
        assert isinstance(config, PreCompactRubricConfig)

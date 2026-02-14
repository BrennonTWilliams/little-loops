"""Integration tests for sprint execution."""

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.config import BRConfig
from little_loops.sprint import SprintManager

pytestmark = pytest.mark.integration


@pytest.fixture
def sprint_project(tmp_path: Path) -> BRConfig:
    """Create a test project with issues and config."""
    # Create directory structure
    issues_dir = tmp_path / ".issues"
    issues_dir.mkdir()

    for category in ["bugs", "features", "enhancements", "completed"]:
        (issues_dir / category).mkdir()

    # Create config
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()

    config_file = config_dir / "ll-config.json"
    config_data = {
        "project": {
            "name": "test-project",
            "src_dir": "src/",
            "test_cmd": "pytest",
            "lint_cmd": "ruff check",
        },
        "issues": {
            "base_dir": ".issues",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
            },
            "completed_dir": "completed",
        },
    }

    with open(config_file, "w") as f:
        json.dump(config_data, f)

    # Create sample issues
    (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
        "# BUG-001: Test Bug\n\nFix this bug."
    )
    (issues_dir / "features" / "P2-FEAT-010-test-feature.md").write_text(
        "# FEAT-010: Test Feature\n\nImplement this feature."
    )

    return BRConfig(tmp_path)


def test_sprint_lifecycle(sprint_project: BRConfig, tmp_path: Path) -> None:
    """Test full sprint lifecycle: create, list, show, delete."""
    manager = SprintManager(sprints_dir=tmp_path, config=sprint_project)

    # Create sprint
    sprint = manager.create(
        name="test-sprint",
        issues=["BUG-001", "FEAT-010"],
        description="Test sprint",
    )

    assert sprint.name == "test-sprint"
    assert len(sprint.issues) == 2

    # List sprints
    sprints = manager.list_all()
    assert len(sprints) == 1
    assert sprints[0].name == "test-sprint"

    # Show sprint
    loaded = manager.load("test-sprint")
    assert loaded is not None
    assert loaded.issues == ["BUG-001", "FEAT-010"]

    # Validate issues
    valid = manager.validate_issues(loaded.issues)
    assert "BUG-001" in valid
    assert "FEAT-010" in valid

    # Delete sprint
    result = manager.delete("test-sprint")
    assert result is True

    # Verify deleted
    sprints = manager.list_all()
    assert len(sprints) == 0


def test_sprint_validation_invalid_issues(sprint_project: BRConfig, tmp_path: Path) -> None:
    """Test sprint validation with invalid issue IDs."""
    manager = SprintManager(sprints_dir=tmp_path, config=sprint_project)

    # Create sprint with mix of valid and invalid issues
    sprint = manager.create(
        name="test-sprint",
        issues=["BUG-001", "NONEXISTENT", "FEAT-010"],
    )

    # Validate
    valid = manager.validate_issues(sprint.issues)

    # Only BUG-001 and FEAT-010 should be valid
    assert "BUG-001" in valid
    assert "FEAT-010" in valid
    assert "NONEXISTENT" not in valid


def test_sprint_yaml_format(sprint_project: BRConfig, tmp_path: Path) -> None:
    """Test sprint YAML file format matches specification."""
    import yaml

    manager = SprintManager(sprints_dir=tmp_path, config=sprint_project)

    manager.create(
        name="test-sprint",
        issues=["BUG-001"],
        description="Test sprint",
    )

    # Read YAML file
    yaml_path = tmp_path / "test-sprint.yaml"
    content = yaml_path.read_text()

    # Verify structure
    assert "name: test-sprint" in content
    assert "description: Test sprint" in content
    assert "issues:" in content
    assert "- BUG-001" in content
    assert "created:" in content

    # Parse and verify
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    assert data["name"] == "test-sprint"
    assert data["description"] == "Test sprint"
    assert data["issues"] == ["BUG-001"]
    assert "created" in data


class TestMultiWaveExecution:
    """Integration tests for multi-wave sprint execution."""

    @staticmethod
    def _setup_multi_wave_project(tmp_path: Path) -> tuple[Path, "BRConfig", "SprintManager"]:
        """Set up project with issues having dependencies for multi-wave testing.

        Creates:
        - BUG-001: no blockers (Wave 1)
        - BUG-002: blocked by BUG-001 (Wave 2)
        - FEAT-001: blocked by BUG-001 (Wave 2)
        - FEAT-002: blocked by BUG-002 and FEAT-001 (Wave 3)
        """
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()

        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_dir / category).mkdir()

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

        config_data = {
            "project": {
                "name": "test-project",
                "src_dir": "src/",
                "test_cmd": "pytest",
                "lint_cmd": "ruff check",
            },
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
                },
                "completed_dir": "completed",
            },
        }

        with open(config_dir / "ll-config.json", "w") as f:
            json.dump(config_data, f)

        # BUG-001: No blockers (Wave 1)
        (issues_dir / "bugs" / "P1-BUG-001-base-bug.md").write_text(
            "# BUG-001: Base Bug\n\n## Summary\nFirst issue, no dependencies."
        )

        # BUG-002: Blocked by BUG-001 (Wave 2)
        (issues_dir / "bugs" / "P1-BUG-002-dependent-bug.md").write_text(
            "# BUG-002: Dependent Bug\n\n## Summary\nDepends on BUG-001.\n\n"
            "## Blocked By\n- BUG-001"
        )

        # FEAT-001: Blocked by BUG-001 (Wave 2)
        (issues_dir / "features" / "P2-FEAT-001-feature-one.md").write_text(
            "# FEAT-001: Feature One\n\n## Summary\nDepends on BUG-001.\n\n## Blocked By\n- BUG-001"
        )

        # FEAT-002: Blocked by BUG-002 and FEAT-001 (Wave 3)
        (issues_dir / "features" / "P2-FEAT-002-feature-two.md").write_text(
            "# FEAT-002: Feature Two\n\n## Summary\nDepends on BUG-002 and FEAT-001.\n\n"
            "## Blocked By\n- BUG-002\n- FEAT-001"
        )

        # Create sprint file
        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()
        (sprints_dir / "multi-wave.yaml").write_text(
            """name: multi-wave
description: Test multi-wave execution
issues:
  - BUG-001
  - BUG-002
  - FEAT-001
  - FEAT-002
"""
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)

        return sprints_dir, config, manager

    def test_sprint_wave_composition(self, tmp_path: Path) -> None:
        """Test wave calculation groups parallel issues correctly."""
        from little_loops.dependency_graph import DependencyGraph

        _, config, manager = self._setup_multi_wave_project(tmp_path)

        # Load sprint and compute waves
        sprint = manager.load("multi-wave")
        assert sprint is not None

        issue_infos = manager.load_issue_infos(sprint.issues)
        assert len(issue_infos) == 4

        dep_graph = DependencyGraph.from_issues(issue_infos)
        waves = dep_graph.get_execution_waves()

        # Should have 3 waves
        assert len(waves) == 3

        # Wave 1: BUG-001 only
        wave1_ids = {issue.issue_id for issue in waves[0]}
        assert wave1_ids == {"BUG-001"}

        # Wave 2: BUG-002 and FEAT-001 (both blocked by BUG-001)
        wave2_ids = {issue.issue_id for issue in waves[1]}
        assert wave2_ids == {"BUG-002", "FEAT-001"}

        # Wave 3: FEAT-002 (blocked by BUG-002 and FEAT-001)
        wave3_ids = {issue.issue_id for issue in waves[2]}
        assert wave3_ids == {"FEAT-002"}

    def test_sprint_run_multiple_waves(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test sprint with 3 waves executes issues in correct order."""
        import argparse

        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_multi_wave_project(tmp_path)

        # Track execution order
        executed_issues: list[str] = []

        def mock_process_inplace(info: Any, **kwargs: Any) -> Any:
            executed_issues.append(info.issue_id)
            from little_loops.issue_manager import IssueProcessingResult

            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr(
            "little_loops.issue_manager.process_issue_inplace",
            mock_process_inplace,
        )

        # Mock ParallelOrchestrator for multi-issue waves
        class MockQueue:
            def __init__(self, ids: set[str]):
                self._ids = ids

            @property
            def completed_ids(self) -> list[str]:
                return sorted(self._ids)

            @property
            def failed_ids(self) -> list[str]:
                return []

        class MockOrchestrator:
            execution_duration = 2.0

            def __init__(self, parallel_config: Any, br_config: Any, path: Any, **kwargs: Any):
                self.only_ids = parallel_config.only_ids
                self.queue = MockQueue(self.only_ids)

            def run(self) -> int:
                # Record execution of all issues in this wave
                for issue_id in sorted(self.only_ids):
                    executed_issues.append(issue_id)
                return 0

        monkeypatch.setattr(
            "little_loops.cli.sprint.ParallelOrchestrator",
            MockOrchestrator,
        )

        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="multi-wave",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=2,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 0

        # Verify execution order respects dependencies
        # Wave 1 (BUG-001) must complete before Wave 2 (BUG-002, FEAT-001)
        # Wave 2 must complete before Wave 3 (FEAT-002)
        assert "BUG-001" in executed_issues
        bug001_idx = executed_issues.index("BUG-001")
        bug002_idx = executed_issues.index("BUG-002")
        feat001_idx = executed_issues.index("FEAT-001")
        feat002_idx = executed_issues.index("FEAT-002")

        assert bug001_idx < bug002_idx, "BUG-001 should execute before BUG-002"
        assert bug001_idx < feat001_idx, "BUG-001 should execute before FEAT-001"
        assert bug002_idx < feat002_idx, "BUG-002 should execute before FEAT-002"
        assert feat001_idx < feat002_idx, "FEAT-001 should execute before FEAT-002"

    def test_sprint_parallel_within_wave(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test issues within same wave are processed together via orchestrator."""
        import argparse

        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_multi_wave_project(tmp_path)

        # Track which waves used orchestrator (multi-issue)
        orchestrator_wave_sizes: list[int] = []

        def mock_process_inplace(info: Any, **kwargs: Any) -> Any:
            from little_loops.issue_manager import IssueProcessingResult

            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr(
            "little_loops.issue_manager.process_issue_inplace",
            mock_process_inplace,
        )

        class MockQueue:
            def __init__(self, ids: set[str]):
                self._ids = ids

            @property
            def completed_ids(self) -> list[str]:
                return sorted(self._ids)

            @property
            def failed_ids(self) -> list[str]:
                return []

        class MockOrchestrator:
            execution_duration = 2.0

            def __init__(self, parallel_config: Any, br_config: Any, path: Any, **kwargs: Any):
                orchestrator_wave_sizes.append(len(parallel_config.only_ids))
                self.queue = MockQueue(parallel_config.only_ids)

            def run(self) -> int:
                return 0

        monkeypatch.setattr(
            "little_loops.cli.sprint.ParallelOrchestrator",
            MockOrchestrator,
        )

        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="multi-wave",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=4,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 0

        # Wave 2 has 2 issues and should use orchestrator
        assert 2 in orchestrator_wave_sizes, "Wave 2 (2 issues) should use ParallelOrchestrator"

    def test_sprint_enables_overlap_detection(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test sprint runner enables overlap detection for parallel waves (BUG-305)."""
        import argparse

        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_multi_wave_project(tmp_path)

        captured_configs: list[Any] = []

        def mock_process_inplace(info: Any, **kwargs: Any) -> Any:
            from little_loops.issue_manager import IssueProcessingResult

            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr(
            "little_loops.issue_manager.process_issue_inplace",
            mock_process_inplace,
        )

        class MockQueue:
            def __init__(self, ids: set[str]):
                self._ids = ids

            @property
            def completed_ids(self) -> list[str]:
                return sorted(self._ids)

            @property
            def failed_ids(self) -> list[str]:
                return []

        class MockOrchestrator:
            execution_duration = 2.0

            def __init__(self, parallel_config: Any, br_config: Any, path: Any, **kwargs: Any):
                captured_configs.append(parallel_config)
                self.queue = MockQueue(parallel_config.only_ids)

            def run(self) -> int:
                return 0

        monkeypatch.setattr(
            "little_loops.cli.sprint.ParallelOrchestrator",
            MockOrchestrator,
        )

        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="multi-wave",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=4,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 0

        # Verify overlap detection is enabled on all parallel configs
        assert len(captured_configs) > 0, "Should have created at least one ParallelConfig"
        for pc in captured_configs:
            assert pc.overlap_detection is True, "Sprint should enable overlap detection"
            assert pc.serialize_overlapping is True, "Sprint should serialize overlapping issues"


class TestErrorRecovery:
    """Integration tests for error recovery during sprint execution."""

    @staticmethod
    def _setup_error_recovery_project(tmp_path: Path) -> tuple[Path, "BRConfig", "SprintManager"]:
        """Set up project for error recovery testing."""
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()

        for category in ["bugs", "features", "enhancements", "completed"]:
            (issues_dir / category).mkdir()

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

        config_data = {
            "project": {
                "name": "test-project",
                "src_dir": "src/",
                "test_cmd": "pytest",
                "lint_cmd": "ruff check",
            },
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                },
                "completed_dir": "completed",
            },
        }

        with open(config_dir / "ll-config.json", "w") as f:
            json.dump(config_data, f)

        # Create 3 independent issues (all in Wave 1)
        (issues_dir / "bugs" / "P1-BUG-001-first.md").write_text(
            "# BUG-001: First\n\n## Summary\nFirst issue."
        )
        (issues_dir / "bugs" / "P1-BUG-002-second.md").write_text(
            "# BUG-002: Second\n\n## Summary\nSecond issue."
        )
        (issues_dir / "bugs" / "P1-BUG-003-third.md").write_text(
            "# BUG-003: Third\n\n## Summary\nThird issue."
        )

        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()
        (sprints_dir / "recovery-test.yaml").write_text(
            """name: recovery-test
issues:
  - BUG-001
  - BUG-002
  - BUG-003
"""
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)

        return sprints_dir, config, manager

    def test_sprint_wave_failure_tracks_correctly(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test failed issues are tracked in state correctly."""
        import argparse

        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_error_recovery_project(tmp_path)

        class MockQueue:
            @property
            def completed_ids(self) -> list[str]:
                return []

            @property
            def failed_ids(self) -> list[str]:
                return ["BUG-001", "BUG-002", "BUG-003"]

        class MockOrchestrator:
            execution_duration = 2.0

            def __init__(self, parallel_config: Any, br_config: Any, path: Any, **kwargs: Any):
                self.queue = MockQueue()

            def run(self) -> int:
                return 1  # Simulate failure

        monkeypatch.setattr(
            "little_loops.cli.sprint.ParallelOrchestrator",
            MockOrchestrator,
        )

        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="recovery-test",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=3,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 1  # Should indicate failure

        # Check state file
        state_file = tmp_path / ".sprint-state.json"
        assert state_file.exists()

        state_data = json.loads(state_file.read_text())
        assert state_data["sprint_name"] == "recovery-test"
        # All 3 issues should be tracked as failed
        assert len(state_data["failed_issues"]) == 3

    def test_sprint_state_saved_on_failure(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test state is saved when issue fails."""
        import argparse

        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_error_recovery_project(tmp_path)

        def mock_process_fail(info: Any, **kwargs: Any) -> Any:
            from little_loops.issue_manager import IssueProcessingResult

            return IssueProcessingResult(success=False, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr(
            "little_loops.issue_manager.process_issue_inplace",
            mock_process_fail,
        )

        # Create a single-issue sprint for simpler testing
        (tmp_path / ".sprints" / "single-fail.yaml").write_text(
            """name: single-fail
issues:
  - BUG-001
"""
        )

        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="single-fail",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=1,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 1

        # Verify state file created
        state_file = tmp_path / ".sprint-state.json"
        assert state_file.exists()

        state_data = json.loads(state_file.read_text())
        assert "BUG-001" in state_data["failed_issues"]

    def test_sprint_resume_skips_completed_waves(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test resume skips already-completed waves.

        Resume works at the wave level, not individual issue level.
        When a wave is fully completed, the sprint resumes from the next wave.
        """
        import argparse

        from little_loops.cli import sprint as cli
        from little_loops.sprint import SprintState

        # Create a project with dependencies to create multiple waves
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()
        for category in ["bugs", "completed"]:
            (issues_dir / category).mkdir()

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

        config_data = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                },
                "completed_dir": "completed",
            },
        }
        with open(config_dir / "ll-config.json", "w") as f:
            json.dump(config_data, f)

        # Create issues with dependencies:
        # BUG-001: Wave 1
        # BUG-002: Wave 2 (blocked by BUG-001)
        (issues_dir / "bugs" / "P1-BUG-001-first.md").write_text(
            "# BUG-001: First\n\n## Summary\nFirst issue."
        )
        (issues_dir / "bugs" / "P1-BUG-002-second.md").write_text(
            "# BUG-002: Second\n\n## Summary\nSecond issue.\n\n## Blocked By\n- BUG-001"
        )

        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()
        (sprints_dir / "resume-test.yaml").write_text(
            """name: resume-test
issues:
  - BUG-001
  - BUG-002
"""
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)

        # Pre-create state showing Wave 1 (BUG-001) already completed
        existing_state = SprintState(
            sprint_name="resume-test",
            current_wave=1,
            completed_issues=["BUG-001"],  # Wave 1 complete
            failed_issues={},
            started_at="2026-01-29T10:00:00",
            last_checkpoint="2026-01-29T10:05:00",
        )
        (tmp_path / ".sprint-state.json").write_text(json.dumps(existing_state.to_dict(), indent=2))

        executed_issues: list[str] = []

        def mock_process_inplace(info: Any, **kwargs: Any) -> Any:
            executed_issues.append(info.issue_id)
            from little_loops.issue_manager import IssueProcessingResult

            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr(
            "little_loops.issue_manager.process_issue_inplace",
            mock_process_inplace,
        )

        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="resume-test",
            dry_run=False,
            resume=True,  # Resume from existing state
            skip=None,
            max_workers=1,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 0

        # Only BUG-002 (Wave 2) should be executed
        # BUG-001 was in Wave 1 which was fully completed
        assert "BUG-002" in executed_issues
        assert "BUG-001" not in executed_issues

    def test_sprint_partial_wave_tracks_per_issue(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test that partial wave success tracks completed and failed issues separately."""
        import argparse

        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_error_recovery_project(tmp_path)

        class MockQueue:
            @property
            def completed_ids(self) -> list[str]:
                return ["BUG-001", "BUG-003"]

            @property
            def failed_ids(self) -> list[str]:
                return ["BUG-002"]

        class MockOrchestrator:
            execution_duration = 3.0

            def __init__(self, parallel_config: Any, br_config: Any, path: Any, **kwargs: Any):
                self.queue = MockQueue()

            def run(self) -> int:
                return 1  # Some failures

        monkeypatch.setattr("little_loops.cli.sprint.ParallelOrchestrator", MockOrchestrator)
        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="recovery-test",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=3,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 1

        state_data = json.loads((tmp_path / ".sprint-state.json").read_text())

        # Only actually-completed issues should be in completed_issues
        assert "BUG-001" in state_data["completed_issues"]
        assert "BUG-003" in state_data["completed_issues"]

        # Failed issue should be in both completed_issues (processed) and failed_issues
        assert "BUG-002" in state_data["completed_issues"]
        assert "BUG-002" in state_data["failed_issues"]

        # Only the actually-failed issue should be in failed_issues
        assert "BUG-001" not in state_data["failed_issues"]
        assert "BUG-003" not in state_data["failed_issues"]

    def test_sprint_stranded_issues_not_marked_completed(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Test that issues neither completed nor failed are left untracked for retry."""
        import argparse

        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_error_recovery_project(tmp_path)

        class MockQueue:
            @property
            def completed_ids(self) -> list[str]:
                return ["BUG-001"]  # Only 1 of 3 completed

            @property
            def failed_ids(self) -> list[str]:
                return ["BUG-002"]  # Only 1 of 3 failed
                # BUG-003 is stranded (not in either list)

        class MockOrchestrator:
            execution_duration = 3.0

            def __init__(self, parallel_config: Any, br_config: Any, path: Any, **kwargs: Any):
                self.queue = MockQueue()

            def run(self) -> int:
                return 1

        monkeypatch.setattr("little_loops.cli.sprint.ParallelOrchestrator", MockOrchestrator)
        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="recovery-test",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=3,
            quiet=False,
        )

        cli._cmd_sprint_run(args, manager, config)

        state_data = json.loads((tmp_path / ".sprint-state.json").read_text())

        # Stranded issue (BUG-003) should NOT be in completed_issues
        assert "BUG-003" not in state_data["completed_issues"]
        assert "BUG-003" not in state_data["failed_issues"]

        # BUG-001 completed, BUG-002 failed — both tracked
        assert "BUG-001" in state_data["completed_issues"]
        assert "BUG-002" in state_data["completed_issues"]
        assert "BUG-002" in state_data["failed_issues"]


    def test_sprint_sequential_retry_after_parallel_failure(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Test failed issues are retried sequentially and recovered (ENH-308)."""
        import argparse

        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_error_recovery_project(tmp_path)

        retry_calls: list[str] = []

        class MockQueue:
            @property
            def completed_ids(self) -> list[str]:
                return ["BUG-001"]

            @property
            def failed_ids(self) -> list[str]:
                return ["BUG-002", "BUG-003"]

        class MockOrchestrator:
            execution_duration = 3.0

            def __init__(self, parallel_config: Any, br_config: Any, path: Any, **kwargs: Any):
                self.queue = MockQueue()

            def run(self) -> int:
                return 1  # Some failures

        def mock_process_inplace(info: Any, **kwargs: Any) -> Any:
            retry_calls.append(info.issue_id)
            from little_loops.issue_manager import IssueProcessingResult

            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr("little_loops.cli.sprint.ParallelOrchestrator", MockOrchestrator)
        monkeypatch.setattr(
            "little_loops.issue_manager.process_issue_inplace",
            mock_process_inplace,
        )
        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="recovery-test",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=3,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        # All retries succeeded, so wave should not be counted as failed
        assert result == 0

        # Both failed issues should have been retried
        assert "BUG-002" in retry_calls
        assert "BUG-003" in retry_calls
        # BUG-001 (completed) should NOT be retried
        assert "BUG-001" not in retry_calls

        # State file is cleaned up on full success, so verify via absence
        # (state cleanup = no failures remaining = retries worked)
        state_file = tmp_path / ".sprint-state.json"
        assert not state_file.exists(), "State file should be cleaned up on full success"

    def test_sprint_sequential_retry_still_fails(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Test retry that also fails keeps issue in failed_issues (ENH-308)."""
        import argparse

        from little_loops.cli import sprint as cli

        _, config, manager = self._setup_error_recovery_project(tmp_path)

        class MockQueue:
            @property
            def completed_ids(self) -> list[str]:
                return ["BUG-001"]

            @property
            def failed_ids(self) -> list[str]:
                return ["BUG-002", "BUG-003"]

        class MockOrchestrator:
            execution_duration = 3.0

            def __init__(self, parallel_config: Any, br_config: Any, path: Any, **kwargs: Any):
                self.queue = MockQueue()

            def run(self) -> int:
                return 1

        def mock_process_inplace(info: Any, **kwargs: Any) -> Any:
            from little_loops.issue_manager import IssueProcessingResult

            # BUG-002 retry succeeds, BUG-003 retry also fails
            success = info.issue_id == "BUG-002"
            return IssueProcessingResult(success=success, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr("little_loops.cli.sprint.ParallelOrchestrator", MockOrchestrator)
        monkeypatch.setattr(
            "little_loops.issue_manager.process_issue_inplace",
            mock_process_inplace,
        )
        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="recovery-test",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=3,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        # BUG-003 still failed, so wave counts as failed
        assert result == 1

        state_data = json.loads((tmp_path / ".sprint-state.json").read_text())
        # BUG-002 recovered — should NOT be in failed_issues
        assert "BUG-002" not in state_data["failed_issues"]
        # BUG-003 still failed — should remain in failed_issues
        assert "BUG-003" in state_data["failed_issues"]


class TestDependencyHandling:
    """Integration tests for dependency handling in sprint execution."""

    def test_sprint_detects_dependency_cycle(self, tmp_path: Path) -> None:
        """Test circular dependencies are detected and reported."""
        import argparse

        from little_loops.cli import sprint as cli

        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()
        for category in ["bugs", "features", "completed"]:
            (issues_dir / category).mkdir()

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

        config_data = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                },
                "completed_dir": "completed",
            },
        }
        with open(config_dir / "ll-config.json", "w") as f:
            json.dump(config_data, f)

        # Create circular dependency: A -> B -> C -> A
        (issues_dir / "bugs" / "P1-BUG-001-a.md").write_text(
            "# BUG-001: A\n\n## Summary\nA.\n\n## Blocked By\n- BUG-003"
        )
        (issues_dir / "bugs" / "P1-BUG-002-b.md").write_text(
            "# BUG-002: B\n\n## Summary\nB.\n\n## Blocked By\n- BUG-001"
        )
        (issues_dir / "bugs" / "P1-BUG-003-c.md").write_text(
            "# BUG-003: C\n\n## Summary\nC.\n\n## Blocked By\n- BUG-002"
        )

        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()
        (sprints_dir / "cyclic.yaml").write_text(
            """name: cyclic
issues:
  - BUG-001
  - BUG-002
  - BUG-003
"""
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)

        args = argparse.Namespace(
            sprint="cyclic",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=1,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 1  # Should fail due to cycle

    def test_sprint_orphan_dependencies_handled(self, tmp_path: Path) -> None:
        """Test issues depending on non-existent issues log warning but proceed."""
        from little_loops.dependency_graph import DependencyGraph

        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()
        for category in ["bugs", "completed"]:
            (issues_dir / category).mkdir()

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

        config_data = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                },
                "completed_dir": "completed",
            },
        }
        with open(config_dir / "ll-config.json", "w") as f:
            json.dump(config_data, f)

        # BUG-001 depends on NONEXISTENT-999
        (issues_dir / "bugs" / "P1-BUG-001-orphan-dep.md").write_text(
            "# BUG-001: Orphan Dep\n\n## Summary\nDepends on missing.\n\n"
            "## Blocked By\n- NONEXISTENT-999"
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=tmp_path, config=config)

        # Create sprint
        manager.create(name="orphan-test", issues=["BUG-001"])

        # Load and build graph - should not fail
        issue_infos = manager.load_issue_infos(["BUG-001"])
        dep_graph = DependencyGraph.from_issues(issue_infos)

        # BUG-001 should be ready (orphan dependency ignored)
        waves = dep_graph.get_execution_waves()
        assert len(waves) == 1
        assert waves[0][0].issue_id == "BUG-001"

    def test_sprint_completed_dependencies_satisfied(self, tmp_path: Path) -> None:
        """Test blockers in completed dir are treated as satisfied."""
        from little_loops.dependency_graph import DependencyGraph

        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()
        for category in ["bugs", "completed"]:
            (issues_dir / category).mkdir()

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

        config_data = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                },
                "completed_dir": "completed",
            },
        }
        with open(config_dir / "ll-config.json", "w") as f:
            json.dump(config_data, f)

        # BUG-002 depends on BUG-001, but BUG-001 is completed
        (issues_dir / "completed" / "P1-BUG-001-done.md").write_text(
            "# BUG-001: Done\n\n## Summary\nAlready completed."
        )
        (issues_dir / "bugs" / "P1-BUG-002-depends.md").write_text(
            "# BUG-002: Depends\n\n## Summary\nDepends on completed BUG-001.\n\n"
            "## Blocked By\n- BUG-001"
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=tmp_path, config=config)

        manager.create(name="completed-dep", issues=["BUG-002"])

        issue_infos = manager.load_issue_infos(["BUG-002"])
        # Build graph with BUG-001 as completed
        dep_graph = DependencyGraph.from_issues(issue_infos, completed_ids={"BUG-001"})

        # BUG-002 should be ready since BUG-001 is completed
        waves = dep_graph.get_execution_waves(completed={"BUG-001"})
        assert len(waves) == 1
        assert waves[0][0].issue_id == "BUG-002"


class TestEdgeCases:
    """Integration tests for edge cases in sprint execution."""

    def test_sprint_single_issue(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test sprint with only one issue uses in-place processing."""
        import argparse

        from little_loops.cli import sprint as cli

        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()
        for category in ["bugs", "completed"]:
            (issues_dir / category).mkdir()

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

        config_data = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                },
                "completed_dir": "completed",
            },
        }
        with open(config_dir / "ll-config.json", "w") as f:
            json.dump(config_data, f)

        (issues_dir / "bugs" / "P1-BUG-001-only.md").write_text(
            "# BUG-001: Only\n\n## Summary\nThe only issue."
        )

        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()
        (sprints_dir / "single.yaml").write_text(
            """name: single
issues:
  - BUG-001
"""
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)

        inplace_called = []
        orchestrator_called = []

        def mock_process_inplace(info: Any, **kwargs: Any) -> Any:
            inplace_called.append(info.issue_id)
            from little_loops.issue_manager import IssueProcessingResult

            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr(
            "little_loops.issue_manager.process_issue_inplace",
            mock_process_inplace,
        )

        class MockQueue:
            @property
            def completed_ids(self) -> list[str]:
                return []

            @property
            def failed_ids(self) -> list[str]:
                return []

        class MockOrchestrator:
            execution_duration = 2.0

            def __init__(self, *args: Any, **kwargs: Any):
                orchestrator_called.append(True)
                self.queue = MockQueue()

            def run(self) -> int:
                return 0

        monkeypatch.setattr(
            "little_loops.cli.sprint.ParallelOrchestrator",
            MockOrchestrator,
        )

        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="single",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=1,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 0

        # Single issue should use in-place, not orchestrator
        assert len(inplace_called) == 1
        assert "BUG-001" in inplace_called
        assert len(orchestrator_called) == 0

    def test_sprint_all_issues_skipped(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test sprint where all issues are filtered via --skip."""
        import argparse

        from little_loops.cli import sprint as cli

        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()
        for category in ["bugs", "completed"]:
            (issues_dir / category).mkdir()

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

        config_data = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                },
                "completed_dir": "completed",
            },
        }
        with open(config_dir / "ll-config.json", "w") as f:
            json.dump(config_data, f)

        (issues_dir / "bugs" / "P1-BUG-001-skip.md").write_text(
            "# BUG-001: Skip\n\n## Summary\nWill be skipped."
        )

        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()
        (sprints_dir / "skip-all.yaml").write_text(
            """name: skip-all
issues:
  - BUG-001
"""
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)

        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="skip-all",
            dry_run=False,
            resume=False,
            skip="BUG-001",  # Skip the only issue
            max_workers=1,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        # Should fail because no issues remain after filtering
        assert result == 1

    def test_sprint_dry_run_no_execution(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test dry run mode makes no actual changes."""
        import argparse

        from little_loops.cli import sprint as cli

        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()
        for category in ["bugs", "completed"]:
            (issues_dir / category).mkdir()

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()

        config_data = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                },
                "completed_dir": "completed",
            },
        }
        with open(config_dir / "ll-config.json", "w") as f:
            json.dump(config_data, f)

        (issues_dir / "bugs" / "P1-BUG-001-dry.md").write_text(
            "# BUG-001: Dry\n\n## Summary\nDry run test."
        )

        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()
        (sprints_dir / "dry-run.yaml").write_text(
            """name: dry-run
issues:
  - BUG-001
"""
        )

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)

        inplace_called = []

        def mock_process_inplace(info: Any, **kwargs: Any) -> Any:
            inplace_called.append(info.issue_id)
            from little_loops.issue_manager import IssueProcessingResult

            return IssueProcessingResult(success=True, duration=1.0, issue_id=info.issue_id)

        monkeypatch.setattr(
            "little_loops.issue_manager.process_issue_inplace",
            mock_process_inplace,
        )

        monkeypatch.chdir(tmp_path)
        cli._sprint_shutdown_requested = False

        args = argparse.Namespace(
            sprint="dry-run",
            dry_run=True,  # Dry run mode
            resume=False,
            skip=None,
            max_workers=1,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 0

        # No actual processing should have occurred
        assert len(inplace_called) == 0

        # No state file should be created
        state_file = tmp_path / ".sprint-state.json"
        assert not state_file.exists()

    def test_sprint_not_found(self, tmp_path: Path) -> None:
        """Test error handling for non-existent sprint."""
        import argparse

        from little_loops.cli import sprint as cli

        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        with open(config_dir / "ll-config.json", "w") as f:
            json.dump({"project": {"name": "test"}}, f)

        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir()

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)

        args = argparse.Namespace(
            sprint="nonexistent",
            dry_run=False,
            resume=False,
            skip=None,
            max_workers=1,
            quiet=False,
        )

        result = cli._cmd_sprint_run(args, manager, config)
        assert result == 1  # Sprint not found
